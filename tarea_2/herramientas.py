"""Tarea 2 · Funciones de apoyo para 01_extraccion.ipynb y 02_evaluacion.ipynb.

OCR con PaddleOCR (API de la Sesión 10), recorte de audios largos en clips, seudonimización
y limpieza (duplicados por hash). La transcripción y la diarización vienen de voz.py (Sesión 13).
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

SR = 16_000

# ───────────────────────────────────────────── OCR
OPCIONES_OCR = dict(lang="es", use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=True)


def crear_ocr(**cambios):
    """PaddleOCR 3.x en español. use_textline_orientation=True ayuda con fotos inclinadas."""
    import os
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCR
    return PaddleOCR(**(OPCIONES_OCR | cambios))


def preprocesar(ruta: Path, destino: Path, lado_max: int = 1600) -> Path:
    """Copia de trabajo: corrige la rotación EXIF, pasa a RGB y limita el lado mayor (memoria)."""
    from PIL import Image, ImageOps
    destino.parent.mkdir(parents=True, exist_ok=True)
    img = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    img.thumbnail((lado_max, lado_max))
    img.save(destino, quality=92)
    return destino


def leer_ocr(ocr, ruta: Path) -> pd.DataFrame:
    """Una fila por línea detectada: texto, confianza y caja (x0, y0, x1, y1)."""
    r = ocr.predict(str(ruta))[0]
    cajas = np.asarray(r["rec_boxes"]).reshape(-1, 4) if len(r["rec_texts"]) else np.zeros((0, 4))
    return pd.DataFrame({"texto": r["rec_texts"], "confianza": np.round(r["rec_scores"], 3),
                         "x0": cajas[:, 0], "y0": cajas[:, 1], "x1": cajas[:, 2], "y1": cajas[:, 3]})


def unir_lineas(lineas: pd.DataFrame) -> str:
    """Ordena las líneas de arriba hacia abajo y de izquierda a derecha y las une en un texto."""
    if lineas.empty:
        return ""
    alto = (lineas["y1"] - lineas["y0"]).median() or 10
    orden = lineas.assign(fila=(lineas["y0"] / (alto * 0.7)).round()).sort_values(["fila", "x0"])
    return "\n".join(orden["texto"].str.strip())


def recortes(lineas: pd.DataFrame, ruta_img: Path, carpeta: Path, n: int = 3) -> list[Path]:
    """Guarda las n líneas de menor confianza como recortes (para revisar dónde falla el OCR)."""
    from PIL import Image
    carpeta.mkdir(parents=True, exist_ok=True)
    img = Image.open(ruta_img)
    salida = []
    for k, f in enumerate(lineas.nsmallest(n, "confianza").itertuples()):
        destino = carpeta / f"{ruta_img.stem}_linea{k}.png"
        img.crop((int(f.x0), int(f.y0), int(f.x1), int(f.y1))).save(destino)
        salida.append(destino)
    return salida


# ───────────────────────────────────────────── archivos y limpieza
def hash_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def marcar_duplicados(tabla: pd.DataFrame, col_ruta: str) -> pd.DataFrame:
    tabla = tabla.copy()
    tabla["hash"] = tabla[col_ruta].map(lambda r: hash_archivo(Path(r)))
    tabla["duplicado"] = tabla.duplicated("hash", keep="first")
    return tabla


# ───────────────────────────────────────────── audio
def cortar_en_clips(audio: np.ndarray, largo_obj: float = 45.0, largo_max: float = 75.0) -> list[tuple[float, float]]:
    """Corta un audio largo en clips de ~45 s, siempre en una pausa (según el VAD de voz.py).

    Devuelve (inicio, fin) en segundos. Los audios de menos de `largo_max` quedan enteros.
    """
    from voz import tramos_de_voz
    total = len(audio) / SR
    if total <= largo_max:
        return [(0.0, total)]
    tramos = tramos_de_voz(audio, silencio_min=0.4)
    cortes, ini = [], 0.0
    for a, b in tramos:
        if b - ini >= largo_obj:
            cortes.append((ini, b))
            ini = b
    if total - ini > 15:            # el resto se vuelve otro clip si tiene al menos 15 s
        cortes.append((ini, total))
    elif cortes:
        cortes[-1] = (cortes[-1][0], total)
    return cortes


def proporcion_voz(audio: np.ndarray) -> float:
    """Qué fracción del audio tiene voz. Clips con < 10 % se descartan como 'sin voz'."""
    from voz import tramos_de_voz
    if len(audio) == 0:
        return 0.0
    return sum(b - a for a, b in tramos_de_voz(audio)) / (len(audio) / SR)


def texto_con_hablantes(segmentos) -> str:
    """'[HABLANTE_1] ... [HABLANTE_2] ...' uniendo segmentos seguidos de la misma persona."""
    turnos = []
    for s in segmentos:
        h = f"HABLANTE_{s.hablante[1:]}" if s.hablante else None
        if turnos and turnos[-1][0] == h:
            turnos[-1][1].append(s.texto)
        else:
            turnos.append([h, [s.texto]])
    return " ".join((f"[{h}] " if h else "") + " ".join(t) for h, t in turnos).strip()


# ───────────────────────────────────────────── seudonimización
PATRONES = {
    "DNI": re.compile(r"(?<!\d)(?:DNI\s*N?[°º.]?\s*)?\d{8}(?!\d)", re.I),
    "RUC": re.compile(r"(?<!\d)(?:10|15|17|20)\d{9}(?!\d)"),
    "TELEFONO": re.compile(r"(?<!\d)(?:\+?51\s?)?9\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)"),
    "CORREO": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
}


def _trozos(texto: str, largo: int) -> list[str]:
    salida = []
    while texto:
        if len(texto) <= largo:
            salida.append(texto)
            break
        corte = texto.rfind(" ", 0, largo)
        corte = corte if corte > 0 else largo
        salida.append(texto[:corte])
        texto = texto[corte:].lstrip()
    return salida


def sugerir_personas(textos: pd.Series, umbral: float = 0.85) -> pd.DataFrame:
    """Sugiere nombres de persona con NER (mrm8488/bert-spanish-cased-finetuned-ner).

    Solo SUGIERE: la decisión de qué es un dato personal (y qué es una figura pública o
    histórica, p. ej. Ricardo Palma en una carta de 1912) es humana.
    """
    from transformers import pipeline
    ner = pipeline("ner", model="mrm8488/bert-spanish-cased-finetuned-ner", aggregation_strategy="simple")
    filas = []
    for idx, t in textos.fillna("").items():
        for trozo in _trozos(t, 600):          # BERT admite 512 tokens: trozos cortos, cortados en un espacio
            for e in ner(trozo):
                if e["entity_group"] == "PER" and e["score"] >= umbral and len(e["word"]) > 3:
                    filas.append({"id": idx, "nombre": e["word"].strip(), "score": round(float(e["score"]), 3)})
    return pd.DataFrame(filas, columns=["id", "nombre", "score"])


def seudonimizar_texto(texto: str, reemplazos: dict[str, str]) -> tuple[str, Counter]:
    """Reemplaza DNI, RUC, teléfonos y correos por etiquetas y los nombres de `reemplazos`
    por seudónimos (comparación difusa de voz.seudonimizar). Devuelve el texto y el conteo."""
    from voz import seudonimizar
    conteo = Counter()
    salida = texto or ""
    for etiqueta, patron in PATRONES.items():
        salida, n = patron.subn(f"[{etiqueta}]", salida)
        conteo[etiqueta] += n
    for nombre, seudonimo in reemplazos.items():
        nuevo = seudonimizar(salida, {nombre: seudonimo})
        conteo["NOMBRE"] += nuevo.count(seudonimo) - salida.count(seudonimo)
        salida = nuevo
    return salida, conteo
