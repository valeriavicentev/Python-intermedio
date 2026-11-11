"""Ficha de pauta: de los datos de un distrito a una propuesta de reportaje.

El modelo (Gemini) recibe solo el contexto del distrito y devuelve una ficha
con un esquema fijo (salida estructurada con Pydantic). Después, una
verificación automática revisa que cada cifra de la ficha exista en el
contexto: si el modelo inventa un número, la app lo marca.
"""

from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field

from typing import Protocol


class Contexto(Protocol):
    def como_texto(self) -> str: ...

MODELO_POR_DEFECTO = "gemini-2.5-flash"


class DatoClave(BaseModel):
    dato: str = Field(description="Una afirmación factual tomada del contexto, con su cifra.")
    fuente: str = Field(description="Etiqueta de la fuente del contexto, por ejemplo F1 o F4.")


class FichaPauta(BaseModel):
    titular_tentativo: str = Field(description="Titular de trabajo, máximo 12 palabras, sin sensacionalismo.")
    pregunta_periodistica: str = Field(description="La pregunta que el reportaje intenta responder.")
    angulo: str = Field(description="Por qué esta historia importa, en 2 o 3 oraciones.")
    datos_clave: list[DatoClave] = Field(description="Entre 3 y 5 datos, todos tomados del contexto.")
    actores_a_consultar: list[str] = Field(description="Tipos de actores: comunidad, empresa, Estado, organizaciones. Sin inventar nombres de personas.")
    preguntas_para_entrevistas: list[str] = Field(description="Entre 4 y 6 preguntas abiertas para el trabajo de campo.")
    fuentes_publicas_a_revisar: list[str] = Field(description="Registros o instituciones públicas peruanas donde verificar o ampliar.")
    por_verificar: list[str] = Field(description="Lo que los datos no dicen y hay que confirmar antes de publicar.")
    riesgos_de_campo: list[str] = Field(description="Riesgos de seguridad o éticos para el equipo y las fuentes.")


INSTRUCCIONES = """Eres editora de Gallo Negro, un medio de periodismo narrativo audiovisual
que cuenta las consecuencias del extractivismo en América Latina desde el testimonio
de quienes las viven. Prepara una ficha de pauta para un mini documental de YouTube
sobre la empresa minera descrita en el CONTEXTO: dónde opera, sus sanciones
ambientales, las obras que financió por Obras por Impuestos y los conflictos donde
aparece.

Reglas:
- Usa SOLO cifras y hechos que aparecen en el CONTEXTO. No agregues cifras externas.
- Cada dato clave lleva la etiqueta de su fuente (F1, F2, F3, F4, F5 o F6).
- Los datos no prueban causalidad ni culpa: formula la pregunta como hipótesis a investigar.
- Las multas firmes (F3) y los expedientes del RUIAS (F6) son registros distintos: no los sumes.
- En Obras por Impuestos el monto es el total de cada obra, aunque haya sido en consorcio.
- Si una unidad tiene coordenadas que no coinciden con su distrito, inclúyelo en "por_verificar".
- No inventes nombres de personas, comunidades ni organizaciones.
- Escribe en español neutro, claro y sin adjetivos sensacionalistas.
"""


def _numeros(texto: str) -> set[str]:
    """Cifras normalizadas de un texto: '1,234.5' -> '1234.5', '36,5' -> '36.5'."""
    encontrados = re.findall(r"\d[\d.,]*", texto)
    normalizados = set()
    for n in encontrados:
        n = n.rstrip(".,")
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", n):
            n = n.replace(",", "")
        else:
            n = n.replace(",", ".")
        normalizados.add(n)
    return normalizados


def verificar(ficha: FichaPauta, ctx: Contexto) -> list[str]:
    """Devuelve las cifras de los datos clave que NO aparecen en el contexto."""
    en_contexto = _numeros(ctx.como_texto())
    sueltas = []
    for d in ficha.datos_clave:
        for n in _numeros(d.dato):
            if n not in en_contexto and n not in {"20"}:
                sueltas.append(f"{n} (en: «{d.dato}»)")
    return sueltas


# Si el modelo por defecto no está disponible para la clave (error 404), se prueba con estos
MODELOS_RESPALDO = ["gemini-flash-latest", "gemini-2.5-flash-lite"]


def generar_con_gemini(ctx: Contexto, api_key: str, modelo: str | None = None) -> FichaPauta:
    from google import genai
    from google.genai import errors

    cliente = genai.Client(api_key=api_key.strip())
    modelos = [modelo or os.getenv("GEMINI_MODEL", MODELO_POR_DEFECTO)] + MODELOS_RESPALDO
    ultimo_error = None
    for m in modelos:
        try:
            respuesta = cliente.models.generate_content(
                model=m,
                contents=f"{INSTRUCCIONES}\n\nCONTEXTO:\n{ctx.como_texto()}",
                config={
                    "response_mime_type": "application/json",
                    "response_schema": FichaPauta,
                    "temperature": 0.4,
                },
            )
        except errors.ClientError as e:
            ultimo_error = e
            if getattr(e, "code", None) == 404:  # modelo no disponible: probar el siguiente
                continue
            raise
        if respuesta.parsed is not None:
            return respuesta.parsed
        return FichaPauta.model_validate_json(respuesta.text)
    raise ultimo_error


def explicar_error(e: Exception) -> str:
    """Motivo legible de un error de Gemini, sin exponer la clave."""
    codigo = getattr(e, "code", None)
    mensaje = str(getattr(e, "message", "") or e)[:300]
    pistas = {
        400: "Revisa que la clave esté bien copiada en los Secrets de Streamlit (GEMINI_API_KEY = \"...\").",
        401: "La clave no es válida.",
        403: "La clave no tiene permiso para usar la API de Gemini (revisa el proyecto en Google AI Studio).",
        404: "Ningún modelo de Gemini probado está disponible para esta clave.",
        429: "Se agotó el límite gratuito de Gemini por ahora; espera un minuto y vuelve a intentar.",
    }
    return f"{type(e).__name__} {codigo or ''}: {mensaje} {pistas.get(codigo, '')}".strip()


def generar_sin_ia(perfil) -> FichaPauta:
    """Ficha base con reglas fijas, para usar sin clave de API (plan B y línea base)."""
    ub = perfil.ubicaciones
    datos: list[DatoClave] = []
    if not perfil.unidades.empty:
        datos.append(DatoClave(dato=f"Unidades mineras registradas a su nombre: {len(perfil.unidades)}.", fuente="F1"))
    elif not ub.empty:
        datos.append(DatoClave(dato=f"Unidades con ubicación aproximada: {len(ub)}, en "
                               + ", ".join(sorted({str(d).title() for d in ub['distrito']})) + ".", fuente="F6"))
    p25 = perfil.produccion[perfil.produccion["anio"] == 2025] if not perfil.produccion.empty else perfil.produccion
    for _, r in p25.sort_values("participacion", ascending=False).head(2).iterrows():
        datos.append(DatoClave(dato=f"{r['metal'].capitalize()} 2025: {r['participacion'] * 100:.1f} % de la producción nacional.",
                               fuente="F7"))
    if not perfil.multas.empty:
        datos.append(DatoClave(dato=f"Multas firmes: {len(perfil.multas)}, por un total de S/ {perfil.multas['multa_soles'].sum():,.2f}.", fuente="F3"))
    if not perfil.oxi.empty:
        datos.append(DatoClave(dato=f"Obras en las que figura como financista: {len(perfil.oxi)}.", fuente="F4"))
    if not perfil.conflictos.empty:
        datos.append(DatoClave(dato=f"Mencionada en {perfil.conflictos['reporte'].nunique()} reportes de la Defensoría.", fuente="F5"))

    por_verificar = ["Si las unidades siguen en operación y el año de referencia de cada fuente."]
    for _, u in perfil.unidades.iterrows():
        if not u["punto_coincide"]:
            por_verificar.append(f"Ubicación real de la unidad {u['unidad']}: sus coordenadas caen en otro distrito.")
    if not perfil.oxi.empty:
        por_verificar.append("Estado y calidad de las obras financiadas por Obras por Impuestos, en campo.")

    return FichaPauta(
        titular_tentativo=f"{perfil.nombre.title()}: la huella que dejan los registros",
        pregunta_periodistica=(
            "¿Qué relación hay entre las sanciones ambientales, las obras financiadas y la vida de las "
            "comunidades donde opera esta empresa?"
        ),
        angulo="La ficha cruza registros públicos dispersos para orientar el trabajo de campo; no prueba causalidad.",
        datos_clave=datos,
        actores_a_consultar=[
            "Comunidades y autoridades locales de los distritos donde opera",
            "La empresa (derecho a réplica)",
            "OEFA y Defensoría del Pueblo",
            "Entidades públicas que recibieron obras por impuestos",
        ],
        preguntas_para_entrevistas=[
            "¿Cómo cambió el territorio desde que llegó la operación?",
            "¿Qué pasó después de las sanciones del OEFA?",
            "¿Quién decidió qué obras se hicieron y a quién benefician?",
            "¿Qué acuerdos se firmaron con la comunidad y se cumplieron?",
        ],
        fuentes_publicas_a_revisar=[
            "Expedientes del OEFA (Tribunal de Fiscalización Ambiental)",
            "Ficha de cada obra en Invierte.pe por su código CUI",
            "Reportes de la Defensoría del Pueblo",
            "Catastro minero de INGEMMET (GEOCATMIN)",
        ],
        por_verificar=por_verificar,
        riesgos_de_campo=[
            "Exposición de fuentes en contextos de conflicto",
            "Acceso a zonas de operación privadas",
            "Distancias y altitud: ruta y contacto de emergencia",
        ],
    )


def como_markdown(ficha: FichaPauta, titulo: str, modo: str) -> str:
    def lista(items):
        return "\n".join(f"- {i}" for i in items)

    datos = "\n".join(f"- {d.dato} [{d.fuente}]" for d in ficha.datos_clave)
    return f"""# Ficha de pauta · {titulo}

*Escáner Minero · Gallo Negro · {modo}*

## {ficha.titular_tentativo}

**Pregunta:** {ficha.pregunta_periodistica}

**Ángulo:** {ficha.angulo}

## Datos clave
{datos}

## Actores a consultar
{lista(ficha.actores_a_consultar)}

## Preguntas para entrevistas
{lista(ficha.preguntas_para_entrevistas)}

## Fuentes públicas a revisar
{lista(ficha.fuentes_publicas_a_revisar)}

## Por verificar antes de publicar
{lista(ficha.por_verificar)}

## Riesgos de campo
{lista(ficha.riesgos_de_campo)}
"""
