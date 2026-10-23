# Tarea 2 · Voces y documentos peruanos: del archivo escaneado al texto buscable

> **Pregunta:** ¿Podemos convertir documentos escaneados y entrevistas en audio en un archivo de texto estructurado y buscable?

_(Este README se completa en la Parte 3: hallazgos, limitaciones y enlace del dashboard.)_

## Estructura

| Archivo | Qué hace |
|---|---|
| `descargas.py` | Busca candidatos en Wikimedia Commons con su licencia y baja lo elegido (User-Agent descriptivo, 1,5 s entre pedidos) |
| `datos.py`, `voz.py` | Copias de la Sesión 13 (OpenSLR 73; VAD, faster-whisper, diarización, SRT/TXT, WER/CER) |
| `herramientas.py` | OCR con PaddleOCR, corte de audios en clips, limpieza por hash y seudonimización |
| `01_extraccion.ipynb` | Parte 1: OCR + ASR, seudonimización, limpieza, EDA y exportación |

## Corpus y fuentes

- Documentos: Wikimedia Commons (dominio público / CC0 / CC BY / CC BY-SA) y capturas propias sin datos personales.
- Audio: Wikimedia Commons (entrevistas CC BY-SA 4.0; noticiarios de la Biblioteca Nacional del Perú, dominio público) y OpenSLR 73 (Google, CC BY-SA 4.0).
- Detalle por archivo (URL, licencia, autor y fecha de extracción): `datos/fuentes.csv`.

## Cómo reproducir la Parte 1

```bash
# en la carpeta del repositorio de la clase (Data-Science-Python):
uv sync --group docai --group audio
# en esta carpeta, con ese entorno:
uv run --project <ruta-a-Data-Science-Python> python descargas.py buscar   # crea datos/candidatos_*.csv
# elegir filas → datos/seleccion_documentos.csv y datos/seleccion_audio.csv
uv run --project <ruta-a-Data-Science-Python> python descargas.py bajar    # baja a datos/raw/ (no se versiona)
# ejecutar 01_extraccion.ipynb con el kernel de ese entorno
```
