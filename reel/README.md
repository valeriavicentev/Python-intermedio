# Reel «¿Cuánto se quemó realmente?» · Sesión 15

Archivos:
- `fuente.txt`: el texto original.
- `guion.json`: el guion en 8 escenas (frase narrada con números en palabras, cifra y etiqueta en pantalla).
- `hacer_reel.py`: tu voz (Qwen3-TTS), control con Whisper, subtítulos y video.
- `posts.md`: los tres posts (Instagram/TikTok, X y LinkedIn).

## 1. Instalar (una vez; descarga unos 4 GB de modelos la primera vez)

```bash
uv venv .venv
uv pip install --python .venv/bin/python qwen-tts faster-whisper pillow imageio-ffmpeg soundfile jiwer scipy
```

En Windows, cambia `.venv/bin/python` por `.venv\Scripts\python`.

## 2. Grabar tu voz

Unos 15 segundos con el celular, en un cuarto callado, con el tono del reel. Guarda el
archivo como `mi_voz.m4a` en esta carpeta.

## 3. Revisar el diseño sin modelos (opcional, tarda 30 s)

```bash
.venv/bin/python hacer_reel.py --prueba --autor "Tu nombre"
```

## 4. Generar el reel

```bash
.venv/bin/python hacer_reel.py --voz mi_voz.m4a --autor "Tu nombre" --fuente "NASA, Agencia Espacial Europea"
```

Sin Mac con chip M, deja el modelo por defecto (0.6B). Con Mac M y 32 GB puedes probar
`--tts Qwen/Qwen3-TTS-12Hz-1.7B-Base`.

Resultado en `salidas/`: `reel.mp4`, `reel.srt` y `portada.png`.

## 5. Entregar

Sube `salidas/reel.mp4` y `posts.md` como comentario en el issue de la sesión 15.
No se publica en redes sin revisar el guion contra la fuente.
