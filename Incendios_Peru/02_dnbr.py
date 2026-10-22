"""Paso 2 · Área quemada de un incendio con dNBR (Sentinel-2 L2A, Planetary Computer).

1. Toma los focos del incendio elegido (data/focos_peru_7d.csv) y define la zona de
   estudio: envolvente de los focos + un buffer (2 km por defecto).
2. Busca imágenes Sentinel-2 L2A ANTES (hasta 75 días antes del primer foco) y DESPUÉS
   (desde el día siguiente al primer foco) y mide el % de nubes DENTRO de la zona con
   la capa SCL. Imprime la tabla de candidatas.
3. Elige el par (mismo tile MGRS) con menos nubes en la zona, o el que indiques con
   --pre / --post.
4. NBR = (B8A − B12) / (B8A + B12) a 20 m; dNBR = NBR_antes − NBR_después.
   Enmascara nubes, sombras, cirros, agua y nieve (SCL) en cualquiera de las dos fechas.
5. Clases de severidad USGS (Key y Benson 2006). Quemado = dNBR >= 0,27.
6. Hectáreas por clase y por distrito, mapas y archivos para el tablero.

Uso:
    python 02_dnbr.py --id 12 --solo-listar      # ver fechas y nubes, sin calcular
    python 02_dnbr.py --id 12                    # par automático
    python 02_dnbr.py --id 12 --pre 2026-09-20 --post 2026-10-18
    python 02_dnbr.py --id 12 --fuente aws       # plan B si Planetary Computer da error 429
"""
import argparse
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import json
from datetime import timedelta
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio import features, windows
from rasterio.enums import Resampling
from rasterio.transform import rowcol
from scipy import ndimage
from rasterio.warp import transform as warp_transform, transform_bounds, reproject, calculate_default_transform
from shapely.geometry import mapping
from shapely.ops import transform as shp_transform
import pyproj

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "outputs"
OUT.mkdir(exist_ok=True)

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
STAC_AWS = "https://earth-search.aws.element84.com/v1"   # plan B: mismas imágenes, sin token
FUENTE = "pc"
BANDAS_AWS = {"B8A": "nir08", "B12": "swir22", "SCL": "scl", "B04": "red"}


def href(item, banda):
    return item.assets[BANDAS_AWS[banda] if FUENTE == "aws" else banda].href


def tile_de(item):
    p = item.properties
    if p.get("s2:mgrs_tile"):
        return p["s2:mgrs_tile"]
    if p.get("mgrs:utm_zone"):
        return f"{p['mgrs:utm_zone']}{p.get('mgrs:latitude_band', '')}{p.get('mgrs:grid_square', '')}"
    return item.id.split("_")[1]
PX_HA = 20 * 20 / 10_000          # un píxel de 20 m = 0,04 ha
MARGEN_M = 3000                   # contexto extra alrededor de la zona en los mapas
SCL_VALIDOS = {2, 4, 5, 7}        # sombra oscura/topográfica, vegetación, suelo, sin clasificar
SCL_NUBE = {3, 8, 9, 10}          # sombra de nube, nube media, nube alta, cirros

# Clases de severidad (USGS / Key y Benson 2006)
CLASES = [
    (2, "Rebrote", -np.inf, -0.10, "#5e9e5a"),
    (3, "No quemado", -0.10, 0.10, "#d9d9d0"),
    (4, "Baja", 0.10, 0.27, "#f6e08a"),
    (5, "Moderada-baja", 0.27, 0.44, "#f3a24b"),
    (6, "Moderada-alta", 0.44, 0.66, "#d9542c"),
    (7, "Alta", 0.66, np.inf, "#7a1712"),
]
UMBRAL_QUEMADO = 0.10   # ver la decisión de método en el README
SIEMBRA_M = 200         # una mancha cuenta como incendio si está a <= 200 m de un foco VIIRS


def args_():
    p = argparse.ArgumentParser()
    p.add_argument("--id", type=int, required=True, help="incendio_id de 01_focos.py")
    p.add_argument("--pre", help="fecha de la imagen ANTES (YYYY-MM-DD)")
    p.add_argument("--post", help="fecha de la imagen DESPUÉS (YYYY-MM-DD)")
    p.add_argument("--buffer-km", type=float, default=2.0)
    p.add_argument("--umbral", type=float, default=UMBRAL_QUEMADO,
                   help="dNBR mínimo para contar un píxel como quemado")
    p.add_argument("--max-nubes-tile", type=float, default=80)
    p.add_argument("--solo-listar", action="store_true")
    p.add_argument("--fuente", choices=["pc", "aws"], default="pc",
                   help="pc = Planetary Computer; aws = Earth Search (AWS), sin token ni límite")
    return p.parse_args()


def zona_de_estudio(inc_id, buffer_km):
    focos = pd.read_csv(DATA / "focos_peru_7d.csv", parse_dates=["fecha_hora"])
    f = focos[focos.incendio_id == inc_id]
    if f.empty:
        raise SystemExit(f"No hay focos con incendio_id={inc_id}")
    g = gpd.GeoDataFrame(f, geometry=gpd.points_from_xy(f.longitude, f.latitude), crs=4326)
    gu = g.to_crs(32718).geometry
    pts = gu.union_all() if hasattr(gu, "union_all") else gu.unary_union
    aoi_utm = pts.convex_hull.buffer(buffer_km * 1000)
    aoi = gpd.GeoSeries([aoi_utm], crs=32718).to_crs(4326).iloc[0]
    return f, aoi


def baseline_offset(item):
    if item.properties.get("earthsearch:boa_offset_applied") is True:
        return 0
    try:
        return -1000 if float(item.properties.get("s2:processing_baseline", "0")) >= 4.0 else 0
    except ValueError:
        return -1000


def ventana(src, bounds):
    """Ventana entera (en píxeles) que cubre bounds en el CRS de src."""
    w = windows.from_bounds(*bounds, transform=src.transform)
    c0, r0 = int(np.floor(w.col_off)), int(np.floor(w.row_off))
    c1, r1 = int(np.ceil(w.col_off + w.width)), int(np.ceil(w.row_off + w.height))
    return windows.Window(c0, r0, c1 - c0, r1 - r0)


def bounds_en_crs(aoi, crs, margen=0):
    proj = pyproj.Transformer.from_crs("EPSG:4326", crs.to_wkt(), always_xy=True).transform
    a = shp_transform(proj, aoi)
    x0, y0, x1, y1 = a.bounds
    return a, (x0 - margen, y0 - margen, x1 + margen, y1 + margen)


def nubes_en_zona(item, aoi):
    """% de nubes y % de cobertura del tile dentro de la zona (capa SCL, 20 m)."""
    with rasterio.open(href(item, "SCL")) as src:
        a, b = bounds_en_crs(aoi, src.crs)
        w = ventana(src, b)
        scl = src.read(1, window=w, boundless=True, fill_value=0)
        tr = src.window_transform(w)
    dentro = features.geometry_mask([mapping(a)], scl.shape, tr, invert=True)
    s = scl[dentro]
    con_dato = s != 0
    cobertura = 100 * con_dato.mean()
    nubes = 100 * np.isin(s[con_dato], list(SCL_NUBE)).mean() if con_dato.any() else 100.0
    return round(nubes, 1), round(cobertura, 1)


def candidatas(aoi, inicio, max_nubes):
    if FUENTE == "aws":
        cat = pystac_client.Client.open(STAC_AWS)
    else:
        cat = pystac_client.Client.open(STAC, modifier=planetary_computer.sign_inplace)
    t0 = inicio.normalize()
    hoy = pd.Timestamp.now().normalize() + timedelta(days=1)
    periodos = {"antes": (t0 - timedelta(days=75), t0 - timedelta(days=1)),
                "después": (t0 + timedelta(days=1), hoy)}
    filas, items = [], {}
    for periodo, (d0, d1) in periodos.items():
        busq = cat.search(collections=["sentinel-2-l2a"], intersects=mapping(aoi),
                          datetime=f"{d0:%Y-%m-%d}/{d1:%Y-%m-%d}",
                          query={"eo:cloud_cover": {"lt": max_nubes}})
        for it in busq.items():
            nubes, cob = nubes_en_zona(it, aoi)
            items[it.id] = it
            filas.append(dict(periodo=periodo, fecha=it.datetime.strftime("%Y-%m-%d"),
                              tile=tile_de(it),
                              nubes_tile=round(it.properties.get("eo:cloud_cover", np.nan), 1),
                              nubes_zona=nubes, cobertura_zona=cob, id=it.id))
    tabla = pd.DataFrame(filas)
    if not tabla.empty:
        tabla = tabla.sort_values(["periodo", "fecha"], ascending=[True, True])
    return tabla, items


def elegir_par(tabla, pre, post):
    ok = tabla[tabla.cobertura_zona >= 95]
    if pre:
        ok = ok[(ok.periodo == "después") | (ok.fecha == pre)]
    if post:
        ok = ok[(ok.periodo == "antes") | (ok.fecha == post)]
    mejor = None
    for tile, t in ok.groupby("tile"):
        a = t[t.periodo == "antes"].sort_values(["nubes_zona", "fecha"], ascending=[True, False])
        d = t[t.periodo == "después"].sort_values(["nubes_zona", "fecha"], ascending=[True, False])
        if a.empty or d.empty:
            continue
        a, d = a.iloc[0], d.iloc[0]
        score = a.nubes_zona + d.nubes_zona
        if mejor is None or score < mejor[0]:
            mejor = (score, a, d)
    if mejor is None:
        raise SystemExit("No hay un par antes/después del mismo tile que cubra la zona. "
                         "Prueba con --max-nubes-tile 95 o fechas distintas.")
    return mejor[1], mejor[2]


def leer(item, banda, bounds, shape=None):
    with rasterio.open(href(item, banda)) as src:
        w = ventana(src, bounds)
        if shape is None:
            arr = src.read(1, window=w, boundless=True, fill_value=0)
            return arr, src.window_transform(w), src.crs
        arr = src.read(1, window=w, boundless=True, fill_value=0,
                       out_shape=shape, resampling=Resampling.average)
        return arr, None, src.crs


def reflectancia(dn, off):
    r = (dn.astype("float32") + off) / 10_000
    r[dn == 0] = np.nan
    return r


def falso_color(item, bounds, shape, off):
    rgb = [reflectancia(leer(item, b, bounds, shape)[0], off) for b in ("B12", "B8A", "B04")]
    rgb = np.dstack(rgb)
    lo, hi = np.nanpercentile(rgb, 2), np.nanpercentile(rgb, 98)
    return np.clip((rgb - lo) / (hi - lo), 0, 1)


def main():
    global FUENTE
    a = args_()
    FUENTE = a.fuente
    print(f"Fuente de imágenes: {'Earth Search (AWS)' if FUENTE == 'aws' else 'Planetary Computer'}")
    focos, aoi = zona_de_estudio(a.id, a.buffer_km)
    inc = pd.read_csv(DATA / "incendios_7d.csv", index_col=0, parse_dates=["inicio", "fin"]).loc[a.id]
    print(f"Incendio {a.id}: {inc.distrito}, {inc.provincia}, {inc.departamento} · "
          f"{inc.focos} focos del {inc.inicio:%d %b} al {inc.fin:%d %b}")

    tabla, items = candidatas(aoi, inc.inicio, a.max_nubes_tile)
    tabla.to_csv(OUT / "candidatas_sentinel2.csv", index=False)
    print("\nImágenes candidatas (nubes y cobertura medidas DENTRO de la zona):")
    print(tabla.drop(columns="id").to_string(index=False) if not tabla.empty else "  ninguna")
    if a.solo_listar:
        return

    pre, post = elegir_par(tabla, a.pre, a.post)
    print(f"\nPar elegido · tile {pre.tile}\n"
          f"  ANTES:   {pre.fecha}  nubes en la zona {pre.nubes_zona} %\n"
          f"  DESPUÉS: {post.fecha}  nubes en la zona {post.nubes_zona} %")
    it_pre, it_post = items[pre.id], items[post.id]

    with rasterio.open(href(it_pre, "B8A")) as src:
        crs = src.crs
    aoi_crs, bounds = bounds_en_crs(aoi, crs, MARGEN_M)

    banda = {}
    for nombre, it in (("pre", it_pre), ("post", it_post)):
        off = baseline_offset(it)
        nir, tr, _ = leer(it, "B8A", bounds)
        swir, _, _ = leer(it, "B12", bounds)
        scl, _, _ = leer(it, "SCL", bounds)
        nir, swir = reflectancia(nir, off), reflectancia(swir, off)
        with np.errstate(invalid="ignore", divide="ignore"):
            nbr = (nir - swir) / (nir + swir)
        banda[nombre] = dict(nbr=nbr, scl=scl, off=off)

    shape = banda["pre"]["nbr"].shape
    dnbr = banda["pre"]["nbr"] - banda["post"]["nbr"]
    valido = (np.isin(banda["pre"]["scl"], list(SCL_VALIDOS)) &
              np.isin(banda["post"]["scl"], list(SCL_VALIDOS)) & np.isfinite(dnbr))
    en_zona = features.geometry_mask([mapping(aoi_crs)], shape, tr, invert=True)

    clase = np.zeros(shape, "uint8")        # 0 = fuera de la zona
    clase[en_zona & ~valido] = 1            # 1 = sin dato (nube, sombra, agua) en alguna fecha
    for cod, _, lo, hi, _ in CLASES:
        clase[en_zona & valido & (dnbr >= lo) & (dnbr < hi)] = cod
    # Área quemada «sembrada con focos»: manchas continuas con dNBR >= umbral que tocan
    # un foco VIIRS (a <= SIEMBRA_M). Quita ruido suelto lejos del fuego y no corta la
    # cicatriz en el borde de la zona de estudio (se busca en toda la ventana).
    fx, fy = warp_transform("EPSG:4326", crs, focos.longitude.tolist(), focos.latitude.tolist())
    filas, cols = rowcol(tr, fx, fy)
    semilla = np.zeros(shape, bool)
    for r_, c_ in zip(filas, cols):
        if 0 <= r_ < shape[0] and 0 <= c_ < shape[1]:
            semilla[r_, c_] = True
    semilla = ndimage.binary_dilation(semilla, iterations=max(1, SIEMBRA_M // 20))

    def sembrado(umbral):
        m = valido & (np.nan_to_num(dnbr, nan=-9) >= umbral)
        m = ndimage.binary_opening(m)                    # quita píxeles sueltos
        lab, _ = ndimage.label(m, structure=np.ones((3, 3)))
        ids = np.unique(lab[semilla & m])
        return np.isin(lab, ids[ids > 0])

    quemado = sembrado(a.umbral)
    sensibilidad = []
    for u in (0.10, 0.15, 0.20, 0.27):
        sensibilidad.append(dict(
            umbral=u,
            ha_todos_los_pixeles_en_zona=round(float((en_zona & valido & (dnbr >= u)).sum() * PX_HA), 1),
            ha_sembrado_con_focos=round(float(sembrado(u).sum() * PX_HA), 1)))
    # La cicatriz puede salir del buffer: esos píxeles también reciben su clase de severidad
    for cod, _, lo, hi, _ in CLASES:
        clase[quemado & ~en_zona & (dnbr >= lo) & (dnbr < hi)] = cod

    # Hectáreas por clase
    ha_clase = {nom: round(float((clase == cod).sum() * PX_HA), 1) for cod, nom, *_ in CLASES}
    ha_zona = float(en_zona.sum() * PX_HA)
    ha_sin_dato = float((clase == 1).sum() * PX_HA)
    ha_quemado = float(quemado.sum() * PX_HA)
    ha_quemado_fuera_zona = float((quemado & ~en_zona).sum() * PX_HA)
    sev_quemado = {nom: round(float((quemado & valido & (dnbr >= lo) & (dnbr < hi)).sum() * PX_HA), 1)
                   for _, nom, lo, hi, _ in CLASES if lo >= 0.10 or nom == "Baja"}

    # Hectáreas quemadas por distrito
    dist = gpd.read_file(DATA / "peru_distrital.geojson").set_crs(4326, allow_override=True).to_crs(crs.to_wkt())
    dist = dist[dist.intersects(aoi_crs.buffer(MARGEN_M))].reset_index(drop=True)
    id_dist = features.rasterize(((geom, i + 1) for i, geom in enumerate(dist.geometry)),
                                 out_shape=shape, transform=tr, fill=0, dtype="int32")
    por_dist = []
    for i, r in dist.iterrows():
        ha = float((quemado & (id_dist == i + 1)).sum() * PX_HA)
        if ha > 0:
            por_dist.append(dict(ubigeo=r.IDDIST, distrito=r.NOMBDIST, provincia=r.NOMBPROV,
                                 departamento=r.NOMBDEP, ha_quemadas=round(ha, 1)))
    por_dist.sort(key=lambda d: -d["ha_quemadas"])

    # Rasters
    perfil = dict(driver="GTiff", height=shape[0], width=shape[1], count=1, crs=crs,
                  transform=tr, compress="deflate")
    with rasterio.open(OUT / "dnbr.tif", "w", dtype="float32", nodata=np.nan, **perfil) as dst:
        dst.write(np.where(valido, dnbr, np.nan).astype("float32"), 1)
    with rasterio.open(OUT / "clases_severidad.tif", "w", dtype="uint8", nodata=0, **perfil) as dst:
        dst.write(clase, 1)
    with rasterio.open(OUT / "quemado.tif", "w", dtype="uint8", nodata=None, **perfil) as dst:
        dst.write(quemado.astype("uint8"), 1)

    # Mapa
    ext = (bounds[0], bounds[2], bounds[1], bounds[3])
    colores = ["#ffffff00", "#9aa6b2"] + [c for *_, c in CLASES]
    cmap = ListedColormap(colores)
    norm = BoundaryNorm(np.arange(-0.5, 8.5, 1), cmap.N)
    fig, ax = plt.subplots(1, 3, figsize=(18, 6.6), constrained_layout=True)
    for k, (it, fecha, off) in enumerate(((it_pre, pre.fecha, banda["pre"]["off"]),
                                          (it_post, post.fecha, banda["post"]["off"]))):
        ax[k].imshow(falso_color(it, bounds, shape, off), extent=ext)
        ax[k].set_title(f"{'Antes' if k == 0 else 'Después'} · {fecha} · falso color (B12, B8A, B4)")
    ax[1].scatter(fx, fy, s=6, c="#ffef3a", edgecolor="k", linewidth=0.3, label="Focos VIIRS")
    ax[1].legend(loc="lower right", fontsize=8)
    ax[2].imshow(np.where(clase == 0, np.nan, clase), cmap=cmap, norm=norm, extent=ext,
                 interpolation="nearest")
    xs = np.linspace(ext[0], ext[1], shape[1])
    ys = np.linspace(ext[3], ext[2], shape[0])
    ax[2].contour(xs, ys, quemado.astype(float), levels=[0.5], colors="#111111", linewidths=1.1)
    ax[2].set_title(f"Severidad dNBR · área quemada (dNBR >= {a.umbral}, sembrada con focos): "
                    f"{ha_quemado:,.0f} ha", fontsize=10)
    leyenda = [Patch(facecolor="none", edgecolor="#111111", label="Área quemada")] + \
              [Patch(color="#9aa6b2", label="Sin dato (nubes)")] + \
              [Patch(color=c, label=n) for _, n, *_, c in CLASES]
    ax[2].legend(handles=leyenda, loc="lower right", fontsize=8)
    for x in ax:
        gpd.GeoSeries([aoi_crs]).boundary.plot(ax=x, color="#00e5ff", linewidth=1)
        dist.boundary.plot(ax=x, color="white", linewidth=0.5, alpha=0.6)
        x.set_xlim(ext[0], ext[1]); x.set_ylim(ext[2], ext[3])
        x.set_xticks([]); x.set_yticks([]); x.set_xlabel(""); x.set_ylabel("")
    fig.suptitle(f"Incendio en {inc.distrito.title()}, {inc.provincia.title()}, "
                 f"{inc.departamento.title()} · Sentinel-2 L2A", fontsize=14)
    fig.savefig(OUT / "mapa_dnbr.png", dpi=150)
    plt.close(fig)

    # Capa de clases en EPSG:4326 para el tablero web
    dtr, dw, dh = calculate_default_transform(crs, "EPSG:4326", shape[1], shape[0], *bounds)
    clase_ll = np.zeros((dh, dw), "uint8")
    reproject(clase, clase_ll, src_transform=tr, src_crs=crs, dst_transform=dtr,
              dst_crs="EPSG:4326", resampling=Resampling.nearest)
    rgba = np.zeros((dh, dw, 4))
    for cod, c in enumerate(colores):
        if cod == 0:
            continue
        rgba[clase_ll == cod] = matplotlib.colors.to_rgba(c)
    plt.imsave(OUT / "clases_4326.png", rgba)
    w_, s_, e_, n_ = transform_bounds(crs, "EPSG:4326", *bounds)

    resumen = dict(
        incendio=dict(id=int(a.id), distrito=inc.distrito, provincia=inc.provincia,
                      departamento=inc.departamento, focos=int(inc.focos),
                      inicio=f"{inc.inicio:%Y-%m-%d %H:%M}", fin=f"{inc.fin:%Y-%m-%d %H:%M}",
                      lat=round(inc.lat, 4), lon=round(inc.lon, 4)),
        zona=dict(buffer_km=a.buffer_km, ha=round(ha_zona, 1),
                  ha_sin_dato=round(ha_sin_dato, 1),
                  pct_sin_dato=round(100 * ha_sin_dato / ha_zona, 1)),
        fuente_imagenes="Earth Search (AWS)" if FUENTE == "aws" else "Microsoft Planetary Computer",
        imagen_antes=dict(fecha=pre.fecha, id=pre.id, tile=pre.tile, nubes_zona=pre.nubes_zona,
                          nubes_tile=pre.nubes_tile),
        imagen_despues=dict(fecha=post.fecha, id=post.id, tile=post.tile, nubes_zona=post.nubes_zona,
                            nubes_tile=post.nubes_tile),
        metodo=f"dNBR >= {a.umbral}, manchas continuas a <= {SIEMBRA_M} m de un foco VIIRS",
        umbral_quemado=a.umbral,
        ha_quemadas=round(ha_quemado, 1),
        ha_quemadas_fuera_de_zona=round(ha_quemado_fuera_zona, 1),
        ha_quemadas_por_severidad=sev_quemado,
        sensibilidad_umbral=sensibilidad,
        ha_por_clase=ha_clase,
        ha_por_distrito=por_dist,
        capa_4326=dict(png="outputs/clases_4326.png", oeste=w_, sur=s_, este=e_, norte=n_),
        focos=[[round(y, 5), round(x, 5)] for x, y in zip(focos.longitude, focos.latitude)],
    )
    (OUT / "resumen_dnbr.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2))

    print(f"\nZona de estudio: {ha_zona:,.0f} ha · sin dato por nubes: {ha_sin_dato:,.0f} ha "
          f"({resumen['zona']['pct_sin_dato']} %)")
    print(f"ÁREA QUEMADA (dNBR >= {a.umbral}, sembrada con focos): {ha_quemado:,.1f} ha "
          f"(de ellas {ha_quemado_fuera_zona:,.1f} ha fuera de la zona de {a.buffer_km} km)")
    print("Área quemada por severidad:", sev_quemado)
    print("\nSensibilidad al umbral (ha):")
    print(pd.DataFrame(sensibilidad).to_string(index=False))
    print("\nClases en toda la zona:", ha_clase)
    print("Por distrito:", [(d["distrito"], d["ha_quemadas"]) for d in por_dist])
    print("\nRevisa outputs/mapa_dnbr.png y luego corre:  python 03_cobertura.py")


if __name__ == "__main__":
    main()
