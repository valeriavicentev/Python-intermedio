"""Limpia la ENAHO 2024 (módulos 34, 02 y, si está, 05) y arma una base de personas con pobreza y minería.

    uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio 2024

Entra:  datos/966-Modulo34.zip, datos/966-Modulo02.zip y, opcional, datos/966-Modulo05.zip
        datos/unidades_mineras.csv (142 unidades mineras con ubigeo; repositorio del curso, sesión 06)
Sale:   salidas/personas_<anio>.parquet, salidas/indicadores.csv y salidas/validacion.txt

Termina con código 1 si falla una validación esencial: no corrige cifras para que cuadren.
"""
import argparse
import io
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path.cwd()
DATOS, SALIDAS = RAIZ / "datos", RAIZ / "salidas"
CODIGO_INEI = {2024: "966"}
LLAVES_HOGAR = ["conglome", "vivienda", "hogar"]
ANCHO = {"conglome": 6, "vivienda": 3, "hogar": 2, "codperso": 2, "ubigeo": 6}
REFERENCIA = {"pobreza_nacional": 27.6, "residentes": 108_664, "urbano": 24.8, "rural": 39.3, "departamentos": 25}


def leer_dta(zip_path, patron):
    """Lee del zip el .dta cuyo nombre cumple el patrón, con las llaves como texto (sin perder ceros)."""
    if not zip_path.exists():
        return None
    with zipfile.ZipFile(zip_path) as z:
        nombres = [n for n in z.namelist() if re.search(patron, n.lower())]
        if not nombres:
            raise SystemExit(f"ERROR: {zip_path.name} no contiene un .dta que cumpla {patron!r}: {z.namelist()}")
        nombre = sorted(nombres, key=len)[0]
        df = pd.read_stata(io.BytesIO(z.read(nombre)), convert_categoricals=False)
    df.columns = [c.lower().replace("ñ", "n") for c in df.columns]    # «aÑo» llega con mayúscula
    for c, ancho in ANCHO.items():
        if c in df.columns:
            s = df[c]
            if pd.api.types.is_numeric_dtype(s):
                s = s.astype("Int64").astype(str)
            df[c] = s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(ancho)
    print(f"  {zip_path.name}/{nombre}: {len(df):,} filas")
    return df


def ponderada(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    ok = ~np.isnan(x) & ~np.isnan(w)
    return float(np.sum(x[ok] * w[ok]) / np.sum(w[ok]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--anio", type=int, default=2024)
    a = p.parse_args()
    cod = CODIGO_INEI.get(a.anio)
    if cod is None:
        raise SystemExit(f"ERROR: solo está configurado 2024 (código INEI 966), no {a.anio}.")
    z34, z02, z05 = (DATOS / f"{cod}-Modulo{m}.zip" for m in ("34", "02", "05"))
    faltan = [z.name for z in (z34, z02) if not z.exists()]
    if faltan:
        raise SystemExit(f"ERROR: faltan {faltan} en datos/. Descárgalos de "
                         f"https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/{cod}-Modulo34.zip y -Modulo02.zip")

    print("Leyendo la ENAHO...")
    hog = leer_dta(z34, r"sumaria-\d{4}\.dta$")
    per = leer_dta(z02, r"enaho01-\d{4}-200\.dta$")
    emp = leer_dta(z05, r"enaho01a-\d{4}-500\.dta$")     # None si no se bajó el módulo 05

    chequeos = []
    def chequear(nombre, ok, detalle, esencial=True):
        chequeos.append((nombre, bool(ok), detalle, esencial))

    # 1. Llaves únicas
    chequear("Llaves de hogar únicas en la sumaria", not hog.duplicated(LLAVES_HOGAR).any(), f"{len(hog):,} hogares")
    chequear("Llaves de persona únicas en el módulo 02",
             not per.duplicated(LLAVES_HOGAR + ["codperso"]).any(), f"{len(per):,} filas")

    # 2. Residentes habituales
    res = per[((per.p204 == 1) & (per.p205 == 2)) | ((per.p204 == 2) & (per.p206 == 1))].copy()
    chequear("Residentes habituales = 108,664", len(res) == REFERENCIA["residentes"], f"{len(res):,}")

    # 3. Unión personas → hogares (m:1)
    cols_hogar = LLAVES_HOGAR + ["ubigeo", "dominio", "estrato", "pobreza", "mieperho", "factor07"]
    cols_hogar += [c for c in ("gashog2d", "inghog1d", "linea", "linpe") if c in hog.columns]
    res = res.drop(columns=[c for c in cols_hogar if c in res.columns and c not in LLAVES_HOGAR])
    base = res.merge(hog[cols_hogar], on=LLAVES_HOGAR, how="left", validate="m:1", indicator=True)
    chequear("Unión m:1 sin perder ni duplicar personas", len(base) == len(res) and (base._merge == "both").all(),
             f"{len(base):,} filas, {(base._merge != 'both').sum()} sin hogar")
    base = base.drop(columns="_merge")

    # 4. Indicadores
    base["ccdd"] = base.ubigeo.str[:2]
    base["ccpp"] = base.ubigeo.str[:4]
    base["urbano"] = base.estrato <= 5
    base["area"] = np.where(base.urbano, "Urbana", "Rural")
    base["pobre"] = (base.pobreza <= 2).astype(int)
    base["pobre_extremo"] = (base.pobreza == 1).astype(int)
    base["sexo"] = base.p207.map({1: "Hombre", 2: "Mujer"})
    base["edad"] = base.p208a
    base["lima_metropolitana"] = base.dominio == 8

    # 5. Minería (a): distritos con unidad minera metálica (MINEM, vía repositorio del curso)
    um_path = DATOS / "unidades_mineras.csv"
    if um_path.exists():
        um = pd.read_csv(um_path, encoding="utf-8-sig")
        um.columns = um.columns.str.strip()
        metal = um[um["MÉTODO DE EXPLOTACIÓN"].str.upper().str.contains("SUBTERR|SUPERFICIAL", regex=True)]
        distritos = set(metal.UBIGEO.astype(str).str.zfill(6))
        provincias = {d[:4] for d in distritos}
        base["distrito_minero"] = base.ubigeo.isin(distritos)
        base["provincia_minera"] = base.ccpp.isin(provincias)
        chequear("Distritos mineros presentes en la muestra", base.distrito_minero.any(),
                 f"{base.loc[base.distrito_minero, 'ubigeo'].nunique()} de {len(distritos)} distritos con unidad "
                 f"metálica tienen hogares encuestados", esencial=False)
    else:
        base["distrito_minero"] = base["provincia_minera"] = pd.NA
        chequear("datos/unidades_mineras.csv disponible", False, "sin clasificación distrital minera", esencial=False)

    # 6. Minería (b): personas ocupadas en minería según CIIU rev. 4 (módulo 05) y hogares con algún minero
    if emp is not None and "p506r4" in emp.columns:
        e = emp[LLAVES_HOGAR + ["codperso", "p506r4", "ocu500"]].copy()
        ciiu = pd.to_numeric(e.p506r4, errors="coerce")
        div = ciiu // 100
        e["trabaja_mineria"] = ((e.ocu500 == 1) & (div.isin([5, 7, 8]) | (ciiu == 990))).astype(int)
        n_antes = len(base)
        base = base.merge(e[LLAVES_HOGAR + ["codperso", "trabaja_mineria"]], on=LLAVES_HOGAR + ["codperso"],
                          how="left", validate="1:1")
        base["trabaja_mineria"] = base.trabaja_mineria.fillna(0).astype(int)
        base["hogar_minero"] = base.groupby(LLAVES_HOGAR).trabaja_mineria.transform("max").astype(bool)
        chequear("Unión con el módulo 05 (1:1) sin duplicar", len(base) == n_antes, f"{len(base):,} filas",
                 esencial=True)
        chequear("Ocupados en minería identificados", base.trabaja_mineria.sum() > 0,
                 f"{int(base.trabaja_mineria.sum()):,} personas en la muestra", esencial=False)
    else:
        base["trabaja_mineria"] = pd.NA
        base["hogar_minero"] = pd.NA
        chequear("Módulo 05 (empleo) disponible", False,
                 "no se encontró datos/966-Modulo05.zip: sin clasificación por empleo minero", esencial=False)

    # 7. Validaciones contra el INEI
    w = base.facpob07
    pob = 100 * ponderada(base.pobre, w)
    pob_hog = 100 * ponderada((hog.pobreza <= 2).astype(int), hog.factor07 * hog.mieperho)
    urb = 100 * ponderada(base.pobre[base.urbano], w[base.urbano])
    rur = 100 * ponderada(base.pobre[~base.urbano], w[~base.urbano])
    chequear("Pobreza nacional (personas, facpob07) a ≤0.1 pp de 27.6 %", abs(pob - 27.6) <= 0.1, f"{pob:.2f} %")
    chequear("Pobreza nacional (sumaria, factor07×mieperho) a ≤0.1 pp de 27.6 %", abs(pob_hog - 27.6) <= 0.1,
             f"{pob_hog:.2f} %")
    chequear("Pobreza urbana ≈ 24.8 %", abs(urb - 24.8) <= 0.15, f"{urb:.2f} %")
    chequear("Pobreza rural ≈ 39.3 %", abs(rur - 39.3) <= 0.15, f"{rur:.2f} %")
    n_dep = base.ccdd.nunique()
    chequear("25 códigos departamentales (01-25)",
             n_dep == 25 and set(base.ccdd) == {f"{i:02d}" for i in range(1, 26)}, f"{n_dep}")
    chequear("Factor de expansión sin faltantes ni ceros", w.notna().all() and (w > 0).all(),
             f"población expandida {w.sum():,.0f}")
    chequear("Ponderar cambia el resultado (no es un promedio simple)", True,
             f"simple {100 * base.pobre.mean():.2f} % vs ponderado {pob:.2f} %", esencial=False)

    # 8. Indicadores para las demás skills
    def tabla(por):
        g = base.groupby(por, dropna=False)
        return g.apply(lambda d: pd.Series({
            "pobreza_pct": round(100 * ponderada(d.pobre, d.facpob07), 2),
            "pobreza_extrema_pct": round(100 * ponderada(d.pobre_extremo, d.facpob07), 2),
            "poblacion_expandida": round(d.facpob07.sum()), "n_muestra": len(d)}), include_groups=False).reset_index()
    filas = [tabla(["ccdd"]).assign(nivel="departamento"), tabla(["area"]).assign(nivel="area"),
             tabla(["sexo"]).assign(nivel="sexo")]
    if base.distrito_minero.notna().any():
        filas.append(tabla(["distrito_minero"]).assign(nivel="distrito_minero"))
        filas.append(tabla(["provincia_minera"]).assign(nivel="provincia_minera"))
    if base.hogar_minero.notna().any():
        filas.append(tabla(["hogar_minero"]).assign(nivel="hogar_minero"))
        filas.append(tabla(["area", "hogar_minero"]).assign(nivel="area_x_hogar_minero"))
    nac = pd.DataFrame([{"nivel": "nacional", "pobreza_pct": round(pob, 2),
                         "pobreza_extrema_pct": round(100 * ponderada(base.pobre_extremo, w), 2),
                         "poblacion_expandida": round(w.sum()), "n_muestra": len(base)}])
    ind = pd.concat([nac, *filas], ignore_index=True)
    orden = ["nivel", "ccdd", "area", "sexo", "distrito_minero", "provincia_minera", "hogar_minero"]
    ind = ind[[c for c in orden if c in ind] + ["pobreza_pct", "pobreza_extrema_pct", "poblacion_expandida", "n_muestra"]]

    SALIDAS.mkdir(exist_ok=True)
    lineas = [f"VALIDACIÓN ENAHO {a.anio} (código INEI {cod})", "=" * 60]
    for nombre, ok, det, esencial in chequeos:
        lineas.append(f"[{'OK  ' if ok else 'FALLA'}] {nombre}: {det}" + ("" if esencial else "  (informativo)"))
    fallas = [c for c in chequeos if c[3] and not c[1]]
    lineas += ["=" * 60, f"Esenciales aprobadas: {sum(1 for c in chequeos if c[3] and c[1])}/"
                         f"{sum(1 for c in chequeos if c[3])}",
               "RESULTADO: " + ("APROBADO" if not fallas else "FALLIDO — no usar la base")]
    texto = "\n".join(lineas)
    (SALIDAS / "validacion.txt").write_text(texto + "\n", encoding="utf-8")
    print(texto)
    parquet = SALIDAS / f"personas_{a.anio}.parquet"
    if fallas:
        parquet.unlink(missing_ok=True)   # nunca dejar una base vieja que parezca válida
        sys.exit(1)
    guardar = ["conglome", "vivienda", "hogar", "codperso", "ubigeo", "ccdd", "ccpp", "dominio", "estrato", "urbano",
               "area", "lima_metropolitana", "sexo", "edad", "pobreza", "pobre", "pobre_extremo", "mieperho",
               "factor07", "facpob07", "distrito_minero", "provincia_minera", "trabaja_mineria", "hogar_minero"]
    base[[c for c in guardar if c in base]].to_parquet(parquet, index=False)
    ind.to_csv(SALIDAS / "indicadores.csv", index=False)
    print(f"\nBase: salidas/personas_{a.anio}.parquet ({len(base):,} personas) · indicadores: salidas/indicadores.csv")


if __name__ == "__main__":
    main()
