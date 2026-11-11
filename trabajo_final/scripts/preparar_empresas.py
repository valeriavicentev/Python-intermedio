"""Arma la base del buscador: una fila por empresa minera y sus registros en cada fuente.

    python scripts/preparar_empresas.py

Requiere haber corrido antes scripts/preparar_datos.py (unidades y distritos).

Fuentes que cruza (todas en data/raw/):
- MINEM: unidades mineras en producción (titular, distrito, coordenadas).
- OEFA: resoluciones con multa firme 2019-2025 (sector minería).
- OEFA: Registro Único de Infractores Ambientales Sancionados, si está en data/raw/oefa/oefa_ruias.csv.
- ProInversión: obras por impuestos adjudicadas y concluidas 2009-2025, y ranking de empresas con RUC.
- Defensoría del Pueblo: reportes de conflictos sociales, si hay archivos en data/raw/defensoria/.

Sin RUC común, el cruce es por nombre normalizado (radar/empresas.py). Cada
coincidencia queda registrada en empresa_alias.csv con su tipo: exacta o aproximada.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from radar.empresas import clave, emparejar, es_estado, es_minera, sin_tildes, slug  # noqa: E402

RAW = RAIZ / "data" / "raw"
PROC = RAIZ / "data" / "processed"


# ---------- utilidades ----------
def lugar(dep, prov, dist) -> str:
    return "|".join(sin_tildes(str(x)).upper().strip() for x in (dep, prov, dist))


def soles(v) -> float | None:
    """El CSV del OEFA mezcla dos formatos:
    'S/.1.070.000,00' (punto de miles, coma decimal) y '30256.25' (punto decimal)."""
    if pd.isna(v) or not str(v).strip():
        return None
    t = str(v).strip()
    if t.startswith("S/"):
        t = re.sub(r"[^\d,]", "", t).replace(",", ".")
    else:
        t = re.sub(r"[^\d.]", "", t)
    try:
        return round(float(t), 2)
    except ValueError:
        return None


class Universo:
    """Registro de empresas: clave normalizada -> datos y alias."""

    def __init__(self):
        self.empresas: dict[str, dict] = {}
        self.alias: list[dict] = []

    def agregar(self, fuente: str, nombres: list[str], ruc: dict[str, str] | None = None, crear: bool = True) -> dict[str, str]:
        """Devuelve {nombre_original: clave_universo} para los nombres que entran."""
        claves = {n: clave(n) for n in nombres if isinstance(n, str) and clave(n)}
        pares = emparejar(sorted(set(claves.values())), list(self.empresas))
        por_ruc = {d["ruc"]: k for k, d in self.empresas.items() if d.get("ruc")}
        salida = {}
        for nombre, c in claves.items():
            r = (ruc or {}).get(nombre)
            if r and r in por_ruc:
                destino, tipo = por_ruc[r], "ruc"
            elif c in pares:
                destino, tipo = pares[c]
            elif crear:
                destino, tipo = c, "nueva"
                self.empresas[c] = {"nombre": nombre.strip(), "ruc": None}
            else:
                continue
            if tipo != "ruc" and destino not in self.empresas:
                continue
            if ruc and ruc.get(nombre) and not self.empresas[destino]["ruc"]:
                self.empresas[destino]["ruc"] = str(ruc[nombre])
            self.alias.append({"clave": destino, "fuente": fuente, "nombre_en_fuente": nombre.strip(),
                               "coincidencia": {"nueva": "exacta", "ruc": "por RUC"}.get(tipo, tipo)})
            salida[nombre] = destino
        return salida


def main() -> None:
    U = Universo()
    import geopandas as gpd

    distritos = gpd.read_file(PROC / "distritos.geojson").drop(columns="geometry")
    distritos["lugar"] = [lugar(*r) for r in distritos[["NOMBDEP", "NOMBPROV", "NOMBDIST"]].values]
    pobreza_por_lugar = distritos.set_index("lugar")[["IDDIST", "pobreza"]]

    # 1) MINEM: unidades mineras
    unidades = pd.read_csv(PROC / "unidades.csv", dtype={"IDDIST": str, "IDDIST_geo": str})
    mapa = U.agregar("MINEM unidades mineras", unidades["titular"].unique().tolist())
    unidades["clave"] = unidades["titular"].map(mapa)
    unidades = unidades.merge(distritos[["IDDIST", "pobreza"]], on="IDDIST", how="left")

    # 2) ProInversión: ranking (trae RUC)
    rk = pd.read_excel(RAW / "oxi" / "oxi_ranking_empresas.xlsx", header=None).iloc[5:, [1, 2, 20]]
    rk.columns = ["empresa", "ruc", "oxi_total_mill"]
    rk = rk.dropna(subset=["empresa"])
    rk = rk[rk["empresa"].map(es_minera)]
    rk["ruc"] = rk["ruc"].astype("Int64").astype(str)
    mapa = U.agregar("ProInversión ranking OxI", rk["empresa"].tolist(), ruc=dict(zip(rk["empresa"], rk["ruc"])))
    rk["clave"] = rk["empresa"].map(mapa)

    # 3) ProInversión: obras adjudicadas y concluidas (consorcios separados por ";")
    oxi = pd.read_excel(RAW / "oxi" / "oxi_adjudicados_concluidos.xlsx", header=4).dropna(subset=["EMPRESAS"])
    oxi["empresas_lista"] = oxi["EMPRESAS"].str.split(";").map(lambda xs: [x.strip() for x in xs if x.strip()])
    oxi["n_empresas"] = oxi["empresas_lista"].str.len()
    filas = oxi.explode("empresas_lista").rename(columns={"empresas_lista": "empresa"})
    filas = filas[filas["empresa"].map(es_minera)]
    mapa = U.agregar("ProInversión obras OxI", filas["empresa"].unique().tolist())
    filas["clave"] = filas["empresa"].map(mapa)
    filas["lugar"] = [lugar(*r) for r in filas[["DEPARTAMENTO", "PROVINCIA", "DISTRITO"]].values]
    filas = filas.join(pobreza_por_lugar, on="lugar")
    oxi_out = filas.rename(columns={
        "NOMBRE DE LA INVERSIÓN": "obra", "FUNCIÓN": "funcion", "ESTADO": "estado",
        "AÑO DE BUENA PRO": "anio", "MONTO DE INVERSIÓN (MILLONES S/)": "monto_mill",
        "ENTIDAD PÚBLICA": "entidad", "DEPARTAMENTO": "departamento", "PROVINCIA": "provincia",
        "DISTRITO": "distrito", "CÓDIGO ÚNICO DE INVERSIONES (CUI)": "cui", "EMPRESAS": "financistas",
    })[["clave", "empresa", "obra", "funcion", "estado", "anio", "monto_mill", "entidad", "departamento",
        "provincia", "distrito", "IDDIST", "pobreza", "cui", "n_empresas", "financistas"]]

    # 4) OEFA: multas firmes (solo sector minería)
    mf = pd.read_csv(RAW / "oefa" / "multas_firmes_2019_2025.csv")
    mf = mf[sin_tildes_col(mf["SECTOR"]).str.contains("MINERIA") & ~mf["ADMINISTRADO"].map(es_estado)].copy()
    mapa = U.agregar("OEFA multas firmes", mf["ADMINISTRADO"].unique().tolist())
    mf["clave"] = mf["ADMINISTRADO"].map(mapa)
    # La columna UIT trae errores (filas con 5150, que es el valor de la UIT): se usa solo soles
    mf["multa_soles"] = mf["MULTA (SOLES)"].map(soles)
    mf["lugar"] = [lugar(*r) for r in mf[["DEPARTAMENTO", "PROVINCIA", "DISTRITO"]].values]
    mf = mf.join(pobreza_por_lugar, on="lugar")
    multas_out = mf.rename(columns={
        "ADMINISTRADO": "empresa", "AÑO": "anio", "UNIDAD AMBIENTAL": "unidad", "DEPARTAMENTO": "departamento",
        "PROVINCIA": "provincia", "DISTRITO": "distrito", "TIPO DE INFRACCION": "infraccion",
        "EXPEDIENTE": "expediente", "RESOLUCION DE PRIMERA INSTANCIA": "resolucion",
        "FECHA DE EMISION DE LA RESOLUCION DE PRIMERA INSTANCIA": "fecha_resolucion",
    })[["clave", "empresa", "anio", "unidad", "departamento", "provincia", "distrito", "IDDIST", "pobreza",
        "infraccion", "expediente", "resolucion", "fecha_resolucion", "multa_soles"]]

    # 5) OEFA RUIAS (opcional)
    ruias_out = cargar_ruias(U)

    # 6) MINEM: producción por empresa e inversión (Anuario Minero 2025); transferencias por departamento
    prod_out = cargar_produccion(U)
    inv_out = cargar_inversion(U)
    guardar_transferencias()
    guardar_exportaciones()

    # 7) Defensoría (opcional): menciones de cada empresa en los reportes
    conflictos_out = cargar_defensoria(U)

    # ---------- tabla de empresas ----------
    # Nombre a mostrar: entre los alias cuyo nombre normalizado es la clave final (no un nombre
    # antiguo como «Alpayana»), el más corto y sin notas entre paréntesis.
    al = pd.DataFrame(U.alias)
    al["propio"] = al["nombre_en_fuente"].map(lambda n: clave(n, renombrar=False)) == al["clave"]
    n = al["nombre_en_fuente"]
    al["largo"] = (
        n.str.len()
        + n.str.contains(r"\(| - ").astype(int) * 500                       # notas o nombres dobles
        + n.str.contains(r"\bCIA\b|\bEMP\.", case=False).astype(int) * 300   # abreviaturas
        + n.str.contains(r"\bS A\b|\bS A A\b|\bS A C\b").astype(int) * 300  # forma societaria sin puntos
        + (n.str.upper() != n).astype(int) * 100                            # minúsculas mezcladas
        + n.str.contains(r"COMPANIA", case=False).astype(int) * 200         # «COMPANIA» sin eñe
        + (n.str.contains(r"S\.A|S\.R\.L|S\.A\.C") & ~n.str.strip().str.endswith(".")).astype(int) * 50
    )
    mejor = al.sort_values(["propio", "largo"], ascending=[False, True]).drop_duplicates("clave")
    for c, n in zip(mejor["clave"], mejor["nombre_en_fuente"]):
        U.empresas[c]["nombre"] = n
    emp = pd.DataFrame([{"clave": c, **d} for c, d in U.empresas.items()])
    emp["empresa_id"] = emp["nombre"].map(slug)
    dup = emp["empresa_id"].duplicated(keep=False)
    emp.loc[dup, "empresa_id"] = emp.loc[dup, "empresa_id"] + "-" + emp.index[dup].astype(str)

    def agg(df, **kw):
        return df.groupby("clave").agg(**kw) if len(df) else pd.DataFrame(columns=list(kw))

    resumen = (
        emp.set_index("clave")
        .join(agg(unidades, n_unidades=("id_unidad", "count"), n_distritos=("IDDIST", "nunique"),
                  pobreza_media=("pobreza", "mean"), n_por_verificar=("punto_coincide", lambda s: int((~s).sum()))))
        .join(agg(multas_out, n_multas=("expediente", "count"), multas_soles=("multa_soles", "sum")))
        .join(agg(oxi_out, n_obras_oxi=("obra", "count"), oxi_monto_obras_mill=("monto_mill", "sum")))
        .join(rk.groupby("clave")["oxi_total_mill"].sum().rename("oxi_ranking_mill"))
    )
    if ruias_out is not None:
        resumen = resumen.join(agg(ruias_out, n_expedientes_ruias=("expediente", "count"),
                                      ruias_uit=("multa_uit", "sum")))
    if conflictos_out is not None:
        resumen = resumen.join(agg(conflictos_out, n_reportes_conflicto=("reporte", "nunique")))
    if prod_out is not None:
        p25 = prod_out[prod_out["anio"] == 2025]
        resumen = resumen.join(p25.groupby("clave")["metal"].apply(lambda m: ", ".join(sorted(set(m)))).rename("metales_2025"))
        resumen = resumen.join(p25.groupby("clave")["participacion"].max().rename("mayor_participacion_2025"))
    if inv_out is not None:
        resumen = resumen.join(inv_out.groupby("clave")[["inversion_2024_usd", "inversion_2025_usd"]].sum())
    resumen = resumen.reset_index()
    for c in resumen.columns:
        if c.startswith("n_"):
            resumen[c] = resumen[c].fillna(0).astype(int)
    ids = dict(zip(resumen["clave"], resumen["empresa_id"]))

    # Guardar (todas las tablas llevan empresa_id)
    def con_id(df):
        return df.assign(empresa_id=df["clave"].map(ids)).drop(columns="clave")

    resumen["ruc"] = resumen["ruc"].astype("string")
    resumen.drop(columns="clave").sort_values("nombre").to_csv(PROC / "empresas.csv", index=False)
    con_id(unidades).to_csv(PROC / "empresa_unidades.csv", index=False)
    con_id(multas_out).to_csv(PROC / "empresa_multas.csv", index=False)
    con_id(oxi_out).to_csv(PROC / "empresa_oxi.csv", index=False)
    con_id(pd.DataFrame(U.alias)).to_csv(PROC / "empresa_alias.csv", index=False)
    if ruias_out is not None:
        con_id(ruias_out).to_csv(PROC / "empresa_ruias.csv", index=False)
    if conflictos_out is not None:
        con_id(conflictos_out).to_csv(PROC / "empresa_conflictos.csv", index=False)
    if prod_out is not None:
        con_id(prod_out).to_csv(PROC / "empresa_produccion.csv", index=False)
    if RUIAS_FILAS is not None:
        con_minem = set(unidades["clave"])
        geo = gpd.read_file(PROC / "distritos.geojson")
        uo = ubicar_unidades_oefa(RUIAS_FILAS[~RUIAS_FILAS["clave"].isin(con_minem)], geo)
        # Multas firmes: traen unidad y distrito
        ya = con_minem | set(uo["clave"])
        mfu = multas_out[~multas_out["clave"].isin(ya)].rename(columns={"empresa": "empresa"})
        uo = pd.concat([uo, ubicar_por_lugar(mfu, geo, "OEFA, resoluciones con multa firme")], ignore_index=True)
        # Ubicaciones buscadas a mano en fuentes públicas (data/raw/manual/)
        man_ruta = RAW / "manual" / "ubicaciones_manuales.csv"
        if man_ruta.exists():
            man = pd.read_csv(man_ruta)
            mapa_man = U.agregar("Ubicación buscada en fuentes públicas", man["empresa"].unique().tolist(), crear=False)
            man["clave"] = man["empresa"].map(mapa_man)
            faltan = man[man["clave"].isna()]
            if len(faltan):
                print("  manual sin empresa en el escáner:", faltan["empresa"].tolist())
            ya = con_minem | set(uo["clave"])
            uo = pd.concat([uo, ubicar_por_lugar(man[man["clave"].notna() & ~man["clave"].isin(ya)], geo, "manual")],
                           ignore_index=True)
        con_id(uo).to_csv(PROC / "empresa_unidades_oefa.csv", index=False)
        print(f"Unidades OEFA (ubicación aproximada): {len(uo)} de {uo['clave'].nunique()} empresas sin unidades del MINEM.")

    aprox = sum(a["coincidencia"] == "aproximada" for a in U.alias)
    print(f"Empresas: {len(resumen)} | alias: {len(U.alias)} ({aprox} aproximados)")
    print(f"Con unidades: {(resumen.n_unidades > 0).sum()} | con multas: {(resumen.n_multas > 0).sum()} | "
          f"con obras OxI: {(resumen.n_obras_oxi > 0).sum()}")


def sin_tildes_col(s: pd.Series) -> pd.Series:
    return s.fillna("").map(sin_tildes).str.upper()


ANUARIO = RAW / "minem" / "anuario_minero_2025_anexos.xlsx"
RUIAS_FILAS: pd.DataFrame | None = None
DEPARTAMENTOS = {
    "AMAZONAS", "ANCASH", "APURIMAC", "AREQUIPA", "AYACUCHO", "CAJAMARCA", "CALLAO", "CUSCO", "HUANCAVELICA",
    "HUANUCO", "ICA", "JUNIN", "LA LIBERTAD", "LAMBAYEQUE", "LIMA", "LORETO", "MADRE DE DIOS", "MOQUEGUA",
    "PASCO", "PIURA", "PUNO", "SAN MARTIN", "TACNA", "TUMBES", "UCAYALI",
}

# Hoja del anuario -> (metal, unidad)
HOJAS_PRODUCCION = {
    "Cu-Empresas": ("cobre", "TMF"), "Au-Empresas": ("oro", "gramos finos"),
    "Zn-Empresas": ("zinc", "TMF"), "Ag-Empresas": ("plata", "kg finos"),
    "Pb-Empresas": ("plomo", "TMF"), "Mo-Empresas": ("molibdeno", "TMF"),
    "Fe-Producción": ("hierro", "TMF"), "Sn-Producción": ("estaño", "TMF"),
}


def sin_nota(nombre: str) -> str:
    """'MINERA LAS BAMBAS S.A.4' -> 'MINERA LAS BAMBAS S.A.' ; 'MARCOBRE S.A.C.8, 2' -> 'MARCOBRE S.A.C.'"""
    return re.sub(r"(?<=[.A-Za-zÁÉÍÓÚÑ)])\s*\d+(\s*,\s*\d+)*\s*$", "", str(nombre)).strip()


def _anios(fila) -> dict[int, int]:
    """Columna -> año, leyendo la fila de encabezado (incluye '2025 1' con nota)."""
    out = {}
    for i, v in enumerate(fila):
        m = re.match(r"^\s*(20\d\d)", str(v))
        if m and i > 0:
            out[i] = int(m.group(1))
    return out


def cargar_produccion(U: Universo) -> pd.DataFrame | None:
    """Producción por empresa y metal (MINEM, Anuario Minero 2025), con su participación nacional."""
    if not ANUARIO.exists():
        print("Anuario Minero: no está (data/raw/minem/). Se omite.")
        return None
    filas = []
    for hoja, (metal, unidad) in HOJAS_PRODUCCION.items():
        df = pd.read_excel(ANUARIO, sheet_name=hoja, header=None)
        enc = df.index[df[0].astype(str).str.startswith("EMPRESA")][0]
        cols = _anios(df.loc[enc])
        total = None
        for _, r in df.loc[enc + 1:].iterrows():
            nombre = r[0]
            if not isinstance(nombre, str) or not nombre.strip():
                continue
            if re.match(r"^(\d/|FUENTE|Fuente|OTROS|ESTIMADO)", nombre.strip()):
                continue
            if sin_tildes(nombre).upper().strip() in DEPARTAMENTOS:  # filas regionales de minería artesanal
                continue
            valores = {a: pd.to_numeric(r[c], errors="coerce") for c, a in cols.items()}
            if nombre.upper().startswith("TOTAL"):
                total = valores
                continue
            for a, v in valores.items():
                if a >= 2024 and pd.notna(v) and v > 0:
                    filas.append({"empresa": sin_nota(nombre), "metal": metal, "unidad": unidad, "anio": a,
                                  "cantidad": float(v), "participacion": float(v) / total[a] if total else None})
    prod = pd.DataFrame(filas)
    mapa = U.agregar("MINEM Anuario Minero (producción)", prod["empresa"].unique().tolist())
    prod["clave"] = prod["empresa"].map(mapa)
    print(f"Producción: {len(prod)} registros de {prod['clave'].nunique()} empresas.")
    return prod


def cargar_inversion(U: Universo) -> pd.DataFrame | None:
    if not ANUARIO.exists():
        return None
    df = pd.read_excel(ANUARIO, sheet_name="Inversión-Empresas", header=None)
    filas = []
    for _, r in df.iloc[4:].iterrows():
        nombre = r[1]
        if isinstance(nombre, str) and nombre.strip() and not nombre.upper().startswith(("TOTAL", "OTROS", "OTRAS")):
            filas.append({"empresa": sin_nota(nombre), "inversion_2024_usd": pd.to_numeric(r[2], errors="coerce"),
                          "inversion_2025_usd": pd.to_numeric(r[3], errors="coerce")})
    inv = pd.DataFrame(filas).dropna(subset=["inversion_2025_usd"])
    mapa = U.agregar("MINEM Anuario Minero (inversión)", inv["empresa"].tolist())
    inv["clave"] = inv["empresa"].map(mapa)
    return inv


def guardar_transferencias() -> None:
    """Canon minero, regalías y derecho de vigencia transferidos a cada departamento (MEF vía Anuario Minero)."""
    if not ANUARIO.exists():
        return
    df = pd.read_excel(ANUARIO, sheet_name="Tranferencias2", header=None)
    enc = df.index[df[0].astype(str).str.startswith("DEPARTAMENTOS")][0]
    cols = _anios(df.loc[enc])
    concepto, filas = None, []
    for _, r in df.loc[enc + 1:].iterrows():
        nombre = r[0]
        if not isinstance(nombre, str):
            continue
        n = sin_tildes(nombre).upper().strip()
        if n.startswith("CANON"):
            concepto = "canon minero"
        elif n.startswith("REGALIAS"):
            concepto = "regalías mineras"
        elif n.startswith("DERECHO"):
            concepto = "derecho de vigencia y penalidad"
        elif concepto and not re.match(r"^(\d/|DATOS|FUENTE)", n):
            for c, a in cols.items():
                filas.append({"departamento": n, "concepto": concepto, "anio": a,
                              "soles": pd.to_numeric(r[c], errors="coerce")})
    pd.DataFrame(filas).to_csv(PROC / "transferencias_departamento.csv", index=False)
    print(f"Transferencias: {len(filas)} registros departamento-concepto-año.")


def guardar_exportaciones() -> None:
    """Resumen de exportaciones mineras (Anuario Minero 2025): total, productos y destinos."""
    if not ANUARIO.exists():
        return
    import json

    tot = pd.read_excel(ANUARIO, sheet_name="Exportaciones", header=None)
    enc = tot.index[tot[0].astype(str).str.startswith("PRODUCTO")][0]
    cols = _anios(tot.loc[enc])
    c25 = next(c for c, a in cols.items() if a == 2025)
    c24 = next(c for c, a in cols.items() if a == 2024)
    fila = lambda nombre: tot.loc[tot[0].astype(str).str.strip().str.upper().str.startswith(nombre)].iloc[0]
    met, total = fila("MINERO METÁLICOS"), fila("TOTAL")

    em = pd.read_excel(ANUARIO, sheet_name="Export Min", header=None)
    enc = em.index[em[0].astype(str).str.startswith("PRODUCTO")][0]
    cols_m = _anios(em.loc[enc])
    k25 = next(c for c, a in cols_m.items() if a == 2025)
    productos = []
    for _, r in em.loc[enc + 1:].iterrows():
        n = str(r[0])
        if n.upper().startswith("TOTAL"):
            break
        if "/" in n and not n.upper().startswith("OTROS"):
            productos.append({"producto": n.split("/")[0].strip().capitalize(), "musd": float(r[k25])})
    productos.sort(key=lambda x: -x["musd"])

    de = pd.read_excel(ANUARIO, sheet_name="Destino export", header=None)
    destinos = [{"pais": str(r[0]).strip().title(), "musd": float(r[2]), "part": float(r[3])}
                for _, r in de.iloc[4:9].iterrows()]

    resumen = {
        "anio": 2025,
        "metalicas_musd": float(met[c25]), "metalicas_2024_musd": float(met[c24]),
        "total_pais_musd": float(total[c25]),
        "productos": productos, "destinos": destinos,
        "fuente": "MINEM, Anuario Minero 2025 (cifras de 2025 preliminares)",
    }
    (PROC / "exportaciones_2025.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"Exportaciones metálicas 2025: US$ {resumen['metalicas_musd']:,.0f} millones.")


def ubicar_unidades_oefa(r: pd.DataFrame, distritos) -> pd.DataFrame:
    """Unidades fiscalizadas por el OEFA (RUIAS) ubicadas en el centro de su distrito.

    Complementa la lista del MINEM, que no trae a muchas empresas. La ubicación es
    aproximada: el RUIAS da el distrito, no coordenadas.
    """
    import geopandas as gpd

    d = distritos.copy()
    d["lugar"] = [lugar(*x) for x in d[["NOMBDEP", "NOMBPROV", "NOMBDIST"]].values]
    centros = d.to_crs("EPSG:32718").geometry.centroid.to_crs("EPSG:4326")
    d["LATITUD"], d["LONGITUD"] = centros.y, centros.x
    d = d.set_index("lugar")

    u = r[(r["NOMBRE_UNIDAD_FISCALIZABLE"].fillna("-") != "-") & (r["DISTRITO"].fillna("-") != "-")]
    u = u.drop_duplicates(["clave", "NOMBRE_UNIDAD_FISCALIZABLE"])
    filas = []
    for _, x in u.iterrows():
        dists = [t.strip() for t in str(x["DISTRITO"]).split(",") if t.strip()]
        deps = [t.strip() for t in str(x["DEPARTAMENTO"]).split(",") if t.strip()]
        provs = [t.strip() for t in str(x["PROVINCIA"]).split(",") if t.strip()]
        # Si declara varios departamentos o provincias, se usa la primera combinación que existe
        candidatos = [lugar(dp, pv, ds) for ds in dists for dp in deps for pv in provs]
        lug = next((c for c in candidatos if c in d.index), None)
        if lug is None:
            continue
        g = d.loc[lug]
        dists = [lug.split("|")[2].title()] + [t for t in dists if sin_tildes(t).upper() != lug.split("|")[2]]
        filas.append({
            "clave": x["clave"], "unidad": str(x["NOMBRE_UNIDAD_FISCALIZABLE"]).upper(),
            "titular": x["NOMBRE_ADMINISTRADO"], "region": lug.split("|")[0],
            "provincia": lug.split("|")[1], "distrito": lug.split("|")[2],
            "distritos_oefa": ", ".join(dists), "IDDIST": g["IDDIST"], "pobreza": g["pobreza"],
            "LATITUD": g["LATITUD"], "LONGITUD": g["LONGITUD"],
            "fuente_ubicacion": "OEFA, Registro Único de Infractores Ambientales Sancionados", "fuente_url": "",
        })
    return pd.DataFrame(filas)


def ubicar_por_lugar(filas: pd.DataFrame, distritos, fuente: str) -> pd.DataFrame:
    """Ubica unidades con departamento, provincia y distrito (multas firmes o lista manual)."""
    d = distritos.copy()
    d["lugar"] = [lugar(*x) for x in d[["NOMBDEP", "NOMBPROV", "NOMBDIST"]].values]
    centros = d.to_crs("EPSG:32718").geometry.centroid.to_crs("EPSG:4326")
    d["LATITUD"], d["LONGITUD"] = centros.y, centros.x
    d = d.set_index("lugar")
    out = []
    for _, x in filas.iterrows():
        lug = lugar(x["departamento"], x["provincia"], x["distrito"])
        if lug not in d.index:
            print(f"  sin distrito en el mapa: {x['unidad']} ({lug})")
            continue
        g = d.loc[lug]
        out.append({
            "clave": x["clave"], "unidad": str(x["unidad"]).upper(), "titular": x["empresa"],
            "region": lug.split("|")[0], "provincia": lug.split("|")[1], "distrito": lug.split("|")[2],
            "distritos_oefa": None, "IDDIST": g["IDDIST"], "pobreza": g["pobreza"],
            "LATITUD": g["LATITUD"], "LONGITUD": g["LONGITUD"],
            "fuente_ubicacion": x.get("nota") if fuente == "manual" else fuente,
            "fuente_url": x.get("fuente_url", "") if isinstance(x.get("fuente_url"), str) else "",
        })
    return pd.DataFrame(out).drop_duplicates(["clave", "unidad"]) if out else pd.DataFrame()


def cargar_ruias(U: Universo) -> pd.DataFrame | None:
    """RUIAS: historial de sanciones, una fila por expediente.

    Montos en UIT según el diccionario de datos del OEFA. No son multas firmes:
    para el mismo expediente difieren de la tabla de multas firmes.
    """
    ruta = RAW / "oefa" / "oefa_ruias.csv"
    if not ruta.exists():
        print("RUIAS: no está (data/raw/oefa/oefa_ruias.csv). Se omite.")
        return None
    r = pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig", dtype=str)
    mineras_ruc = set(r.loc[r["SUBSECTOR_ECONOMICO"].fillna("").str.contains("Miner")
                            | r["NOMBRE_ADMINISTRADO"].fillna("").str.contains(r"MINER|MINING|MINAS", case=False),
                            "ID_DOC_ADMINISTRADO"])
    r = r[r["ID_DOC_ADMINISTRADO"].isin(mineras_ruc) & ~r["NOMBRE_ADMINISTRADO"].map(es_estado)].copy()
    nombres = r.drop_duplicates("ID_DOC_ADMINISTRADO")
    mapa = U.agregar("OEFA RUIAS", nombres["NOMBRE_ADMINISTRADO"].tolist(),
                     ruc=dict(zip(nombres["NOMBRE_ADMINISTRADO"], nombres["ID_DOC_ADMINISTRADO"])))
    r["clave"] = r["NOMBRE_ADMINISTRADO"].map(mapa)
    global RUIAS_FILAS
    RUIAS_FILAS = r.copy()
    r["uit"] = pd.to_numeric(r["MULTA_EXPEDIENTE"].str.replace(",", "."), errors="coerce")
    r["fecha"] = pd.to_datetime(r["FECHA_RD"], format="%Y%m%d", errors="coerce")
    exp = (
        r.groupby(["clave", "NRO_EXPEDIENTE"])
        .agg(
            empresa=("NOMBRE_ADMINISTRADO", "first"),
            unidad=("NOMBRE_UNIDAD_FISCALIZABLE", lambda s: next((x for x in s if x != "-"), "-")),
            departamento=("DEPARTAMENTO", lambda s: next((x for x in s if x != "-"), "-")),
            distrito=("DISTRITO", lambda s: next((x for x in s if x != "-"), "-")),
            fecha=("fecha", "min"),
            infracciones=("TIPO_INFRACCION", lambda s: "; ".join(sorted(set(x for x in s if x != "-")))),
            detalle=("DETALLE_INFRACCION", "first"),
            sancion=("TIPO_SANCION", lambda s: next((x for x in s if x != "-"), "Medida administrativa")),
            multa_uit=("uit", "max"),
        )
        .reset_index()
        .rename(columns={"NRO_EXPEDIENTE": "expediente"})
    )
    exp["anio"] = exp["fecha"].dt.year
    print(f"RUIAS: {len(exp)} expedientes de {exp['clave'].nunique()} empresas mineras.")
    return exp


URL_REPORTES = {
    270: "https://www.defensoria.gob.pe/wp-content/uploads/2026/09/Reporte-de-conflictos-sociales-n-270.pdf",
    269: "https://www.defensoria.gob.pe/wp-content/uploads/2026/08/Reporte-de-Conflictos-Sociales-n-269.pdf",
    268: "https://www.defensoria.gob.pe/wp-content/uploads/2026/07/Reporte-de-Conflictos-Sociales-n-268.pdf",
}

# Nombres cortos con los que la prensa y la Defensoría nombran a las grandes mineras
NOMBRES_CORTOS = {
    "ANTAMINA": "ANTAMINA", "SOUTHERN": "SOUTHERN PERU", "LAS BAMBAS": "LAS BAMBAS",
    "YANACOCHA": "YANACOCHA", "CERRO VERDE": "CERRO VERDE", "ANTAPACCAY": "ANTAPACCAY",
    "VOLCAN": "VOLCAN COMPANIA", "BUENAVENTURA": "BUENAVENTURA", "HUDBAY": "HUDBAY",
    "CHINALCO": "CHINALCO", "MINSUR": "MINSUR", "PODEROSA": "PODEROSA", "EL BROCAL": "EL BROCAL",
    "SHOUGANG": "SHOUGANG", "NEXA": "NEXA RESOURCES",
}


def cargar_defensoria(U: Universo) -> pd.DataFrame | None:
    """Busca el nombre de cada empresa del universo en el texto de los reportes."""
    carpeta = RAW / "defensoria"
    archivos = sorted(carpeta.glob("reporte_conflictos_*.*")) if carpeta.exists() else []
    if not archivos:
        print("Defensoría: no hay reportes en data/raw/defensoria/. Se omite.")
        return None
    filas = []
    for ruta in archivos:
        numero = int(re.search(r"(\d+)", ruta.stem).group(1))
        texto = texto_de(ruta)
        plano = re.sub(r"\s+", " ", sin_tildes(texto)).upper()
        # Cada nombre corto se asigna solo a la empresa con la clave más corta que lo contiene
        # ("NEXA RESOURCES" -> Nexa Resources Perú, no a todas sus filiales)
        dueno = {}
        for corto, marca in NOMBRES_CORTOS.items():
            candidatas = [c for c in U.empresas if marca in c]
            if candidatas:
                dueno[corto] = min(candidatas, key=len)
        for c in U.empresas:
            buscar = [c] if len(c) >= 12 and " " in c else []
            buscar += [corto for corto, d in dueno.items() if d == c]
            if not buscar:
                continue
            patron = r"\b(" + "|".join(re.escape(b) for b in buscar) + r")\b"
            ultimo = -10_000
            for m in re.finditer(patron, plano):
                if m.start() - ultimo < 1500:  # mismo caso: no repetir fragmentos superpuestos
                    continue
                ultimo = m.start()
                ini, fin = max(0, m.start() - 400), min(len(plano), m.end() + 400)
                filas.append({"clave": c, "reporte": numero, "archivo": ruta.name,
                              "url": URL_REPORTES.get(numero, "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/"),
                              "fragmento": plano[ini:fin]})
    df = pd.DataFrame(filas)
    if len(df):
        df = df.drop_duplicates(["clave", "reporte", "fragmento"])
    print(f"Defensoría: {len(archivos)} reportes, {len(df)} menciones.")
    return df


def texto_de(ruta: Path) -> str:
    if ruta.suffix.lower() == ".pdf":
        import pdfplumber

        with pdfplumber.open(ruta) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    html = ruta.read_text(encoding="utf-8", errors="ignore")
    return re.sub(r"<[^>]+>", " ", html)


if __name__ == "__main__":
    main()
