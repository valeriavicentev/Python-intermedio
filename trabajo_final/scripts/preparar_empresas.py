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

    # 6) Defensoría (opcional): menciones de cada empresa en los reportes
    conflictos_out = cargar_defensoria(U)

    # ---------- tabla de empresas ----------
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

    aprox = sum(a["coincidencia"] == "aproximada" for a in U.alias)
    print(f"Empresas: {len(resumen)} | alias: {len(U.alias)} ({aprox} aproximados)")
    print(f"Con unidades: {(resumen.n_unidades > 0).sum()} | con multas: {(resumen.n_multas > 0).sum()} | "
          f"con obras OxI: {(resumen.n_obras_oxi > 0).sum()}")


def sin_tildes_col(s: pd.Series) -> pd.Series:
    return s.fillna("").map(sin_tildes).str.upper()


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
    mineras_ruc = set(r.loc[r["SUBSECTOR_ECONOMICO"].fillna("").str.contains("Miner"), "ID_DOC_ADMINISTRADO"])
    r = r[r["ID_DOC_ADMINISTRADO"].isin(mineras_ruc) & ~r["NOMBRE_ADMINISTRADO"].map(es_estado)].copy()
    nombres = r.drop_duplicates("ID_DOC_ADMINISTRADO")
    mapa = U.agregar("OEFA RUIAS", nombres["NOMBRE_ADMINISTRADO"].tolist(),
                     ruc=dict(zip(nombres["NOMBRE_ADMINISTRADO"], nombres["ID_DOC_ADMINISTRADO"])))
    r["clave"] = r["NOMBRE_ADMINISTRADO"].map(mapa)
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
