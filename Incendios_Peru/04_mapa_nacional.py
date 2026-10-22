"""Paso 4 · Mapa nacional: todos los focos e incendios de la semana en el Perú.

- Usa los resultados de 01_focos.py (data/focos_peru_7d.csv y data/incendios_7d.csv).
- Cuenta focos por departamento y por día, y arma el ranking de incendios.
- Dibuja el mapa nacional (outputs/mapa_nacional.png) con el incendio estudiado destacado.
- Exporta outputs/nacional.json para el tablero web.

Uso:  python 04_mapa_nacional.py [--id 990]
"""
import argparse
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "outputs"
OUT.mkdir(exist_ok=True)
URL_DEP = ("https://raw.githubusercontent.com/juaneladio/peru-geojson/"
           "master/peru_departamental_simple.geojson")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, default=990, help="incendio estudiado en 02_dnbr.py")
    a = ap.parse_args()

    ruta = DATA / "peru_departamental.geojson"
    if not ruta.exists():
        r = requests.get(URL_DEP, timeout=120)
        r.raise_for_status()
        ruta.write_bytes(r.content)
    dep = gpd.read_file(ruta).set_crs(4326, allow_override=True)

    focos = pd.read_csv(DATA / "focos_peru_7d.csv", parse_dates=["fecha_hora"])
    inc = pd.read_csv(DATA / "incendios_7d.csv", index_col=0, parse_dates=["inicio", "fin"])
    inc.index.name = "incendio_id"

    por_dep = (focos.groupby("NOMBDEP")
                    .agg(focos=("latitude", "size"), frp=("frp", "sum"),
                         incendios=("incendio_id", "nunique"))
                    .sort_values("focos", ascending=False))
    grandes = inc[inc.focos >= 10].groupby("departamento").size()
    por_dep["incendios_10_focos"] = grandes.reindex(por_dep.index, fill_value=0)
    por_dia = focos.groupby("acq_date").size()
    por_dep.to_csv(OUT / "focos_por_departamento.csv")

    # Mapa estático
    dep_m = dep.merge(por_dep, left_on="NOMBDEP", right_index=True, how="left").fillna({"focos": 0})
    g = gpd.GeoDataFrame(inc, geometry=gpd.points_from_xy(inc.lon, inc.lat), crs=4326)
    fig, ax = plt.subplots(figsize=(8.5, 11), constrained_layout=True)
    dep_m.plot(ax=ax, column="focos", cmap="YlOrBr", vmin=0, vmax=por_dep.focos.max() * 1.6,
               edgecolor="#5b6460", linewidth=0.5, legend=True,
               legend_kwds={"label": "Focos VIIRS por departamento", "shrink": 0.45})
    g.plot(ax=ax, markersize=(g.focos ** 0.5) * 9, color="#3b0d06", alpha=0.7, edgecolor="white", linewidth=0.3)
    if a.id in inc.index:
        e = inc.loc[a.id]
        ax.scatter(e.lon, e.lat, s=320, facecolor="none", edgecolor="#1f5fa8", linewidth=2.2, zorder=5)
        ax.annotate(f"{e.distrito.title()} ({e.departamento.title()})\n{int(e.focos)} focos · id {a.id}",
                    (e.lon, e.lat), xytext=(-78.6, -16.6), fontsize=9, color="#1f5fa8",
                    arrowprops=dict(arrowstyle="-", color="#1f5fa8", lw=1))
    for _, r in dep.iterrows():
        p = r.geometry.representative_point()
        ax.text(p.x, p.y, r.NOMBDEP.title(), fontsize=6, ha="center", color="#33403a", alpha=0.8)
    ax.set_axis_off()
    ax.set_title(f"Perú · focos de calor VIIRS S-NPP del {focos.acq_date.min()} al {focos.acq_date.max()}\n"
                 f"{len(focos):,} focos en {len(inc):,} incendios (círculos: tamaño = focos)",
                 fontsize=11)
    fig.savefig(OUT / "mapa_nacional.png", dpi=150)
    plt.close(fig)

    top = inc.sort_values(["focos", "frp_total"], ascending=False).head(15)
    nacional = dict(
        periodo=[focos.acq_date.min(), focos.acq_date.max()],
        focos=int(len(focos)), incendios=int(len(inc)),
        incendios_10_focos=int((inc.focos >= 10).sum()),
        departamentos_con_focos=int(por_dep.shape[0]),
        por_dia={k: int(v) for k, v in por_dia.items()},
        por_departamento=[dict(departamento=k, focos=int(r.focos), incendios=int(r.incendios),
                               incendios_10_focos=int(r.incendios_10_focos), frp=round(float(r.frp), 1))
                          for k, r in por_dep.iterrows()],
        top_incendios=[dict(id=int(k), focos=int(r.focos), frp=round(float(r.frp_total), 1),
                            distrito=r.distrito, provincia=r.provincia, departamento=r.departamento,
                            inicio=f"{r.inicio:%Y-%m-%d}", fin=f"{r.fin:%Y-%m-%d}",
                            lat=round(r.lat, 4), lon=round(r.lon, 4))
                       for k, r in top.iterrows()],
        incendio_estudiado=a.id,
    )
    (OUT / "nacional.json").write_text(json.dumps(nacional, ensure_ascii=False, indent=2))

    print(f"{len(focos):,} focos · {len(inc):,} incendios · "
          f"{nacional['incendios_10_focos']} con 10 focos o más")
    print(por_dep.head(10).to_string())
    print("\nGuardado: outputs/mapa_nacional.png, outputs/nacional.json, outputs/focos_por_departamento.csv")


if __name__ == "__main__":
    main()
