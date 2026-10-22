"""Paso 5 · El mismo análisis para los 10 incendios con más focos del Perú.

Para cada incendio (ranking de data/incendios_7d.csv):
1. Zona de estudio: focos + 2 km.
2. Busca Sentinel-2 L2A ANTES (hasta 45 días antes del primer foco) y DESPUÉS (desde el día
   siguiente al ÚLTIMO foco), mide el % de nubes dentro de la zona con SCL y elige el par
   del mismo tile con menos nubes (si hay varias limpias, la más cercana al incendio).
3. dNBR y área quemada con el mismo método que Chichas: dNBR >= 0,10 en manchas continuas
   a <= 200 m de un foco VIIRS. También guarda el resultado con el umbral 0,27.
4. Hectáreas por severidad, por distrito y por cobertura (ESA WorldCover 2021).
5. Imágenes antes/después en falso color y capa de severidad para el tablero.

Si un incendio no tiene un par de imágenes útil (nubes, sin imagen posterior), lo deja
anotado y sigue con el siguiente. Si se corta, vuelve a correrlo: salta los ya hechos.

Uso:
    python 05_top10.py                      # 10 incendios, imágenes de Earth Search (AWS)
    python 05_top10.py --n 5                # solo los 5 primeros
    python 05_top10.py --rehacer            # recalcula aunque ya existan resultados
Salidas: outputs/top10/<id>/..., outputs/top10.json, outputs/top10_resumen.csv
"""
import argparse
import importlib.util
import json
import math
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "4")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from PIL import Image
from rasterio import features, windows
from rasterio.enums import Resampling
from rasterio.transform import rowcol
from rasterio.warp import reproject, transform as warp_transform, transform_bounds
from scipy import ndimage
from shapely.geometry import mapping

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dnbr", BASE / "02_dnbr.py")
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)          # reutiliza las funciones de 02_dnbr.py

DATA = BASE / "data"
OUT = BASE / "outputs" / "top10"
OUT.mkdir(parents=True, exist_ok=True)

UMBRAL = 0.10
UMBRAL_USGS = 0.27
MAX_NUBES_TILE = 70        # descarta escenas casi cubiertas antes de medir la zona
NUBES_LIMPIA = 10          # % de nubes en la zona para considerar una imagen «limpia»
NUBES_MAX_PAR = 40         # por encima de esto en alguna fecha, el resultado es parcial o nublado
NUBLADOS = True            # procesar igual los incendios nublados (imágenes + parte despejada)
COLORES_SEV = {1: (154, 166, 178, 255), 2: (94, 158, 90, 255), 3: (217, 217, 208, 120),
               4: (246, 224, 138, 255), 5: (243, 162, 75, 255), 6: (217, 84, 44, 255),
               7: (122, 23, 18, 255)}
WORLDCOVER = {10: "Bosque", 20: "Matorral", 30: "Pastizal", 40: "Cultivo", 50: "Urbano",
              60: "Suelo desnudo", 70: "Nieve y hielo", 80: "Agua", 90: "Humedal herbáceo",
              95: "Manglar", 100: "Musgo y liquen"}
URL_WC_AWS = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
              "ESA_WorldCover_10m_2021_v200_{}_Map.tif")


def catalogo():
    if D.FUENTE == "aws":
        return pystac_client.Client.open(D.STAC_AWS)
    return pystac_client.Client.open(D.STAC, modifier=planetary_computer.sign_inplace)


def buscar(cat, aoi, d0, d1, max_nubes=MAX_NUBES_TILE):
    busq = cat.search(collections=["sentinel-2-l2a"], intersects=mapping(aoi),
                      datetime=f"{d0:%Y-%m-%d}/{d1:%Y-%m-%d}",
                      query={"eo:cloud_cover": {"lt": max_nubes}})
    return list(busq.items())


def medir(items, aoi, periodo):
    def uno(it):
        try:
            nubes, cob = D.nubes_en_zona(it, aoi)
        except Exception as e:                     # escena ilegible: se descarta
            return None
        return dict(periodo=periodo, fecha=it.datetime.strftime("%Y-%m-%d"), tile=D.tile_de(it),
                    nubes_tile=round(it.properties.get("eo:cloud_cover", np.nan), 1),
                    nubes_zona=nubes, cobertura_zona=cob, id=it.id, item=it)
    with ThreadPoolExecutor(max_workers=8) as ex:
        return [r for r in ex.map(uno, items) if r is not None]


def elegir(tabla, inicio, fin):
    """Mejor par antes/después del mismo tile: menos nubes; entre las limpias, la más cercana."""
    mejor = None
    for minimo in (95, 80):
        ok = tabla[tabla.cobertura_zona >= minimo]
        for tile, t in ok.groupby("tile"):
            a = t[t.periodo == "antes"].copy()
            d = t[t.periodo == "después"].copy()
            if a.empty or d.empty:
                continue
            a["dist"] = (inicio.normalize() - pd.to_datetime(a.fecha)).dt.days
            d["dist"] = (pd.to_datetime(d.fecha) - fin.normalize()).dt.days
            for x in (a, d):
                x["costo"] = np.where(x.nubes_zona <= NUBES_LIMPIA, x.nubes_zona / 10 + x.dist / 30,
                                      x.nubes_zona + x.dist / 30)
                # penaliza escenas cortadas por el borde del tile (franja sin dato en la imagen)
                x["costo"] = x["costo"] + (100 - x.cobertura_zona) * 0.5
            pa, pd_ = a.sort_values("costo").iloc[0], d.sort_values("costo").iloc[0]
            costo = pa.costo + pd_.costo + (0 if minimo == 95 else 5)
            if mejor is None or costo < mejor[0]:
                mejor = (costo, pa, pd_)
        if mejor is not None:
            break
    return mejor


def png_sev(clase, quemado, ruta, escala):
    rgba = np.zeros(clase.shape + (4,), np.uint8)
    for k, v in COLORES_SEV.items():
        rgba[clase == k] = v
    rgba = np.repeat(np.repeat(rgba, escala, 0), escala, 1)
    q = np.repeat(np.repeat(quemado, escala, 0), escala, 1)
    rgba[q & ~ndimage.binary_erosion(q, iterations=max(1, escala - 1))] = (20, 20, 20, 255)
    Image.fromarray(rgba, "RGBA").save(ruta, optimize=True)


def jpg(arr, ruta, lado_max=640):
    im = Image.fromarray((np.nan_to_num(arr) * 255).astype(np.uint8))
    f = lado_max / max(im.size)
    if f < 1:
        im = im.resize((round(im.size[0] * f), round(im.size[1] * f)), Image.LANCZOS)
    im.save(ruta, quality=80)


def worldcover(shape, tr, crs):
    oeste, sur, este, norte = transform_bounds(crs, "EPSG:4326", *rasterio.transform.array_bounds(shape[0], shape[1], tr))
    if D.FUENTE == "aws":
        urls = []
        for lat in range(math.floor(sur / 3) * 3, math.ceil(norte / 3) * 3, 3):
            for lon in range(math.floor(oeste / 3) * 3, math.ceil(este / 3) * 3, 3):
                urls.append(URL_WC_AWS.format(f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
                                              f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"))
    else:
        cat = catalogo()
        urls = [i.assets["map"].href for i in
                cat.search(collections=["esa-worldcover"], bbox=[oeste, sur, este, norte]).items()]
    cob = np.zeros(shape, "uint8")
    for url in urls:
        try:
            with rasterio.open(url) as src:
                w = windows.from_bounds(oeste, sur, este, norte, transform=src.transform)
                w = windows.Window(int(w.col_off) - 1, int(w.row_off) - 1,
                                   int(np.ceil(w.width)) + 3, int(np.ceil(w.height)) + 3)
                arr = src.read(1, window=w, boundless=True, fill_value=0)
                tmp = np.zeros(shape, "uint8")
                reproject(arr, tmp, src_transform=src.window_transform(w), src_crs=src.crs,
                          dst_transform=tr, dst_crs=crs, resampling=Resampling.nearest,
                          src_nodata=0, dst_nodata=0)
                cob = np.where(cob == 0, tmp, cob)
        except rasterio.errors.RasterioIOError:
            continue                                  # tile de océano: no existe
    return cob


def analizar(inc_id, inc, cat, dist_all):
    carpeta = OUT / str(inc_id)
    carpeta.mkdir(exist_ok=True)
    t0 = time.time()
    focos, aoi = D.zona_de_estudio(inc_id, 2.0)
    base = dict(id=int(inc_id), distrito=inc.distrito, provincia=inc.provincia,
                departamento=inc.departamento, distritos_focos=inc.distritos,
                focos=int(inc.focos), frp=round(float(inc.frp_total), 1),
                inicio=f"{inc.inicio:%Y-%m-%d %H:%M}", fin=f"{inc.fin:%Y-%m-%d %H:%M}",
                lat=round(inc.lat, 4), lon=round(inc.lon, 4))

    hoy = pd.Timestamp.now().normalize() + timedelta(days=1)
    pre_items = buscar(cat, aoi, inc.inicio.normalize() - timedelta(days=45),
                       inc.inicio.normalize() - timedelta(days=1))
    # Corte «después»: el día siguiente a cuando ya ocurrió el 90 % de los focos. Un foco
    # residual al final no debe impedir medir la cicatriz. Para la imagen posterior no se
    # filtra por nubes del tile completo: la zona puede estar despejada en un tile nublado.
    t90 = focos.fecha_hora.sort_values().iloc[int(np.ceil(0.9 * len(focos))) - 1]
    post_items = buscar(cat, aoi, t90.normalize() + timedelta(days=1), hoy, max_nubes=100)
    filas = medir(pre_items, aoi, "antes") + medir(post_items, aoi, "después")
    tabla = pd.DataFrame(filas)
    if not tabla.empty:
        tabla.drop(columns="item").sort_values(["periodo", "fecha"]).to_csv(carpeta / "candidatas.csv", index=False)
    items = {f["id"]: f["item"] for f in filas}
    par = elegir(tabla, inc.inicio, t90) if not tabla.empty else None
    if par is None or max(par[1].nubes_zona, par[2].nubes_zona) > NUBES_MAX_PAR:
        if tabla.empty or not (tabla.periodo == "después").any():
            motivo = f"No hay imagen Sentinel-2 posterior al {t90:%d %b} todavía"
        elif not (tabla.periodo == "antes").any():
            motivo = "No hay imagen Sentinel-2 previa al incendio"
        elif par is None:
            motivo = "Ninguna imagen cubre bien la zona (borde de tile o sin dato)"
        elif par[2].nubes_zona > NUBES_MAX_PAR:
            motivo = f"La mejor imagen posterior tiene {par[2].nubes_zona} % de nubes en la zona"
        else:
            motivo = f"La mejor imagen previa tiene {par[1].nubes_zona} % de nubes en la zona"
        if par is None or not NUBLADOS:
            res = dict(base, estado="sin_par", motivo=motivo, candidatas=int(len(tabla)))
            (carpeta / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
            print(f"   ✗ {motivo} ({len(tabla)} escenas revisadas)")
            return res
        nota_nubes = motivo           # se procesa igual: imágenes + lo que se vea despejado
        print(f"   ~ {motivo}: proceso la parte despejada")
    else:
        nota_nubes = None

    _, pre, post = par
    it_pre, it_post = items[pre.id], items[post.id]
    with rasterio.open(D.href(it_pre, "B8A")) as src:
        crs = src.crs
    aoi_crs, bounds = D.bounds_en_crs(aoi, crs, 1500)

    banda = {}
    for nombre, it in (("pre", it_pre), ("post", it_post)):
        off = D.baseline_offset(it)
        nir, tr, _ = D.leer(it, "B8A", bounds)
        swir, _, _ = D.leer(it, "B12", bounds)
        scl, _, _ = D.leer(it, "SCL", bounds)
        nir, swir = D.reflectancia(nir, off), D.reflectancia(swir, off)
        with np.errstate(invalid="ignore", divide="ignore"):
            banda[nombre] = dict(nbr=(nir - swir) / (nir + swir), scl=scl, off=off)
    shape = banda["pre"]["nbr"].shape
    dnbr = banda["pre"]["nbr"] - banda["post"]["nbr"]
    valido = (np.isin(banda["pre"]["scl"], list(D.SCL_VALIDOS)) &
              np.isin(banda["post"]["scl"], list(D.SCL_VALIDOS)) & np.isfinite(dnbr))
    en_zona = features.geometry_mask([mapping(aoi_crs)], shape, tr, invert=True)

    fx, fy = warp_transform("EPSG:4326", crs, focos.longitude.tolist(), focos.latitude.tolist())
    filas_px, cols_px = rowcol(tr, fx, fy)
    semilla = np.zeros(shape, bool)
    for r_, c_ in zip(filas_px, cols_px):
        if 0 <= r_ < shape[0] and 0 <= c_ < shape[1]:
            semilla[r_, c_] = True
    semilla = ndimage.binary_dilation(semilla, iterations=D.SIEMBRA_M // 20)

    def sembrado(u):
        m = valido & (np.nan_to_num(dnbr, nan=-9) >= u)
        m = ndimage.binary_opening(m)
        lab, _ = ndimage.label(m, structure=np.ones((3, 3)))
        ids = np.unique(lab[semilla & m])
        return np.isin(lab, ids[ids > 0])

    quemado = sembrado(UMBRAL)
    quemado_usgs = sembrado(UMBRAL_USGS)
    clase = np.zeros(shape, "uint8")
    clase[en_zona & ~valido] = 1
    zona_o_quemado = en_zona | quemado
    for cod, _, lo, hi, _ in D.CLASES:
        clase[zona_o_quemado & valido & (dnbr >= lo) & (dnbr < hi)] = cod

    ha = lambda m: round(float(m.sum() * D.PX_HA), 1)
    sev = {nom: ha(quemado & (dnbr >= lo) & (dnbr < hi)) for _, nom, lo, hi, _ in D.CLASES if lo >= 0.10 or nom == "Baja"}
    focos_px_sin_dato = int((semilla & ~valido & en_zona).sum())

    # distritos
    dist = dist_all.to_crs(crs.to_wkt())
    dist = dist[dist.intersects(aoi_crs.buffer(1500))].reset_index(drop=True)
    id_dist = features.rasterize(((g, i + 1) for i, g in enumerate(dist.geometry)),
                                 out_shape=shape, transform=tr, fill=0, dtype="int32")
    por_dist = sorted([dict(ubigeo=r.IDDIST, distrito=r.NOMBDIST, provincia=r.NOMBPROV,
                            departamento=r.NOMBDEP, ha=ha(quemado & (id_dist == i + 1)))
                       for i, r in dist.iterrows()], key=lambda d: -d["ha"])
    por_dist = [d for d in por_dist if d["ha"] > 0]

    # cobertura
    cob = worldcover(shape, tr, crs)
    por_cob = []
    for cod, nom in WORLDCOVER.items():
        hq, hz = ha(quemado & (cob == cod)), ha(en_zona & valido & (cob == cod))
        if hq > 0 or hz > 0:
            por_cob.append(dict(cobertura=nom, ha_quemadas=hq, ha_zona=hz))
    total_q = max(ha(quemado), 0.01)
    total_z = max(sum(c["ha_zona"] for c in por_cob), 0.01)
    for c in por_cob:
        c["pct_quemado"] = round(100 * c["ha_quemadas"] / total_q, 1)
        c["pct_zona"] = round(100 * c["ha_zona"] / total_z, 1)
    por_cob.sort(key=lambda c: -c["ha_quemadas"])

    # imágenes para el tablero y figura
    fc_pre = D.falso_color(it_pre, bounds, shape, banda["pre"]["off"])
    fc_post = D.falso_color(it_post, bounds, shape, banda["post"]["off"])
    jpg(fc_pre, carpeta / "antes.jpg")
    jpg(fc_post, carpeta / "despues.jpg")
    png_sev(clase, quemado, carpeta / "severidad.png", 2)
    focos_px = [[round(c_ / shape[1], 4), round(r_ / shape[0], 4)] for r_, c_ in zip(filas_px, cols_px)
                if 0 <= r_ < shape[0] and 0 <= c_ < shape[1]]
    with rasterio.open(carpeta / "dnbr.tif", "w", driver="GTiff", height=shape[0], width=shape[1],
                       count=1, dtype="float32", crs=crs, transform=tr, nodata=np.nan,
                       compress="deflate") as dst:
        dst.write(np.where(valido, dnbr, np.nan).astype("float32"), 1)

    fig, ax = plt.subplots(1, 3, figsize=(15, 5.6), constrained_layout=True)
    ax[0].imshow(fc_pre); ax[0].set_title(f"Antes · {pre.fecha} · nubes {pre.nubes_zona} %")
    ax[1].imshow(fc_post); ax[1].set_title(f"Después · {post.fecha} · nubes {post.nubes_zona} %")
    ax[1].scatter([p[0] * shape[1] for p in focos_px], [p[1] * shape[0] for p in focos_px],
                  s=6, c="#ffef3a", edgecolor="k", linewidth=0.3)
    ax[2].imshow(fc_post, alpha=0.35)
    ax[2].imshow(np.asarray(Image.open(carpeta / "severidad.png")), extent=(0, shape[1], shape[0], 0))
    ax[2].set_title(f"Quemado (dNBR >= {UMBRAL}, sembrado): {ha(quemado):,.0f} ha")
    for x in ax:
        x.set_xticks([]); x.set_yticks([])
    fig.suptitle(f"{inc.distrito.title()}, {inc.provincia.title()}, {inc.departamento.title()} · "
                 f"{int(inc.focos)} focos · id {inc_id}", fontsize=13)
    fig.savefig(carpeta / "mapa.png", dpi=110)
    plt.close(fig)

    sin_dato = 100 * float((en_zona & ~valido).sum()) / max(1, en_zona.sum())
    if nota_nubes is None:
        estado = "ok"
    elif sin_dato < 80:
        estado = "parcial"        # área quemada = mínimo, solo en la parte despejada
    else:
        estado = "nublado"        # casi todo tapado: se muestran las imágenes, no se mide
    res = dict(base, estado=estado, motivo=nota_nubes, candidatas=int(len(tabla)),
               imagen_antes=dict(fecha=pre.fecha, id=pre.id, tile=pre.tile, nubes_zona=float(pre.nubes_zona),
                                 dias_antes=int(pre.dist)),
               imagen_despues=dict(fecha=post.fecha, id=post.id, tile=post.tile, nubes_zona=float(post.nubes_zona),
                                   dias_despues=int(post.dist)),
               corte_despues=f"{t90:%Y-%m-%d %H:%M}",
               despues_antes_del_ultimo_foco=bool(pd.Timestamp(post.fecha) <= inc.fin.normalize()),
               zona_ha=ha(en_zona), pct_zona_sin_dato=round(100 * float((en_zona & ~valido).sum()) / max(1, en_zona.sum()), 1),
               ha_quemadas=ha(quemado), ha_quemadas_usgs_027=ha(quemado_usgs),
               ha_todos_px_010=ha(en_zona & valido & (dnbr >= UMBRAL)),
               ha_por_severidad=sev, ha_por_distrito=por_dist, ha_por_cobertura=por_cob,
               focos_en_nubes_px=focos_px_sin_dato,
               imagenes=dict(antes="antes.jpg", despues="despues.jpg", severidad="severidad.png",
                             ancho=int(shape[1]), alto=int(shape[0])),
               focos_xy=focos_px, segundos=round(time.time() - t0))
    (carpeta / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    top_cob = por_cob[0]["cobertura"] if por_cob else "—"
    print(f"   {'✓' if estado == 'ok' else '~'} [{estado}] {pre.fecha} → {post.fecha} · nubes {pre.nubes_zona} % / {post.nubes_zona} % · "
          f"{ha(quemado):,.0f} ha quemadas · sobre todo {top_cob} · {res['segundos']} s")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--ids", type=int, nargs="*", default=[], help="recalcular solo estos incendios")
    ap.add_argument("--fuente", choices=["pc", "aws"], default="aws")
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument("--sin-nublados", action="store_true",
                    help="no procesar incendios cuya mejor imagen tiene más de 40 %% de nubes")
    a = ap.parse_args()
    D.FUENTE = a.fuente
    global NUBLADOS
    NUBLADOS = not a.sin_nublados
    cat = catalogo()

    inc = pd.read_csv(DATA / "incendios_7d.csv", index_col=0, parse_dates=["inicio", "fin"])
    top = inc.sort_values(["focos", "frp_total"], ascending=False).head(a.n)
    dist_all = gpd.read_file(DATA / "peru_distrital.geojson").set_crs(4326, allow_override=True)

    resultados = []
    for k, (inc_id, r) in enumerate(top.iterrows(), 1):
        print(f"[{k}/{len(top)}] Incendio {inc_id} · {r.distrito.title()}, {r.departamento.title()} · "
              f"{r.focos} focos · {r.inicio:%d %b} a {r.fin:%d %b}")
        previo = OUT / str(inc_id) / "resumen.json"
        if previo.exists() and not a.rehacer and inc_id not in a.ids:
            res = json.loads(previo.read_text())
            if res.get("estado") in ("ok", "parcial", "nublado"):
                print("   = ya calculado (usa --rehacer para repetir)")
                resultados.append(res)
                continue
        try:
            resultados.append(analizar(inc_id, r, cat, dist_all))
        except Exception as e:
            print(f"   ✗ Error: {type(e).__name__}: {e}")
            resultados.append(dict(id=int(inc_id), distrito=r.distrito, provincia=r.provincia,
                                   departamento=r.departamento, focos=int(r.focos),
                                   estado="error", motivo=f"{type(e).__name__}: {e}"))

    for k, res in enumerate(resultados, 1):
        res["rank"] = k
    (BASE / "outputs" / "top10.json").write_text(json.dumps(
        dict(fuente="Earth Search (AWS)" if a.fuente == "aws" else "Microsoft Planetary Computer",
             umbral=UMBRAL, incendios=resultados), ensure_ascii=False, indent=2))
    filas = []
    for res in resultados:
        cob = (res.get("ha_por_cobertura") or [{}])[0]
        filas.append(dict(rank=res["rank"], id=res["id"], distrito=res["distrito"],
                          departamento=res["departamento"], focos=res["focos"], estado=res["estado"],
                          antes=res.get("imagen_antes", {}).get("fecha"),
                          despues=res.get("imagen_despues", {}).get("fecha"),
                          nubes_antes=res.get("imagen_antes", {}).get("nubes_zona"),
                          nubes_despues=res.get("imagen_despues", {}).get("nubes_zona"),
                          ha_quemadas=res.get("ha_quemadas"), ha_usgs_027=res.get("ha_quemadas_usgs_027"),
                          cobertura_principal=cob.get("cobertura"), pct_cobertura_principal=cob.get("pct_quemado"),
                          motivo=res.get("motivo", "")))
    t = pd.DataFrame(filas)
    t.to_csv(BASE / "outputs" / "top10_resumen.csv", index=False)
    print("\n" + t.drop(columns=["motivo"]).to_string(index=False))
    print("\nListo. Avísale a Claude para actualizar el tablero.")


if __name__ == "__main__":
    main()
