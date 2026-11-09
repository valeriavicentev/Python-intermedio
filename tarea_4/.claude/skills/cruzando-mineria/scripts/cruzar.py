"""Cruza producción minera (BCRP, vía MCP), canon minero (MEF, opcional) y pobreza (ENAHO 2024) por departamento.

    uv run .claude/skills/cruzando-mineria/scripts/cruzar.py --anio 2024 [--tc 3.75]

Entra:  salidas/produccion_minera_<anio>.csv   (lo escribe la herramienta MCP produccion_minera_departamental)
        salidas/personas_<anio>.parquet        (lo escribe la skill limpiando-enaho)
        datos/canon_minero_<anio>.csv          (opcional: ccdd,canon_minero_soles — exportado del MEF)
        --tc: tipo de cambio promedio del año (S/ por US$), obtenido con resumen(PD04638PD) del MCP
Sale:   salidas/cruce_mineria_<anio>.csv, salidas/pobreza_zonas_mineras_<anio>.csv, figuras/mineria_vs_pobreza.png
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path.cwd()
NOMBRES = {"01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho", "06": "Cajamarca",
           "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco", "11": "Ica", "12": "Junín",
           "13": "La Libertad", "14": "Lambayeque", "15": "Lima", "16": "Loreto", "17": "Madre de Dios",
           "18": "Moquegua", "19": "Pasco", "20": "Piura", "21": "Puno", "22": "San Martín", "23": "Tacna",
           "24": "Tumbes", "25": "Ucayali"}


def w(d, col="pobre"):
    return 100 * np.average(d[col], weights=d.facpob07)


def spearman(a, b):
    """Correlación de rangos (sin scipy)."""
    return a.rank().corr(b.rank())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--anio", type=int, default=2024)
    p.add_argument("--tc", type=float, default=None, help="S/ por US$, promedio del año (MCP: resumen PD04638PD)")
    a = p.parse_args()
    prod_path = RAIZ / "salidas" / f"produccion_minera_{a.anio}.csv"
    base_path = RAIZ / "salidas" / f"personas_{a.anio}.parquet"
    if not base_path.exists():
        raise SystemExit("ERROR: falta la base de la ENAHO. Corre primero la skill limpiando-enaho.")
    if not prod_path.exists():
        raise SystemExit(f"ERROR: falta {prod_path.name}. Llama a la herramienta MCP "
                         f"produccion_minera_departamental(anio={a.anio}, guardar=true).")
    df = pd.read_parquet(base_path)
    prod = pd.read_csv(prod_path, dtype={"ccdd": str})

    pob = df.groupby("ccdd").apply(lambda d: pd.Series({"pobreza_pct": w(d), "poblacion": d.facpob07.sum(),
                                                        "n_muestra": len(d)}), include_groups=False).reset_index()
    val = prod.groupby("ccdd", as_index=False).valor_musd.sum()
    metales = prod.pivot_table(index="ccdd", columns="metal", values="valor_musd", aggfunc="sum").add_prefix("musd_")
    t = pob.merge(val, on="ccdd", how="left").merge(metales, on="ccdd", how="left").fillna({"valor_musd": 0})
    t.insert(1, "departamento", t.ccdd.map(NOMBRES))
    t["valor_usd_per_capita"] = 1e6 * t.valor_musd / t.poblacion
    t["productor_minero"] = t.valor_musd > 0

    canon_path = RAIZ / "datos" / f"canon_minero_{a.anio}.csv"
    if canon_path.exists():
        c = pd.read_csv(canon_path, dtype={"ccdd": str})
        c["ccdd"] = c.ccdd.str.zfill(2)
        t = t.merge(c[["ccdd", "canon_minero_soles"]], on="ccdd", how="left", validate="1:1")
        t["canon_soles_per_capita"] = t.canon_minero_soles / t.poblacion
        if a.tc:
            t["canon_pct_valor_produccion"] = 100 * t.canon_minero_soles / (t.valor_musd * 1e6 * a.tc)
            t.loc[t.valor_musd == 0, "canon_pct_valor_produccion"] = np.nan
        print(f"Canon minero: {canon_path.name} ({t.canon_minero_soles.notna().sum()} departamentos con dato)")
    else:
        print(f"LIMITACIÓN: no está datos/{canon_path.name}; el cruce se hace sin canon departamental.")

    salida = RAIZ / "salidas" / f"cruce_mineria_{a.anio}.csv"
    t.sort_values("valor_musd", ascending=False).round(4).to_csv(salida, index=False)

    # Correlaciones descriptivas (25 observaciones: sin inferencia causal)
    prod_t = t[t.productor_minero]
    print(f"\nDepartamentos con producción minera metálica registrada por el BCRP: {len(prod_t)} de 25")
    print(f"Pobreza promedio (ponderada por población) en departamentos productores: "
          f"{np.average(prod_t.pobreza_pct, weights=prod_t.poblacion):.2f} %; no productores: "
          f"{np.average(t[~t.productor_minero].pobreza_pct, weights=t[~t.productor_minero].poblacion):.2f} %")
    corr = {"pearson_pobreza_vs_valor_pc": prod_t.pobreza_pct.corr(prod_t.valor_usd_per_capita),
            "spearman_pobreza_vs_valor_pc": spearman(prod_t.pobreza_pct, prod_t.valor_usd_per_capita)}
    if "canon_soles_per_capita" in t:
        cc = t.dropna(subset=["canon_soles_per_capita"])
        corr["spearman_pobreza_vs_canon_pc"] = spearman(cc.pobreza_pct, cc.canon_soles_per_capita)
    for k, v in corr.items():
        print(f"  {k}: {v:.3f}")

    cols = ["ccdd", "departamento", "valor_musd", "valor_usd_per_capita", "pobreza_pct", "n_muestra"]
    cols += [c for c in ("canon_minero_soles", "canon_soles_per_capita", "canon_pct_valor_produccion") if c in t]
    print("\nTop 10 por valor estimado de producción minera (millones de US$):")
    print(t.sort_values("valor_musd", ascending=False)[cols].head(10).round(1).to_string(index=False))

    # Dentro de cada departamento: distritos con unidad minera vs. resto (muestra pequeña: descriptivo)
    if df.distrito_minero.notna().any():
        filas = []
        for cd, d in df.groupby("ccdd"):
            si, no = d[d.distrito_minero == True], d[d.distrito_minero == False]  # noqa: E712
            if len(si) >= 30:
                filas.append({"ccdd": cd, "departamento": NOMBRES[cd], "pobreza_distritos_mineros": w(si),
                              "n_distritos_mineros": len(si), "pobreza_resto": w(no), "n_resto": len(no),
                              "diferencia_pp": w(si) - w(no)})
        z = pd.DataFrame(filas).sort_values("diferencia_pp")
        z.round(2).to_csv(RAIZ / "salidas" / f"pobreza_zonas_mineras_{a.anio}.csv", index=False)
        print("\nPobreza en distritos con unidad minera vs. resto del mismo departamento (≥30 personas en muestra):")
        print(z.round(1).to_string(index=False))
        tot_si = df[df.distrito_minero == True]  # noqa: E712
        print(f"Nacional: distritos con unidad minera {w(tot_si):.2f} % (n={len(tot_si):,}) vs. resto "
              f"{w(df[df.distrito_minero == False]):.2f} %")  # noqa: E712

    # Gráfico de dispersión
    fig, ax = plt.subplots(figsize=(9, 6))
    x = t.valor_usd_per_capita.clip(lower=1)
    ax.scatter(x, t.pobreza_pct, s=t.poblacion / 2e4, color="#1f4e79", alpha=0.6, edgecolor="white")
    for r in t.itertuples():
        ax.annotate(r.departamento, (max(r.valor_usd_per_capita, 1), r.pobreza_pct), fontsize=7,
                    xytext=(3, 3), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_xlabel("Valor estimado de la producción minera metálica por habitante (US$, escala log; 1 = sin producción)")
    ax.set_ylabel("Pobreza monetaria (% de personas)")
    ax.set_ylim(0, t.pobreza_pct.max() * 1.1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"Producción minera por habitante y pobreza monetaria por departamento ({a.anio})\n"
                 f"Spearman = {corr['spearman_pobreza_vs_valor_pc']:.2f} entre productores (n={len(prod_t)})",
                 loc="left", fontsize=11)
    fig.text(0.01, 0.01, "Fuente: BCRP, producción minera por departamento (series RD…DA) y precios de exportación "
                         "(PN387…BM); INEI, ENAHO 2024. Burbuja ∝ población. Asociación descriptiva, no causal.",
             fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    (RAIZ / "figuras").mkdir(exist_ok=True)
    fig.savefig(RAIZ / "figuras" / "mineria_vs_pobreza.png", dpi=200)
    print(f"\nTabla: {salida.relative_to(RAIZ)} · Figura: figuras/mineria_vs_pobreza.png")


if __name__ == "__main__":
    main()
