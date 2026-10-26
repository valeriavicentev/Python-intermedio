"""Del texto a tu voz: convierte guion.json en un reel vertical narrado con tu voz clonada.

Pasos:
  1. Revisa el guion contra la fuente: toda cifra debe aparecer tal cual en el texto.
  2. Transcribe tu nota de voz con Whisper (Qwen3-TTS necesita saber qué dijiste).
  3. Qwen3-TTS narra cada escena con tu voz. Whisper la vuelve a escuchar y, si entiende
     mal más del 25 % de las palabras, la genera de nuevo.
  4. Arma el video 1080x1920 a 30 fps (H.264 + AAC, -14 LUFS) con subtítulos palabra por
     palabra, el aviso «Voz generada con IA», reel.srt y portada.png.

Uso:
  python hacer_reel.py --voz mi_voz.m4a --autor "Tu nombre" --fuente "NASA FIRMS, ESA Sentinel-2"
  python hacer_reel.py --prueba      # sin modelos: audio en silencio, solo para revisar el diseño
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

ANCHO, ALTO, FPS = 1080, 1920, 30
PAUSA = 0.35          # segundos de silencio entre escenas
UMBRAL_WER = 0.25     # si Whisper entiende mal más de esto, se regenera la escena
INTENTOS = 3
FONDO, TINTA, GRIS, NARANJA = (28, 26, 23), (246, 242, 234), (170, 164, 154), (226, 132, 74)
WHISPER = "small"


# ───────────────────────────────────────────────────────── utilidades
def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def fuente(tamano: int, negrita: bool = True) -> ImageFont.FreeTypeFont:
    """Busca una tipografía del sistema (Mac, Windows o Linux)."""
    candidatas = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if negrita else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if negrita else "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if negrita else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf" if negrita else "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrita else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for ruta in candidatas:
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tamano)
    return ImageFont.load_default(size=tamano)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ñ ]+", " ", texto).strip()


def envolver(draw, texto, letra, ancho_max):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if draw.textlength(prueba, font=letra) <= ancho_max:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


# ───────────────────────────────────────────────────────── 1. revisar guion
def revisar_guion(escenas, texto_fuente: str | None):
    total = sum(len(e["frase"].split()) for e in escenas)
    print(f"Guion: {len(escenas)} escenas, {total} palabras (~{total / 2.6:.0f} s narrado)")
    if not texto_fuente:
        return
    plano = texto_fuente.replace("\u00a0", " ")
    for i, e in enumerate(escenas, 1):
        cifra = e.get("cifra", "").strip()
        if cifra and cifra not in plano:
            print(f"  ¡¡ Escena {i}: la cifra «{cifra}» no aparece tal cual en la fuente. Revísala.")


# ───────────────────────────────────────────────────────── 2-3. voz
class Narrador:
    def __init__(self, modelo_tts: str):
        import torch
        from faster_whisper import WhisperModel
        from qwen_tts import Qwen3TTSModel

        if torch.cuda.is_available():
            kw = {"device_map": "cuda:0", "dtype": torch.bfloat16}
        elif torch.backends.mps.is_available():
            kw = {"device_map": "mps", "dtype": torch.float32}
        else:
            kw = {"device_map": "cpu", "dtype": torch.float32}
        print(f"Cargando {modelo_tts} en {kw['device_map']}…")
        self.tts = Qwen3TTSModel.from_pretrained(modelo_tts, **kw)
        print("Cargando Whisper…")
        self.whisper = WhisperModel(WHISPER, device="cpu", compute_type="int8")
        self.prompt = None

    def transcribir(self, audio: np.ndarray, sr: int, palabras=False):
        if sr != 16_000:
            import scipy.signal as ss
            audio = ss.resample_poly(audio, 16_000, sr)
        segs, _ = self.whisper.transcribe(audio.astype(np.float32), language="es", word_timestamps=palabras)
        segs = list(segs)
        texto = " ".join(s.text.strip() for s in segs)
        if not palabras:
            return texto
        return texto, [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or [])]

    def preparar_voz(self, ruta_voz: Path, texto_voz: str | None):
        wav = ruta_voz.with_suffix(".ref.wav")
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(ruta_voz), "-ac", "1", "-ar", "24000", str(wav)], check=True)
        audio, sr = sf.read(wav, dtype="float32")
        dur = len(audio) / sr
        print(f"Tu voz: {dur:.1f} s")
        if dur < 8:
            print("  Aviso: la grabación dura menos de 8 s; el clon puede sonar poco parecido.")
        if not texto_voz:
            texto_voz = self.transcribir(audio, sr)
            print(f"  Whisper entendió: «{texto_voz}»")
        self.prompt = self.tts.create_voice_clone_prompt(ref_audio=(audio, sr), ref_text=texto_voz)

    def narrar(self, frase: str):
        import jiwer
        mejor = None
        for intento in range(1, INTENTOS + 1):
            wavs, sr = self.tts.generate_voice_clone(text=frase, language="Spanish", voice_clone_prompt=self.prompt)
            audio = np.asarray(wavs[0], dtype=np.float32)
            oido, palabras = self.transcribir(audio, sr, palabras=True)
            error = jiwer.wer(normalizar(frase), normalizar(oido) or "x")
            print(f"    intento {intento}: error {error:.0%}")
            if mejor is None or error < mejor[0]:
                mejor = (error, audio, sr, palabras)
            if error <= UMBRAL_WER:
                break
        if mejor[0] > UMBRAL_WER:
            print("    ¡¡ Sigue sonando mal: escucha esta escena antes de publicar.")
        return mejor[1], mejor[2], mejor[3]


def tiempos_palabras(frase: str, palabras_whisper, inicio: float, dur: float):
    """Asigna a cada palabra del guion su momento: usa Whisper si coincide, si no, reparte."""
    palabras = frase.split()
    if palabras_whisper and len(palabras_whisper) == len(palabras):
        return [(p, inicio + a, inicio + b) for p, (_, a, b) in zip(palabras, palabras_whisper)]
    a = palabras_whisper[0][1] if palabras_whisper else 0.1
    b = palabras_whisper[-1][2] if palabras_whisper else dur - 0.1
    pesos = np.array([len(p) + 2 for p in palabras], dtype=float)
    cortes = a + np.concatenate([[0], np.cumsum(pesos)]) / pesos.sum() * (b - a)
    return [(p, inicio + cortes[i], inicio + cortes[i + 1]) for i, p in enumerate(palabras)]


# ───────────────────────────────────────────────────────── 4. video
def bloques_subtitulo(palabras, maximo=4):
    """Agrupa palabras en bloques cortos, cortando en la puntuación."""
    bloques, actual = [], []
    for w in palabras:
        actual.append(w)
        if len(actual) >= maximo or w[0][-1] in ".,:;?!":
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


def lamina(escena, titulo, autor, fuente_datos, progreso):
    img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    d = ImageDraw.Draw(img)
    x = 90
    d.line([(x, 150), (ANCHO - 90, 150)], fill=(60, 56, 50), width=4)
    d.line([(x, 150), (x + (ANCHO - 180) * progreso, 150)], fill=NARANJA, width=4)
    d.text((x, 190), titulo.upper(), font=fuente(34), fill=NARANJA)
    aviso = "VOZ GENERADA CON IA"
    f_aviso = fuente(24)
    w = d.textlength(aviso, font=f_aviso)
    d.rounded_rectangle([x, 250, x + w + 36, 294], radius=22, outline=GRIS, width=2)
    d.text((x + 18, 259), aviso, font=f_aviso, fill=GRIS)

    cifra = escena.get("cifra", "").strip()
    y = 620
    if cifra:
        tam = 260
        while d.textlength(cifra, font=fuente(tam)) > ANCHO - 180:
            tam -= 10
        d.text((x, y), cifra, font=fuente(tam), fill=TINTA)
        y += tam + 40
        for linea in envolver(d, escena["etiqueta"], fuente(48, False), ANCHO - 180):
            d.text((x, y), linea, font=fuente(48, False), fill=GRIS)
            y += 62
    else:
        for linea in envolver(d, escena["etiqueta"], fuente(96), ANCHO - 180):
            d.text((x, y), linea, font=fuente(96), fill=TINTA)
            y += 112

    pie = f"{autor} · Fuente: {fuente_datos}" if autor else f"Fuente: {fuente_datos}"
    for i, linea in enumerate(envolver(d, pie, fuente(26, False), ANCHO - 180)):
        d.text((x, 1480 + i * 36), linea, font=fuente(26, False), fill=GRIS)
    return img


def dibujar_subtitulo(img, bloque, t):
    d = ImageDraw.Draw(img)
    letra = fuente(56)
    espacio = d.textlength(" ", font=letra)
    textos = [w[0] for w in bloque]
    ancho = sum(d.textlength(p, font=letra) for p in textos) + espacio * (len(textos) - 1)
    if ancho > ANCHO - 200:
        letra = fuente(int(56 * (ANCHO - 200) / ancho))
        espacio = d.textlength(" ", font=letra)
        ancho = sum(d.textlength(p, font=letra) for p in textos) + espacio * (len(textos) - 1)
    x, y = (ANCHO - ancho) / 2, 1250
    d.rounded_rectangle([x - 28, y - 18, x + ancho + 28, y + 86], radius=16, fill=(44, 41, 37))
    for p, a, b in bloque:
        color = NARANJA if a <= t < b + 0.05 else TINTA
        d.text((x, y), p, font=letra, fill=color)
        x += d.textlength(p, font=letra) + espacio


def srt_tiempo(s):
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def armar_video(escenas, audios, sr, palabras_por_escena, args, salida: Path):
    # audio completo
    pista, inicios = [], []
    t = 0.0
    for a in audios:
        inicios.append(t)
        pista += [a, np.zeros(int(PAUSA * sr), dtype=np.float32)]
        t += len(a) / sr + PAUSA
    total = t
    sf.write(salida / "reel.wav", np.concatenate(pista), sr)

    # subtítulos
    bloques = []
    for i, ws in enumerate(palabras_por_escena):
        for b in bloques_subtitulo(ws):
            bloques.append((i, b))
    with open(salida / "reel.srt", "w", encoding="utf-8") as f:
        for n, (_, b) in enumerate(bloques, 1):
            f.write(f"{n}\n{srt_tiempo(b[0][1])} --> {srt_tiempo(b[-1][2] + 0.1)}\n{' '.join(w[0] for w in b)}\n\n")

    # láminas fijas por escena
    fondos = [lamina(e, args.titulo, args.autor, args.fuente, (i + 1) / len(escenas)) for i, e in enumerate(escenas)]
    portada = lamina({"cifra": "", "etiqueta": args.titulo}, args.titulo, args.autor, args.fuente, 0)
    portada.save(salida / "portada.png")

    fin_escena = inicios[1:] + [total]
    cmd = [ffmpeg(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
           "-i", str(salida / "reel.wav"),
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
           str(salida / "reel.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n_cuadros = int(np.ceil(total * FPS))
    escena, k = 0, 0
    for n in range(n_cuadros):
        t = n / FPS
        while escena < len(escenas) - 1 and t >= fin_escena[escena]:
            escena += 1
        cuadro = fondos[escena].copy()
        while k < len(bloques) - 1 and t >= bloques[k + 1][1][0][1]:
            k += 1
        i, b = bloques[k]
        if i == escena and t <= b[-1][2] + 0.4:
            dibujar_subtitulo(cuadro, b, t)
        proc.stdin.write(cuadro.tobytes())
        if n % (FPS * 10) == 0:
            print(f"  video: {t:.0f}/{total:.0f} s")
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg falló al armar el video.")
    print(f"Listo: {salida / 'reel.mp4'} ({total:.1f} s)")
    if not 30 <= total <= 60:
        print(f"  ¡¡ El reel dura {total:.0f} s; la tarea pide entre 30 y 60.")


# ───────────────────────────────────────────────────────── principal
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--guion", default="guion.json")
    p.add_argument("--texto", default="fuente.txt", help="texto original, para verificar las cifras")
    p.add_argument("--voz", help="tu nota de voz (.m4a, .ogg, .wav), unos 15 segundos")
    p.add_argument("--texto-voz", help="lo que dices en la nota de voz; si falta, lo transcribe Whisper")
    p.add_argument("--autor", default="")
    p.add_argument("--fuente", default="NASA, Agencia Espacial Europea")
    p.add_argument("--titulo", help="texto de la cabecera; por defecto, el título del guion")
    p.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    p.add_argument("--salida", default="salidas")
    p.add_argument("--prueba", action="store_true", help="sin modelos: silencio, para revisar el diseño")
    args = p.parse_args()

    guion = json.loads(Path(args.guion).read_text(encoding="utf-8"))
    escenas = guion["escenas"]
    args.titulo = args.titulo or guion.get("titulo", "")
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    texto = Path(args.texto).read_text(encoding="utf-8") if Path(args.texto).exists() else None
    revisar_guion(escenas, texto)

    audios, palabras = [], []
    if args.prueba:
        sr, t = 24_000, 0.0
        for e in escenas:
            dur = len(e["frase"].split()) / 2.6 + 0.3
            audios.append(np.zeros(int(dur * sr), dtype=np.float32))
            palabras.append(tiempos_palabras(e["frase"], [], t, dur))
            t += dur + PAUSA
    else:
        if not args.voz:
            sys.exit("Falta --voz con tu nota de voz.")
        narrador = Narrador(args.tts)
        narrador.preparar_voz(Path(args.voz), args.texto_voz)
        t = 0.0
        for i, e in enumerate(escenas, 1):
            print(f"  Escena {i}/{len(escenas)}")
            audio, sr, ws = narrador.narrar(e["frase"])
            dur = len(audio) / sr
            audios.append(audio)
            palabras.append(tiempos_palabras(e["frase"], ws, t, dur))
            t += dur + PAUSA
    armar_video(escenas, audios, sr, palabras, args, salida)


if __name__ == "__main__":
    main()
