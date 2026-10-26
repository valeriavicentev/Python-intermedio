"""Tarea 2 · Extracción estructurada con Gemini (API REST, sin paquetes extra).

La clave se lee de .env (GEMINI_API_KEY), que no se versiona. Cada respuesta se guarda en
datos/raw/llm/<id>.json, así que volver a correr no repite consultas ni gasta cuota.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MODELOS = ["gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-2.5-flash"]  # en orden de preferencia
CACHE = Path("datos/raw/llm")

PROMPT = """Eres un asistente de archivo. Extrae información SOLO del texto dado (salida de OCR o de una
transcripción automática de audio en español peruano; puede tener errores de lectura).

Responde únicamente un objeto JSON con estas claves:
- "modalidad": "documento" o "audio" (te lo indico abajo; cópialo).
- "tema": 2 a 6 palabras sobre de qué trata.
- "resumen": una oración (máx. 35 palabras) fiel al texto.
- "emisor": quién emite o firma el documento, o quién habla principalmente. null si no aparece.
- "fecha": fecha tal como aparece en el texto. null si no aparece.
- "monto": cantidad de dinero tal como aparece. null si no aparece.
- "lugar": lugar mencionado como sede o contexto. null si no aparece.
- "citas_clave": lista de 1 a 3 frases COPIADAS LITERALMENTE del texto (solo audio; para documentos usa []).
- "numero_hablantes": número de etiquetas [HABLANTE_n] distintas si las hay; null si no hay etiquetas.

Reglas: no inventes ni completes con conocimiento externo; si un dato no está explícito, usa null.
Si el texto es ilegible o vacío, pon tema "ilegible" y el resto en null.

Modalidad: {modalidad}
Texto:
\"\"\"{texto}\"\"\"
"""


def _clave() -> str:
    if "GEMINI_API_KEY" not in os.environ and Path(".env").exists():
        for linea in Path(".env").read_text().splitlines():
            if linea.startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = linea.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ["GEMINI_API_KEY"]


def _llamar(modelo: str, prompt: str, intentos: int = 6) -> dict:
    cuerpo = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}).encode()
    for k in range(intentos):
        req = urllib.request.Request(API.format(modelo=modelo), data=cuerpo, method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": _clave()})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                datos = json.load(r)
            texto = datos["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```(?:json)?|```$", "", texto.strip()).strip())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and k < intentos - 1:
                espera = 15 * 2 ** k
                print(f"  … {modelo} respondió {e.code}; reintento en {espera} s")
                time.sleep(espera)
                continue
            raise


def elegir_modelo() -> str:
    """Primer modelo de la lista que responde (se prueba con un texto mínimo)."""
    for m in MODELOS:
        try:
            _llamar(m, PROMPT.format(modalidad="documento", texto="Lima, 1 de enero de 1900."), intentos=2)
            return m
        except Exception as e:  # noqa: BLE001
            print(f"  {m} no disponible: {str(e)[:80]}")
    raise RuntimeError("Ningún modelo de Gemini respondió: revisa GEMINI_API_KEY en .env")


def extraer(id_: str, modalidad: str, texto: str, modelo: str, pausa: float = 4.0) -> dict:
    """Devuelve los campos y guarda en caché {campos, modelo}. Si el modelo pedido sigue saturado
    tras 3 intentos, prueba con el siguiente de MODELOS (el modelo usado queda registrado)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta = CACHE / f"{id_}.json"
    if ruta.exists():
        guardado = json.loads(ruta.read_text(encoding="utf-8"))
        return guardado if "_modelo" in guardado else guardado | {"_modelo": modelo}
    prompt = PROMPT.format(modalidad=modalidad, texto=(texto or "")[:5000])
    orden = [modelo] + [m for m in MODELOS if m != modelo]
    for k, m in enumerate(orden):
        try:
            campos = _llamar(m, prompt, intentos=3)
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 503) or k == len(orden) - 1:
                raise
            print(f"  {m} sigue sin responder ({e.code}); se usa {orden[k + 1]} para {id_}")
    campos["_modelo"] = m
    ruta.write_text(json.dumps(campos, ensure_ascii=False), encoding="utf-8")
    time.sleep(pausa)  # cuota gratuita: pocas solicitudes por minuto
    return campos
