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
}


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
        )
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

        L += ["", f"[F1] {FUENTES['F1']} y [F2] {FUENTES['F2']}:"]
        L.append(f"- Unidades mineras registradas a su nombre: {len(self.unidades)}.")
        for _, u in self.unidades.iterrows():
            pob = "sin dato de pobreza" if pd.isna(u["pobreza"]) else f"pobreza distrital {u['pobreza']:.1f} %"
            nota = "" if u["punto_coincide"] else " (OJO: sus coordenadas caen en otro distrito; verificar)"
            L.append(f"  - {u['unidad']} en {str(u['distrito']).title()} ({str(u['region']).title()}), "
                     f"{str(u['metodo']).lower()}, {u['producto']}; {pob}{nota}.")

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

        if not self.conflictos.empty:
            L += ["", f"[F5] {FUENTES['F5']}:"]
            L.append(f"- Mencionada en {self.conflictos['reporte'].nunique()} reportes: "
                     + ", ".join(f"n.º {n}" for n in sorted(self.conflictos['reporte'].unique())) + ".")
            for frag in self.conflictos["fragmento"].head(3):
                L.append(f"  - «…{frag[:500]}…»")
        if not self.ruias.empty:
            L += ["", f"[F6] {FUENTES['F6']}:", f"- Registros de sanción: {len(self.ruias)}."]
        return "\n".join(L)
