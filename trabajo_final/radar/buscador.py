"""Búsqueda de empresas y armado de su perfil con todas las fuentes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from radar.empresas import clave, sin_tildes

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"

FUENTES = {
    "F1": "MINEM, unidades mineras en producción (dataset de la sesión 06 del curso)",
    "F2": "INEI, mapa de pobreza distrital (dataset de la sesión 06 del curso)",
    "F3": "OEFA, resoluciones con multa firme 2019-2025 (datos abiertos)",
    "F4": "ProInversión, inversiones adjudicadas y concluidas por Obras por Impuestos 2009-2025",
    "F5": "Defensoría del Pueblo, reportes de conflictos sociales",
    "F6": "OEFA, Registro Único de Infractores Ambientales Sancionados (RUIAS)",
    "F7": "MINEM, Anuario Minero 2025: producción e inversión por empresa (2025, datos preliminares)",
    "F8": "MEF vía Anuario Minero 2025: canon, regalías y derecho de vigencia transferidos a cada departamento",
}


# Símbolos químicos del registro del MINEM -> nombre en español
METALES = {
    "Cu": "cobre", "Au": "oro", "Ag": "plata", "Zn": "zinc", "Pb": "plomo", "Mo": "molibdeno",
    "Sn": "estaño", "Fe": "hierro", "As": "arsénico", "Bi": "bismuto", "Mn": "manganeso", "Cd": "cadmio",
}


def minerales(producto: str) -> list[str]:
    """'Cu, Mo, Au, Ag' -> ['cobre', 'molibdeno', 'oro', 'plata']; los no metálicos van en minúscula."""
    if not isinstance(producto, str):
        return []
    return [METALES.get(t.strip(), t.strip().lower()) for t in producto.replace(";", ",").split(",") if t.strip()]


def _leer(nombre: str, **kw) -> pd.DataFrame | None:
    ruta = PROC / nombre
    return pd.read_csv(ruta, **kw) if ruta.exists() else None


@dataclass
class Base:
    empresas: pd.DataFrame
    unidades: pd.DataFrame
    multas: pd.DataFrame
    oxi: pd.DataFrame
    alias: pd.DataFrame
    conflictos: pd.DataFrame | None = None
    ruias: pd.DataFrame | None = None
    produccion: pd.DataFrame | None = None
    transferencias: pd.DataFrame | None = None
    unidades_oefa: pd.DataFrame | None = None

    @classmethod
    def cargar(cls) -> "Base":
        tipos = {"ruc": str, "IDDIST": str, "IDDIST_geo": str}
        b = cls(
            empresas=_leer("empresas.csv", dtype=tipos),
            unidades=_leer("empresa_unidades.csv", dtype=tipos),
            multas=_leer("empresa_multas.csv", dtype=tipos),
            oxi=_leer("empresa_oxi.csv", dtype=tipos),
            alias=_leer("empresa_alias.csv"),
            conflictos=_leer("empresa_conflictos.csv"),
            ruias=_leer("empresa_ruias.csv", dtype=str),
            produccion=_leer("empresa_produccion.csv"),
            transferencias=_leer("transferencias_departamento.csv"),
            unidades_oefa=_leer("empresa_unidades_oefa.csv", dtype=tipos),
        )
        # SUNAT (Padrón Reducido del RUC): RUC faltante, estado y condición de domicilio
        sunat = _leer("empresa_sunat.csv", dtype={"ruc": str})
        if sunat is not None:
            sn = sunat.set_index("empresa_id")
            b.empresas["ruc"] = b.empresas["ruc"].fillna(b.empresas["empresa_id"].map(sn["ruc"]))
            b.empresas["estado_sunat"] = b.empresas["empresa_id"].map(sn["estado"])
            b.empresas["condicion_sunat"] = b.empresas["empresa_id"].map(sn["condicion"])
        else:
            b.empresas["estado_sunat"] = None
            b.empresas["condicion_sunat"] = None

        # Minerales que produce cada empresa, según sus unidades
        por_emp = b.unidades.groupby("empresa_id")["producto"].apply(
            lambda ps: sorted({m for p in ps for m in minerales(p)}, key=lambda m: (m not in METALES.values(), m))
        )
        b.empresas["minerales"] = b.empresas["empresa_id"].map(por_emp).apply(lambda x: x if isinstance(x, list) else [])
        if b.produccion is not None:  # suma los metales que declara en el Anuario Minero
            decl = b.produccion.groupby("empresa_id")["metal"].apply(set)
            b.empresas["minerales"] = [
                sorted(set(ms) | decl.get(i, set()), key=lambda m: (m not in METALES.values(), m))
                for i, ms in zip(b.empresas["empresa_id"], b.empresas["minerales"])
            ]
            top = (b.produccion[b.produccion["anio"] == 2025].sort_values("participacion", ascending=False)
                   .drop_duplicates("empresa_id").set_index("empresa_id"))
            b.empresas["metal_principal"] = b.empresas["empresa_id"].map(top["metal"])
            b.empresas["participacion_principal"] = b.empresas["empresa_id"].map(top["participacion"])

        # Texto de búsqueda: nombre + todos sus alias + RUC
        alias_txt = b.alias.groupby("empresa_id")["nombre_en_fuente"].apply(lambda s: " ".join(s))
        b.empresas["_buscar"] = (
            b.empresas["nombre"].fillna("") + " " + b.empresas["empresa_id"].map(alias_txt).fillna("")
        ).map(lambda t: sin_tildes(t).upper()) + " " + b.empresas["ruc"].fillna("")
        return b

    def buscar(self, consulta: str) -> pd.DataFrame:
        q = consulta.strip()
        if not q:
            return self.empresas.iloc[0:0]
        if q.isdigit():
            return self.empresas[self.empresas["ruc"].fillna("").str.startswith(q)]
        palabras = clave(q).split() or sin_tildes(q).upper().split()
        mascara = pd.Series(True, index=self.empresas.index)
        for p in palabras:
            mascara &= self.empresas["_buscar"].str.contains(p, regex=False)
        return self.empresas[mascara]

    def perfil(self, empresa_id: str) -> "Perfil":
        def de(df):
            if df is None:
                return pd.DataFrame()
            return df[df["empresa_id"] == empresa_id].copy()

        fila = self.empresas.loc[self.empresas["empresa_id"] == empresa_id].iloc[0]
        return Perfil(
            fila=fila,
            unidades=de(self.unidades),
            multas=de(self.multas),
            oxi=de(self.oxi),
            alias=de(self.alias),
            conflictos=de(self.conflictos),
            ruias=de(self.ruias),
            produccion=de(self.produccion),
            transferencias=self.transferencias,
            unidades_oefa=de(self.unidades_oefa),
        )


@dataclass
class Perfil:
    fila: pd.Series
    unidades: pd.DataFrame
    multas: pd.DataFrame
    oxi: pd.DataFrame
    alias: pd.DataFrame
    conflictos: pd.DataFrame = field(default_factory=pd.DataFrame)
    ruias: pd.DataFrame = field(default_factory=pd.DataFrame)
    produccion: pd.DataFrame = field(default_factory=pd.DataFrame)
    transferencias: pd.DataFrame | None = None
    unidades_oefa: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def ubicaciones(self) -> pd.DataFrame:
        """Unidades del MINEM (coordenadas exactas) o, si no hay, las del OEFA (centro del distrito)."""
        if not self.unidades.empty:
            return self.unidades.assign(aproximada=False)
        if not self.unidades_oefa.empty:
            return self.unidades_oefa.assign(aproximada=True, punto_coincide=True, producto="", metodo="")
        return pd.DataFrame()

    def transferencias_donde_opera(self, anio: int = 2025) -> pd.DataFrame:
        """Canon, regalías y derecho de vigencia de los departamentos donde tiene unidades."""
        ub = self.ubicaciones
        if self.transferencias is None or ub.empty:
            return pd.DataFrame()
        deps = {sin_tildes(d).upper() for d in ub["region"].dropna()}
        t = self.transferencias[(self.transferencias["anio"] == anio) & self.transferencias["departamento"].isin(deps)]
        return t.pivot_table(index="departamento", columns="concepto", values="soles", aggfunc="sum").reset_index()

    @property
    def nombre(self) -> str:
        return str(self.fila["nombre"])

    @property
    def distritos_operacion(self) -> set[str]:
        return set(self.unidades["IDDIST"].dropna())

    def obras_donde_opera(self) -> pd.DataFrame:
        return self.oxi[self.oxi["IDDIST"].isin(self.distritos_operacion)]

    def como_texto(self) -> str:
        """Contexto con fuentes etiquetadas: lo único que recibe la IA."""
        f = self.fila
        L = [f"EMPRESA: {self.nombre}" + (f", RUC {f['ruc']}" if isinstance(f["ruc"], str) else "") + "."]
        if isinstance(f.get("estado_sunat"), str):
            L.append(f"Estado ante la SUNAT (Padrón Reducido del RUC, noviembre 2026): {f['estado_sunat']}, "
                     f"domicilio {f['condicion_sunat']}.")

        L += ["", f"[F1] {FUENTES['F1']} y [F2] {FUENTES['F2']}:"]
        L.append(f"- Unidades mineras registradas a su nombre: {len(self.unidades)}.")
        if self.fila["minerales"]:
            L.append("- Minerales que producen sus unidades: " + ", ".join(self.fila["minerales"]) + ".")
        for _, u in self.unidades.iterrows():
            pob = "sin dato de pobreza" if pd.isna(u["pobreza"]) else f"pobreza distrital {u['pobreza']:.1f} %"
            nota = "" if u["punto_coincide"] else " (OJO: sus coordenadas caen en otro distrito; verificar)"
            L.append(f"  - {u['unidad']} en {str(u['distrito']).title()} ({str(u['region']).title()}), "
                     f"{str(u['metodo']).lower()}, {u['producto']}; {pob}{nota}.")

        if self.unidades.empty and not self.unidades_oefa.empty:
            L += ["", f"[F6] {FUENTES['F6']}, unidades fiscalizadas (ubicación por distrito, aproximada):"]
            for _, u in self.unidades_oefa.iterrows():
                pob = "sin dato de pobreza" if pd.isna(u["pobreza"]) else f"pobreza distrital {u['pobreza']:.1f} %"
                L.append(f"  - {u['unidad']} en {str(u['distrito']).title()}, {str(u['provincia']).title()} "
                         f"({str(u['region']).title()}); {pob}.")

        L += ["", f"[F3] {FUENTES['F3']}:"]
        if self.multas.empty:
            L.append("- Sin multas firmes registradas en este periodo.")
        else:
            L.append(f"- Multas firmes: {len(self.multas)}, por un total de S/ {self.multas['multa_soles'].sum():,.2f}.")
            for _, m in self.multas.sort_values("multa_soles", ascending=False).head(6).iterrows():
                L.append(f"  - {m['anio']}: {m['infraccion']} en la unidad {m['unidad']} "
                         f"({str(m['distrito']).title()}), S/ {m['multa_soles']:,.2f}.")

        L += ["", f"[F4] {FUENTES['F4']}:"]
        if self.oxi.empty:
            L.append("- Sin obras registradas por Obras por Impuestos.")
        else:
            L.append(f"- Obras en las que figura como financista: {len(self.oxi)}, "
                     f"con una inversión total de S/ {self.oxi['monto_mill'].sum():,.1f} millones "
                     "(monto total de cada obra; algunas se financiaron en consorcio).")
            por_funcion = self.oxi.groupby("funcion")["monto_mill"].sum().sort_values(ascending=False).head(4)
            L.append("- Principales funciones: " + "; ".join(f"{k.title()} S/ {v:,.1f} millones" for k, v in por_funcion.items()) + ".")
            dpto = self.oxi["departamento"].value_counts().head(4)
            L.append("- Departamentos con más obras: " + ", ".join(f"{k.title()} ({v})" for k, v in dpto.items()) + ".")
            donde = self.obras_donde_opera()
            L.append(f"- Obras en distritos donde tiene unidades mineras: {len(donde)}.")

        if not self.produccion.empty:
            L += ["", f"[F7] {FUENTES['F7']}:"]
            for _, r in self.produccion[self.produccion["anio"] == 2025].sort_values("participacion", ascending=False).iterrows():
                L.append(f"- {r['metal'].capitalize()} 2025: {r['cantidad']:,.0f} {r['unidad']}, "
                         f"{r['participacion'] * 100:.1f} % de la producción nacional.")
        if pd.notna(self.fila.get("inversion_2025_usd")):
            L.append(f"- Inversión minera 2025: US$ {self.fila['inversion_2025_usd']:,.0f}.")
        t = self.transferencias_donde_opera()
        if not t.empty:
            L += ["", f"[F8] {FUENTES['F8']} (montos de todo el departamento, no solo de esta empresa):"]
            for _, r in t.iterrows():
                L.append(f"- {r['departamento'].title()}, 2025: canon minero S/ {r.get('canon minero', 0):,.0f}; "
                         f"regalías S/ {r.get('regalías mineras', 0):,.0f}.")

        if not self.conflictos.empty:
            L += ["", f"[F5] {FUENTES['F5']}:"]
            L.append(f"- Mencionada en {self.conflictos['reporte'].nunique()} reportes: "
                     + ", ".join(f"n.º {n}" for n in sorted(self.conflictos['reporte'].unique())) + ".")
            for frag in self.conflictos["fragmento"].head(3):
                L.append(f"  - «…{frag[:500]}…»")
        if not self.ruias.empty:
            L += ["", f"[F6] {FUENTES['F6']}:", f"- Registros de sanción: {len(self.ruias)}."]
        return "\n".join(L)
