"""Gráficos de pobreza monetaria (ENAHO 2024), siempre ponderados con facpob07.

    uv run .claude/skills/graficando-enaho/scripts/graficar.py --tipo area|sexo|departamento|mineria|todos
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path.cwd()
BASE = RAIZ / "salidas" / "personas_2024.parquet"
FIG = RAIZ / "figuras"
FUENTE = "Fuente: INEI, ENAHO 2024 (módulos 34 y 02; 05 para empleo minero). Estimaciones ponderadas con facpob07."
NOMBRES = {"01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho", "06": "Cajamarca",
           "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco", "11": "Ica", "12": "Junín",
           "13": "La Libertad", "14": "Lambayeque", "15": "Lima", "16": "Loreto", "17": "Madre de Dios",
           "18": "Moquegua", "19": "Pasco", "20": "Piura", "21": "Puno", "22": "San Martín", "23": "Tacna",
           "24": "Tumbes", "25": "Ucayali"}
AZUL, GRIS = "#1f4e79", "#9aa5b1"


def tasa(df, por):
    g = df.groupby(por, observed=True)
    out = g.apply(lambda d: pd.Series({"pobreza_pct": 100 * np.average(d.pobre, weights=d.facpob07),
                                       "n": len(d)}), include_groups=False)
    return out.reset_index()


def barras(t, etiqueta, titulo, archivo, horizontal=False, colores=None, nacional=None, nota=""):
    t = t.sort_values("pobreza_pct", ascending=horizontal)
    alto = max(4, 0.32 * len(t)) if horizontal else 4.5
    fig, ax = plt.subplots(figsize=(9, alto))
    c = colores if colores is not None else AZUL
    if horizontal:
        b = ax.barh(t[etiqueta], t.pobreza_pct, color=c)
        ax.set_xlim(0, t.pobreza_pct.max() * 1.15)
        ax.set_xlabel("% de personas en situación de pobreza monetaria")
        if nacional is not None:
            ax.axvline(nacional, color="#c0392b", ls="--", lw=1)
            ax.text(nacional, len(t) - 0.4, f" Nacional {nacional:.1f} %", color="#c0392b", fontsize=8, va="top")
    else:
        b = ax.bar(t[etiqueta], t.pobreza_pct, color=c, width=0.55)
        ax.set_ylim(0, t.pobreza_pct.max() * 1.2)
        ax.set_ylabel("% de personas en situación de pobreza monetaria")
    ax.bar_label(b, fmt="%.1f %%", padding=3, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(titulo, loc="left", fontsize=11)
    fig.text(0.01, 0.01, FUENTE + (" " + nota if nota else ""), fontsize=7, color="gray", wrap=True)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / archivo, dpi=200)
    plt.close(fig)
    print(f"  -> figuras/{archivo}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tipo", default="todos", choices=["area", "sexo", "departamento", "mineria", "todos"])
    a = p.parse_args()
    if not BASE.exists():
        raise SystemExit("ERROR: falta salidas/personas_2024.parquet. Corre primero la skill limpiando-enaho.")
    df = pd.read_parquet(BASE)
    nac = 100 * np.average(df.pobre, weights=df.facpob07)
    tipos = ["area", "sexo", "departamento", "mineria"] if a.tipo == "todos" else [a.tipo]

    if "area" in tipos:
        t = tasa(df, "area")
        print(t.round(2).to_string(index=False))
        brecha = t.set_index("area").pobreza_pct
        barras(t, "area", f"La pobreza rural supera a la urbana en {brecha['Rural'] - brecha['Urbana']:.1f} puntos "
                          f"(Perú, 2024)", "pobreza_area.png")
    if "sexo" in tipos:
        t = tasa(df, "sexo")
        print(t.round(2).to_string(index=False))
        barras(t, "sexo", "Pobreza monetaria por sexo, Perú 2024", "pobreza_sexo.png")
    if "departamento" in tipos:
        t = tasa(df, "ccdd").assign(departamento=lambda d: d.ccdd.map(NOMBRES))
        print(t.sort_values("pobreza_pct", ascending=False).round(2).to_string(index=False))
        top = t.loc[t.pobreza_pct.idxmax()]
        barras(t, "departamento", f"{top.departamento} encabeza la pobreza monetaria departamental con "
                                  f"{top.pobreza_pct:.1f} % (Perú, 2024)", "pobreza_departamento.png",
               horizontal=True, nacional=nac)
    if "mineria" in tipos:
        filas = []
        if df.distrito_minero.notna().any():
            for k, v in (("Distritos con unidad minera metálica", True), ("Resto de distritos", False)):
                d = df[df.distrito_minero == v]
                filas.append({"grupo": k, "pobreza_pct": 100 * np.average(d.pobre, weights=d.facpob07), "n": len(d)})
        if "hogar_minero" in df and df.hogar_minero.notna().any():
            for k, v in (("Hogares con trabajador minero", True), ("Hogares sin trabajador minero", False)):
                d = df[df.hogar_minero == v]
                filas.append({"grupo": k, "pobreza_pct": 100 * np.average(d.pobre, weights=d.facpob07), "n": len(d)})
        if not filas:
            raise SystemExit("ERROR: la base no tiene variables de minería (faltan unidades_mineras.csv y módulo 05).")
        t = pd.DataFrame(filas)
        print(t.round(2).to_string(index=False))
        t["grupo"] = t.grupo + "\n(n=" + t.n.map("{:,}".format) + ")"
        colores = [AZUL if ("con" in g.split("\n")[0] and "sin" not in g) else GRIS for g in t.sort_values(
            "pobreza_pct").grupo]
        barras(t, "grupo", "Pobreza monetaria en zonas y hogares mineros, Perú 2024", "pobreza_mineria.png",
               horizontal=True, colores=colores, nacional=nac,
               nota="n = personas encuestadas; la ENAHO no es representativa por distrito.")
    print(f"Pobreza nacional ponderada: {nac:.2f} %")


if __name__ == "__main__":
    main()
