"""Paso 1 · Focos de calor VIIRS (S-NPP) de los últimos 7 días en el Perú.

- Descarga el CSV público de NASA FIRMS «South America 7d» (no pide clave).
- Se queda con los focos dentro del Perú y les asigna distrito (límites INEI, peru-geojson).
- Agrupa focos en «incendios»: focos a <= 1 km y <= 48 h pertenecen al mismo incendio.
- Imprime el ranking de incendios para elegir uno.

Uso:  python 01_focos.py
Salidas: data/focos_peru_7d.csv, data/incendios_7d.csv
"""
import io
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

URL_FIRMS = ("https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
             "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_7d.csv")
URL_DIST = ("https://raw.githubusercontent.com/juaneladio/peru-geojson/"
            "master/peru_distrital_simple.geojson")

DIST_M = 1000      # distancia máxima entre focos del mismo incendio
HORAS = 48         # separación temporal máxima


def descargar(url, destino):
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    destino.write_bytes(r.content)
    return r.content


def agrupar(xy, t_horas):
    """Union-find: une focos a <= DIST_M metros y <= HORAS horas."""
    padre = np.arange(len(xy))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i, j in cKDTree(xy).query_pairs(DIST_M):
        if abs(t_horas[i] - t_horas[j]) <= HORAS:
            ri, rj = raiz(i), raiz(j)
            if ri != rj:
                padre[rj] = ri
    raices = np.array([raiz(i) for i in range(len(xy))])
    _, etiquetas = np.unique(raices, return_inverse=True)
    return etiquetas


def main():
    crudo = descargar(URL_FIRMS, DATA / "firms_viirs_snpp_sa_7d.csv")
    df = pd.read_csv(io.BytesIO(crudo))
    print(f"FIRMS Sudamérica 7d: {len(df):,} focos "
          f"({df.acq_date.min()} a {df.acq_date.max()})")

    ruta_dist = DATA / "peru_distrital.geojson"
    if not ruta_dist.exists():
        descargar(URL_DIST, ruta_dist)
    dist = gpd.read_file(ruta_dist)[["IDDIST", "NOMBDIST", "NOMBPROV", "NOMBDEP", "geometry"]]
    dist = dist.set_crs(4326, allow_override=True)

    df = df[df.latitude.between(-18.6, 0.2) & df.longitude.between(-81.5, -68.5)]
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs=4326)
    g = gpd.sjoin(g, dist, how="inner", predicate="within").drop(columns="index_right")

    n_total = len(g)
    # Confianza VIIRS: l = baja, n = nominal, h = alta. Quitamos las de baja confianza.
    g = g[g.confidence.astype(str).str.lower().isin(["n", "h", "nominal", "high"])].copy()
    print(f"Focos en el Perú: {n_total:,}; sin confianza baja: {len(g):,}")

    g["fecha_hora"] = pd.to_datetime(
        g.acq_date + " " + g.acq_time.astype(int).astype(str).str.zfill(4),
        format="%Y-%m-%d %H%M")
    t_horas = (g.fecha_hora - g.fecha_hora.min()).dt.total_seconds().to_numpy() / 3600
    utm = g.to_crs(32718)
    xy = np.column_stack([utm.geometry.x, utm.geometry.y])
    g["incendio_id"] = agrupar(xy, t_horas)

    ultimo = g.fecha_hora.max()
    inc = (g.groupby("incendio_id")
             .agg(focos=("latitude", "size"),
                  frp_total=("frp", "sum"),
                  inicio=("fecha_hora", "min"),
                  fin=("fecha_hora", "max"),
                  lat=("latitude", "mean"),
                  lon=("longitude", "mean"),
                  lat_min=("latitude", "min"), lat_max=("latitude", "max"),
                  lon_min=("longitude", "min"), lon_max=("longitude", "max"),
                  distrito=("NOMBDIST", lambda s: s.mode().iat[0]),
                  provincia=("NOMBPROV", lambda s: s.mode().iat[0]),
                  departamento=("NOMBDEP", lambda s: s.mode().iat[0]),
                  distritos=("NOMBDIST", lambda s: ", ".join(sorted(s.unique())))))
    inc["focos_24h"] = (g[g.fecha_hora >= ultimo - pd.Timedelta(hours=24)]
                        .groupby("incendio_id").size()).reindex(inc.index, fill_value=0)
    inc = inc.sort_values(["focos", "frp_total"], ascending=False)

    g.drop(columns="geometry").to_csv(DATA / "focos_peru_7d.csv", index=False)
    inc.to_csv(DATA / "incendios_7d.csv")

    print(f"\n{len(inc):,} incendios (focos a <= {DIST_M} m y <= {HORAS} h). "
          f"Los 20 con más focos:\n")
    cols = ["focos", "focos_24h", "frp_total", "inicio", "fin", "distrito", "provincia", "departamento"]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(inc[cols].head(20).round({"frp_total": 1}).to_string())
    print("\nElige un incendio y corre:  python 02_dnbr.py --id <incendio_id>")


if __name__ == "__main__":
    main()
