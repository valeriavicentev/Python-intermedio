"""Prepara los datos del Radar Extractivo.

Lee las tablas crudas de data/raw/, hace los cruces geoespaciales y guarda
los resultados en data/processed/. Se corre una sola vez (o cuando cambian
los datos crudos):

    python scripts/preparar_datos.py

Pasos:
1. Normaliza los UBIGEO a 6 dígitos y une pobreza con los polígonos distritales.
2. Convierte las unidades mineras en puntos y verifica, con un spatial join,
   que cada punto cae dentro del distrito que declara su UBIGEO.
3. Traza un radio de influencia alrededor de cada unidad (por defecto 20 km)
   y calcula qué distritos vecinos toca, aunque no tengan una mina dentro.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
OUT = RAIZ / "data" / "processed"

# UTM 18S: proyección métrica que cubre la mayor parte del Perú andino.
# Sirve para medir radios en km; en los extremos del país el error es pequeño
# para un radio de 20 km.
CRS_METRICO = "EPSG:32718"
RADIO_KM = 20


def ubigeo(serie: pd.Series) -> pd.Series:
    return serie.astype(int).astype(str).str.zfill(6)


def cargar_pobreza() -> pd.DataFrame:
    p = pd.read_csv(RAW / "Poverty.csv", encoding="utf-8-sig")
    p["IDDIST"] = ubigeo(p["UBIGEO1"])
    return p.rename(
        columns={
            "POVERTY_RATE": "pobreza",
            "PBI_PC": "pbi_pc_dep",
            "IDH": "idh_dep",
        }
    )[["IDDIST", "pobreza", "pbi_pc_dep", "idh_dep"]]


def cargar_unidades() -> gpd.GeoDataFrame:
    m = pd.read_csv(RAW / "MINING.csv", encoding="utf-8-sig")
    m.columns = [c.strip() for c in m.columns]
    m = m.rename(
        columns={
            "MÉTODO DE EXPLOTACIÓN": "metodo",
            "TITULAR": "titular",
            "UNIDAD": "unidad",
            "REGION": "region",
            "PROVINCIA": "provincia",
            "DISTRITO": "distrito",
            "PRODUCTO": "producto",
        }
    )
    m["IDDIST"] = ubigeo(m["UBIGEO"])
    m["metodo"] = m["metodo"].str.upper().str.replace("MINERíA", "MINERÍA")
    m["id_unidad"] = [f"U{i:03d}" for i in range(1, len(m) + 1)]
    return gpd.GeoDataFrame(
        m.drop(columns=["UBIGEO"]),
        geometry=gpd.points_from_xy(m["LONGITUD"], m["LATITUD"]),
        crs="EPSG:4326",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    distritos = gpd.read_file(RAW / "peru_distrital_simple.geojson")
    distritos = distritos[["IDDIST", "NOMBDIST", "NOMBPROV", "NOMBDEP", "geometry"]]
    distritos = distritos.merge(cargar_pobreza(), on="IDDIST", how="left")

    unidades = cargar_unidades()

    # 1) Validación espacial: ¿el punto cae en el distrito que dice su UBIGEO?
    cruce = gpd.sjoin(
        unidades[["id_unidad", "IDDIST", "geometry"]],
        distritos[["IDDIST", "geometry"]].rename(columns={"IDDIST": "IDDIST_geo"}),
        how="left",
        predicate="within",
    )
    cruce = cruce.drop_duplicates("id_unidad").set_index("id_unidad")
    unidades["IDDIST_geo"] = unidades["id_unidad"].map(cruce["IDDIST_geo"])
    unidades["punto_coincide"] = unidades["IDDIST"] == unidades["IDDIST_geo"]

    # 2) Radio de influencia: distritos que toca cada unidad a RADIO_KM
    buffers = unidades[["id_unidad", "geometry"]].to_crs(CRS_METRICO)
    buffers["geometry"] = buffers.buffer(RADIO_KM * 1000)
    toques = gpd.sjoin(
        buffers,
        distritos[["IDDIST", "geometry"]].to_crs(CRS_METRICO),
        how="inner",
        predicate="intersects",
    )[["id_unidad", "IDDIST"]]

    # Resumen por distrito
    dentro = unidades.groupby("IDDIST").size().rename("unidades_dentro")
    cerca = toques.groupby("IDDIST")["id_unidad"].nunique().rename("unidades_20km")
    distritos = distritos.join(dentro, on="IDDIST").join(cerca, on="IDDIST")
    distritos[["unidades_dentro", "unidades_20km"]] = (
        distritos[["unidades_dentro", "unidades_20km"]].fillna(0).astype(int)
    )

    # Percentil de pobreza dentro del país (0-100): ayuda a leer el dato
    distritos["pobreza_percentil"] = (distritos["pobreza"].rank(pct=True) * 100).round(0)

    # Simplificar geometrías para que el mapa cargue rápido en la web
    distritos["geometry"] = distritos.geometry.simplify(0.003, preserve_topology=True)

    distritos.to_file(OUT / "distritos.geojson", driver="GeoJSON")
    unidades.drop(columns="geometry").to_csv(OUT / "unidades.csv", index=False)
    toques.to_csv(OUT / "influencia.csv", index=False)

    print(f"Distritos: {len(distritos)} | con pobreza: {distritos['pobreza'].notna().sum()}")
    print(f"Unidades: {len(unidades)} | punto dentro de su distrito: {unidades['punto_coincide'].sum()}")
    print(f"Distritos con unidad dentro: {(distritos['unidades_dentro'] > 0).sum()}")
    print(f"Distritos a {RADIO_KM} km de alguna unidad: {(distritos['unidades_20km'] > 0).sum()}")


if __name__ == "__main__":
    main()
