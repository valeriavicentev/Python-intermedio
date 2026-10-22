"""Paso 6 · ¿Hay imágenes Landsat 8/9 despejadas para los incendios tapados por nubes?

Solo busca y mide nubes; no calcula nada. Para cada incendio sin imagen Sentinel-2 útil
(estado «parcial» o «nublado» en outputs/top10.json) lista las escenas Landsat Collection 2
Level-2 antes y después, con el % de nubes DENTRO de la zona (capa QA_PIXEL), y prueba si
se pueden leer desde Earth Search (AWS) y desde Planetary Computer.

Uso:  python 06_buscar_landsat.py
Salida: outputs/landsat_candidatas.csv
"""
import importlib.util
import json
import os
import warnings
from datetime import timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio import features, windows
from shapely.geometry import mapping

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dnbr", BASE / "02_dnbr.py")
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)

FUENTES = {
    "aws": ("https://earth-search.aws.element84.com/v1", None),
    "pc": ("https://planetarycomputer.microsoft.com/api/stac/v1", planetary_computer.sign_inplace),
}
# QA_PIXEL: bit 1 nube dilatada, 2 cirros, 3 nube, 4 sombra de nube
MASCARA_NUBE = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)


def href_qa(item):
    for k in ("qa_pixel", "QA_PIXEL", "qa"):
        if k in item.assets:
            a = item.assets[k]
            alt = (a.extra_fields.get("alternate") or {})
            for v in alt.values():
                if v.get("href", "").startswith("http"):
                    return v["href"]
            return a.href
    return None


def nubes_zona(item, aoi):
    h = href_qa(item)
    if h is None:
        return None, None, "sin QA_PIXEL"
    if h.startswith("s3://"):
        h = "/vsis3/" + h[5:]
    try:
        with rasterio.open(h) as src:
            a, b = D.bounds_en_crs(aoi, src.crs)
            w = D.ventana(src, b)
            qa = src.read(1, window=w, boundless=True, fill_value=1)
            tr = src.window_transform(w)
    except Exception as e:
        return None, None, f"no se pudo leer: {type(e).__name__}"
    dentro = features.geometry_mask([mapping(a)], qa.shape, tr, invert=True)
    q = qa[dentro]
    con_dato = (q & 1) == 0          # bit 0 = relleno
    if not con_dato.any():
        return 100.0, 0.0, "ok"
    nubes = 100 * ((q[con_dato] & MASCARA_NUBE) > 0).mean()
    return round(float(nubes), 1), round(100 * float(con_dato.mean()), 1), "ok"


def main():
    top = json.loads((BASE / "outputs" / "top10.json").read_text())["incendios"]
    pendientes = [r for r in top if r["estado"] in ("parcial", "nublado", "sin_par")]
    filas = []
    for r in pendientes:
        focos, aoi = D.zona_de_estudio(r["id"], 2.0)
        t0 = focos.fecha_hora.min().normalize()
        t90 = focos.fecha_hora.sort_values().iloc[int(np.ceil(0.9 * len(focos))) - 1].normalize()
        hoy = pd.Timestamp.now().normalize() + timedelta(days=1)
        print(f"\nIncendio {r['id']} · {r['distrito'].title()}, {r['departamento'].title()}")
        for fuente, (url, mod) in FUENTES.items():
            try:
                cat = pystac_client.Client.open(url, modifier=mod) if mod else pystac_client.Client.open(url)
                for periodo, d0, d1 in (("antes", t0 - timedelta(days=60), t0 - timedelta(days=1)),
                                        ("después", t90 + timedelta(days=1), hoy)):
                    items = list(cat.search(collections=["landsat-c2-l2"], intersects=mapping(aoi),
                                            datetime=f"{d0:%Y-%m-%d}/{d1:%Y-%m-%d}",
                                            query={"platform": {"in": ["landsat-8", "landsat-9"]}}).items())
                    for it in items:
                        nubes, cob, estado = nubes_zona(it, aoi)
                        filas.append(dict(id=r["id"], distrito=r["distrito"], fuente=fuente, periodo=periodo,
                                          fecha=it.datetime.strftime("%Y-%m-%d"), satelite=it.properties.get("platform"),
                                          nubes_escena=it.properties.get("eo:cloud_cover"), nubes_zona=nubes,
                                          cobertura_zona=cob, lectura=estado, item=it.id))
                        print(f"   {fuente:3} {periodo:7} {filas[-1]['fecha']} {filas[-1]['satelite']}: "
                              f"nubes en la zona {nubes} % · cobertura {cob} % · {estado}")
                    if not items:
                        print(f"   {fuente:3} {periodo:7} sin escenas")
            except Exception as e:
                print(f"   {fuente:3} error: {type(e).__name__}: {str(e)[:120]}")
    t = pd.DataFrame(filas)
    t.to_csv(BASE / "outputs" / "landsat_candidatas.csv", index=False)
    if not t.empty:
        limpias = t[(t.periodo == "después") & (t.nubes_zona <= 40) & (t.cobertura_zona >= 80)]
        print("\nImágenes Landsat POSTERIORES con 40 % de nubes o menos en la zona:")
        print(limpias.drop(columns="item").to_string(index=False) if not limpias.empty else "   ninguna")
    print("\nListo. Pásale el resultado a Claude.")


if __name__ == "__main__":
    main()
