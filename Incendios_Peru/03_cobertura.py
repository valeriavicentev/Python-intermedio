"""Paso 3 · ¿Qué se quemó? Cruce del área quemada con ESA WorldCover 2021 (10 m).

- Lee WorldCover (Planetary Computer, colección «esa-worldcover») solo en la zona del incendio.
- Lo lleva a la grilla del dNBR (20 m, vecino más cercano: es una variable categórica).
- Calcula hectáreas quemadas por tipo de cobertura y por severidad, y compara con la
  composición de toda la zona de estudio (¿el fuego «prefiere» alguna cobertura?).

Uso:  python 03_cobertura.py [--fuente aws]   (después de 02_dnbr.py)
Salidas: outputs/cobertura_quemada.csv, outputs/resumen_cobertura.json, outputs/cobertura.png
"""
import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio import windows
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds

BASE = Path(__file__).resolve().parent
OUT = BASE / "outputs"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
PX_HA = 0.04
UMBRAL = json.loads((Path(__file__).resolve().parent / "outputs" / "resumen_dnbr.json").read_text())["umbral_quemado"]

WORLDCOVER = {
    10: ("Bosque", "#006400"), 20: ("Matorral", "#ffbb22"), 30: ("Pastizal", "#ffff4c"),
    40: ("Cultivo", "#f096ff"), 50: ("Urbano", "#fa0000"), 60: ("Suelo desnudo", "#b4b4b4"),
    70: ("Nieve y hielo", "#f0f0f0"), 80: ("Agua", "#0064c8"), 90: ("Humedal herbáceo", "#0096a0"),
    95: ("Manglar", "#00cf75"), 100: ("Musgo y liquen", "#fae6a0"),
}
SEVERIDAD = {4: "Baja", 5: "Moderada-baja", 6: "Moderada-alta", 7: "Alta"}


URL_WC_AWS = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{}_Map.tif"


def hrefs_aws(oeste, sur, este, norte):
    """Tiles de 3x3 grados de WorldCover en el bucket público de AWS."""
    out = []
    for lat in range(math.floor(sur / 3) * 3, math.ceil(norte / 3) * 3, 3):
        for lon in range(math.floor(oeste / 3) * 3, math.ceil(este / 3) * 3, 3):
            nombre = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
            out.append(URL_WC_AWS.format(nombre))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuente", choices=["pc", "aws"], default="pc")
    fuente = ap.parse_args().fuente
    with rasterio.open(OUT / "clases_severidad.tif") as src:
        clase = src.read(1)
        tr, crs, shape = src.transform, src.crs, clase.shape
        b = src.bounds
    with rasterio.open(OUT / "dnbr.tif") as src:
        dnbr = src.read(1)

    oeste, sur, este, norte = transform_bounds(crs, "EPSG:4326", *b)
    if fuente == "aws":
        urls = hrefs_aws(oeste, sur, este, norte)
    else:
        cat = pystac_client.Client.open(STAC, modifier=planetary_computer.sign_inplace)
        items = list(cat.search(collections=["esa-worldcover"], bbox=[oeste, sur, este, norte],
                                query={"esa_worldcover:product_version": {"eq": "2.0.0"}}).items())
        if not items:  # por si cambia la etiqueta de versión
            items = list(cat.search(collections=["esa-worldcover"], bbox=[oeste, sur, este, norte]).items())
        urls = [i.assets["map"].href for i in items]
    print(f"Tiles WorldCover: {len(urls)}")

    cob = np.zeros(shape, "uint8")
    for url in urls:
        with rasterio.open(url) as src:
            w = windows.from_bounds(oeste, sur, este, norte, transform=src.transform)
            w = w.intersection(windows.Window(0, 0, src.width, src.height))
            w = windows.Window(int(w.col_off), int(w.row_off), int(np.ceil(w.width)) + 1,
                               int(np.ceil(w.height)) + 1)
            arr = src.read(1, window=w, boundless=True, fill_value=0)
            tmp = np.zeros(shape, "uint8")
            reproject(arr, tmp, src_transform=src.window_transform(w), src_crs=src.crs,
                      dst_transform=tr, dst_crs=crs, resampling=Resampling.nearest,
                      src_nodata=0, dst_nodata=0)
            cob = np.where(cob == 0, tmp, cob)

    en_zona = clase > 0
    valido = clase >= 2
    with rasterio.open(OUT / "quemado.tif") as src:
        quemado = src.read(1).astype(bool) & valido   # máscara definida en 02_dnbr.py

    filas = []
    for cod, (nom, color) in WORLDCOVER.items():
        m = cob == cod
        zona_ha = float((m & valido).sum() * PX_HA)
        q_ha = float((m & quemado).sum() * PX_HA)
        if zona_ha == 0 and q_ha == 0:
            continue
        fila = dict(codigo=cod, cobertura=nom, color=color, ha_zona_observada=round(zona_ha, 1),
                    ha_quemadas=round(q_ha, 1))
        for c, n in SEVERIDAD.items():
            fila[f"ha_{n}"] = round(float((m & quemado & (clase == c)).sum() * PX_HA), 1)
        filas.append(fila)
    t = pd.DataFrame(filas)
    t["pct_de_lo_quemado"] = (100 * t.ha_quemadas / t.ha_quemadas.sum()).round(1)
    t["pct_de_la_zona"] = (100 * t.ha_zona_observada / t.ha_zona_observada.sum()).round(1)
    t["pct_de_la_cobertura_que_se_quemo"] = (100 * t.ha_quemadas / t.ha_zona_observada).round(1)
    t = t.sort_values("ha_quemadas", ascending=False)
    t.to_csv(OUT / "cobertura_quemada.csv", index=False)

    sin_cob = float((quemado & (cob == 0)).sum() * PX_HA)
    resumen = dict(fuente=f"ESA WorldCover 2021 v200 (10 m), {'AWS' if fuente == 'aws' else 'Planetary Computer'}",
                   umbral_dnbr=UMBRAL, ha_quemadas_total=round(float(quemado.sum() * PX_HA), 1),
                   ha_quemadas_sin_cobertura=round(sin_cob, 1),
                   tabla=t.to_dict(orient="records"))
    (OUT / "resumen_cobertura.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2))

    # Gráfico: % de lo quemado vs % de la zona
    t2 = t[t.pct_de_lo_quemado > 0.5].iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(t2) + 1.6), constrained_layout=True)
    y = np.arange(len(t2))
    ax.barh(y + 0.2, t2.pct_de_lo_quemado, 0.4, color=t2.color, edgecolor="#333", label="% del área quemada")
    ax.barh(y - 0.2, t2.pct_de_la_zona, 0.4, color="none", edgecolor="#333", hatch="///",
            label="% de la zona de estudio")
    for yi, (q, h) in enumerate(zip(t2.pct_de_lo_quemado, t2.ha_quemadas)):
        ax.text(q + 0.8, yi + 0.2, f"{q:.0f} % · {h:,.0f} ha", va="center", fontsize=9)
    ax.set_yticks(y, t2.cobertura)
    ax.set_xlabel("%")
    ax.legend(loc="lower right", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"¿Qué se quemó? Cobertura del área quemada (dNBR >= {UMBRAL}) · WorldCover 2021")
    fig.savefig(OUT / "cobertura.png", dpi=150)
    plt.close(fig)

    with pd.option_context("display.width", 200):
        print(t.drop(columns=["color", "codigo"]).to_string(index=False))
    print("\nListo. Avísale a Claude para armar el README y el tablero.")


if __name__ == "__main__":
    main()
