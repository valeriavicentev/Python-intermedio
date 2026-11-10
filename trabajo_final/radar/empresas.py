"""Normalización de nombres de empresas para cruzar fuentes sin RUC común.

Cada fuente escribe el mismo nombre de forma distinta:
    "CIA MINERA PODEROSA S A"  ==  "COMPAÑIA MINERA PODEROSA S.A."
    "SOUTHERN PERU COPPER CORPORATION SUCURSAL DEL PERU"  ==  "SOUTHERN PERU COPPER CORPORATION"
La clave normalizada quita tildes, puntuación, formas societarias y notas entre
paréntesis. Las coincidencias que no son exactas se marcan como aproximadas.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

FORMAS = [
    "SOCIEDAD ANONIMA ABIERTA", "SOCIEDAD ANONIMA CERRADA", "SOCIEDAD ANONIMA",
    "SUCURSAL DEL PERU", "SUCURSAL PERU", "EN LIQUIDACION EN MARCHA", "EN LIQUIDACION",
    "S A A", "S A C", "S R L", "E I R L", "S A", "SAA", "SAC", "SRL", "EIRL", "SA", "INC",
]
_FORMAS_RE = re.compile(r"\b(" + "|".join(re.escape(f) for f in FORMAS) + r")\b")

# Palabras que delatan actividad minera en fuentes que mezclan sectores (OxI)
MINERAS_RE = re.compile(
    r"MINER|MINING|MINAS|GOLD|COPPER|SOUTHERN PERU|HUDBAY|NEXA|CERRO VERDE|BAMBAS|"
    r"ANTAPACCAY|CHINALCO|VOLCAN|ARUNTANI|SHOUGANG|MINSUR|BUENAVENTURA|ANTAMINA|"
    r"YANACOCHA|PODEROSA|BROCAL|CHUNGAR|HORIZONTE|COIMOLACHE|LA ZANJA|SILVER|METAIS|NYRSTAR",
    re.IGNORECASE,
)


def sin_tildes(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def clave(nombre: str) -> str:
    """Clave de cruce: 'Compañía Minera Poderosa S.A.' -> 'COMPANIA MINERA PODEROSA'."""
    if not isinstance(nombre, str):
        return ""
    t = sin_tildes(nombre).upper()
    t = re.sub(r"\(.*?\)", " ", t)           # notas: "(Ex Compañía Minera Milpo)"
    t = re.sub(r"[.,;:&/\-]", " ", t)
    t = re.sub(r"\bCIA\b", "COMPANIA", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = _FORMAS_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


ESTADO_RE = re.compile(r"MINISTERIO|MUNICIPALIDAD|GOBIERNO REGIONAL|DIRECCION REGIONAL", re.IGNORECASE)


def es_estado(nombre: str) -> bool:
    return bool(ESTADO_RE.search(sin_tildes(str(nombre))))


def es_minera(nombre: str) -> bool:
    return bool(MINERAS_RE.search(sin_tildes(str(nombre)))) and not es_estado(nombre)


def emparejar(claves_fuente: list[str], universo: list[str], umbral: float = 0.93) -> dict[str, tuple[str, str]]:
    """Asigna cada clave de una fuente a una clave del universo.

    Devuelve {clave_fuente: (clave_universo, "exacta" | "aproximada")}.
    Las que no alcanzan el umbral quedan fuera.
    """
    universo_set = set(universo)
    resultado = {}
    for c in claves_fuente:
        if not c:
            continue
        if c in universo_set:
            resultado[c] = (c, "exacta")
            continue
        mejor, puntaje = None, 0.0
        for u in universo:
            p = SequenceMatcher(None, c, u).ratio()
            if p > puntaje:
                mejor, puntaje = u, p
        if mejor and puntaje >= umbral:
            resultado[c] = (mejor, "aproximada")
    return resultado


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes(texto).lower()).strip("-")[:60]
