"""Mapa coroplético de la pobreza monetaria departamental (ENAHO 2024) con las unidades mineras encima.

    uv run .claude/skills/mapeando-enaho/scripts/mapear.py [--sin-minas]

Une ccdd (= ubigeo[:2]) con FIRST_IDDP del GeoJSON del curso, como texto. Nunca por nombre.
"""
import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SKILL = Path(__file__).resolve().parent.parent
RAIZ = Path.cwd()
BASE = RAIZ / "salidas" / "personas_2024.parquet"
GEO = SKILL / "peru_departamental_simple.geojson"
REF = SKILL / "pobreza_departamento_2024.csv"
MINAS = RAIZ / "datos" / "unidades_mineras.csv"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sin-minas", action="store_true")
    a = p.parse_args()
    if not BASE.exists():
        raise SystemExit("ERROR: falta salidas/personas_2024.parquet. Corre primero la skill limpiando-enaho.")
    df = pd.read_parquet(BASE)
    pob = (df.groupby("ccdd").apply(lambda d: 100 * np.average(d.pobre, weights=d.facpob07), include_groups=False)
           .rename("pobreza_pct").reset_index())
    geo = gpd.read_file(GEO)
    geo["FIRST_IDDP"] = geo.FIRST_IDDP.astype(str).str.zfill(2)
    m = geo.merge(pob, left_on="FIRST_IDDP", right_on="ccdd", how="left", validate="1:1")
    faltan = m[m.pobreza_pct.isna()].NOMBDEP.tolist()
    if len(m) != 25 or faltan:
        raise SystemExit(f"ERROR: el mapa debe tener 25 departamentos con dato; faltan {faltan}")
    assert {"07", "15"} <= set(m.FIRST_IDDP), "Lima (15) y Callao (07) deben estar separados"

    ref = pd.read_csv(REF, dtype={"ccdd": str})
    comp = pob.merge(ref, on="ccdd", suffixes=("", "_ref"))
    comp["dif"] = (comp.pobreza_pct - comp.pobreza_pct_ref).abs()
    print(f"Comparación con la referencia de la Sesión 16: {len(comp)} departamentos, "
          f"diferencia máxima {comp.dif.max():.2f} pp ({comp.loc[comp.dif.idxmax(), 'departamento']})")
    if comp.dif.max() > 0.1:
        print("AVISO: hay departamentos que difieren en más de 0.1 pp de la referencia:")
        print(comp[comp.dif > 0.1].round(2).to_string(index=False))

    fig, ax = plt.subplots(figsize=(7.5, 9.5))
    m.plot(column="pobreza_pct", cmap="Reds", vmin=0, vmax=np.ceil(m.pobreza_pct.max() / 5) * 5, ax=ax,
           edgecolor="white", linewidth=0.6, legend=True,
           legend_kwds={"label": "Pobreza monetaria (% de personas)", "shrink": 0.55})
    for r in m.itertuples():
        pt = r.geometry.representative_point()
        ax.annotate(f"{r.pobreza_pct:.0f}", (pt.x, pt.y), ha="center", fontsize=7, color="#222")
    titulo = "Pobreza monetaria por departamento, Perú 2024"
    if not a.sin_minas and MINAS.exists():
        u = pd.read_csv(MINAS, encoding="utf-8-sig")
        u.columns = u.columns.str.strip()
        u = u[u["MÉTODO DE EXPLOTACIÓN"].str.upper().str.contains("SUBTERR|SUPERFICIAL", regex=True)]
        ax.scatter(u.LONGITUD, u.LATITUD, s=10, marker="^", color="#1f4e79", edgecolor="white", linewidth=0.3,
                   label=f"Unidad minera metálica (n={len(u)})", zorder=3)
        ax.legend(loc="lower left", fontsize=8, frameon=False)
        titulo += "\ny unidades mineras metálicas"
    ax.set_title(titulo, loc="left", fontsize=12)
    ax.set_axis_off()
    fig.text(0.02, 0.02, "Fuente: INEI, ENAHO 2024 (ponderado con facpob07); unidades mineras: MINEM, repositorio "
                         "del curso (sesión 06).", fontsize=7, color="gray")
    salida = RAIZ / "mapas" / "pobreza_departamento.png"
    salida.parent.mkdir(exist_ok=True)
    fig.savefig(salida, dpi=200, bbox_inches="tight")
    m[["FIRST_IDDP", "NOMBDEP", "pobreza_pct"]].sort_values("pobreza_pct", ascending=False).to_csv(
        RAIZ / "salidas" / "pobreza_departamento_mapa.csv", index=False)
    print(f"Mapa: {salida.relative_to(RAIZ)} · 25/25 departamentos con dato")
    print(m.sort_values("pobreza_pct", ascending=False)[["FIRST_IDDP", "NOMBDEP", "pobreza_pct"]]
          .round(1).to_string(index=False))


if __name__ == "__main__":
    main()
