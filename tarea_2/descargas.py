"""Tarea 2 · Descarga del corpus (documentos y audio) con licencia y atribución.

    uv run python descargas.py buscar      # lista candidatos de Wikimedia Commons con su licencia
    uv run python descargas.py bajar       # baja lo elegido en datos/seleccion_*.csv y escribe datos/fuentes.csv

Reglas que sigue: User-Agent descriptivo, 1,5 s de pausa entre pedidos, solo licencias libres
(dominio público, CC0, CC BY, CC BY-SA) y todo queda en datos/raw/ (fuera de Git).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
RAW_DOC = AQUI / "datos" / "raw" / "documentos"
RAW_AUD = AQUI / "datos" / "raw" / "audio"
API = "https://commons.wikimedia.org/w/api.php"
FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"
UA = {"User-Agent": "tarea2-ds-python-up/2026 (curso Data Science Python UP; uso académico)"}
PAUSA = 1.5
LICENCIAS_OK = re.compile(r"public domain|dominio p|pd|cc0|cc by(-sa)? \d|cc-by", re.I)
LICENCIAS_NO = re.compile(r"\bnc\b|\bnd\b|non-?commercial|fair use", re.I)

# ── Documentos ya verificados en la Sesión 10 (créditos en el notebook de la clase) ──
SEMILLA_DOCUMENTOS = [
    # (archivo en Commons, tipo, descripción)
    ("Acta de Creación de los Símbolos para el Distrito de Mache.jpg", "impreso", "Resolución de alcaldía de Mache (2016)"),
    ("Pisco-punch-mercurio-peruano-1791.jpg", "impreso", "Mercurio Peruano, 13 de enero de 1791"),
    ("Placa Calle Capon.jpg", "foto", "Placa de la Calle Capón, Lima"),
    ("Menu Levaggi 09052010.jpg", "foto", "Pizarra de menú, Lince"),
    ("Cartel Picante de cuy.JPG", "foto", "Cartel «Picante de cuy», Ingenio, Junín"),
    ("Carteles chicha.jpg", "foto", "Carteles chicha"),
    ("Peruvian Telephone Company receipt Lima 1895.JPG", "manuscrito", "Recibo llenado a mano, Lima 1895"),
    ("Tarjeta de Ricardo Palma a Luis Antonio Eguiguren Escudero 24 octubre 1912.png", "manuscrito", "Tarjeta manuscrita de Ricardo Palma (1912)"),
    ("Acta de Independencia Peru.jpg", "manuscrito", "Acta de la Independencia del Perú (1821)"),
]

# Búsquedas para completar el corpus (filetype:bitmap = solo imágenes)
BUSQUEDAS_DOCUMENTOS = {
    "impreso": ["El Comercio Lima periódico 18", "decreto Perú impreso", "El Peruano diario oficial página",
                "Mercurio Peruano", "Variedades revista Lima 19"],
    "foto": ["cartel Lima letrero", "aviso Lima calle texto", "placa conmemorativa Lima", "letrero Cusco tienda"],
    "manuscrito": ["carta manuscrita Perú", "manuscrito colonial Lima", "manuscrito Ricardo Palma",
                   "documento manuscrito Archivo General de la Nación Perú", "firma autógrafo presidente Perú carta"],
}

# ── Audio: entrevistas de la Sesión 13 + noticiarios de la Biblioteca Nacional del Perú ──
SEMILLA_AUDIO = [
    ("Entrevista 1 en la Av. Rivagüero - El Agustino.ogg", "entrevista", "Entrevista en la calle, El Agustino (2022)"),
    ("Entrevista 2 en la Av. Rivagüero - El Agustino.ogg", "entrevista", "Entrevista a dos vendedoras, El Agustino (2022) – multihablante"),
    ("Entrevista-Aurora Coronado-organización de mujeres indígenas-fiestas patrias.ogg", "entrevista", "Dirigente de Fenmucarinap (2022)"),
    ("Del Viejo Lima (Los Descalzos).webm", "noticiario", "Noticiario de los años 40 (BNP) – narración con música"),
    ("Verano En La Punta.webm", "noticiario", "Noticiario de los años 40 (BNP) – narración con música"),
]
BUSQUEDAS_AUDIO = ["entrevista Lima", "entrevista Perú", "noticiario Biblioteca Nacional del Perú",
                   "entrevista Cusco", "entrevista Arequipa", "Wikimedia Perú entrevista", "conferencia Lima"]


def _get_json(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params | {"format": "json"})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        datos = json.load(r)
    time.sleep(PAUSA)
    return datos


def info_commons(titulos: list[str]) -> pd.DataFrame:
    """Licencia, autor, tamaño, tipo MIME y duración (si es audio/video) de cada archivo."""
    filas = []
    for i in range(0, len(titulos), 40):
        lote = ["File:" + t.removeprefix("File:") for t in titulos[i:i + 40]]
        d = _get_json({"action": "query", "titles": "|".join(lote), "prop": "imageinfo",
                       "iiprop": "url|size|mime|extmetadata|metadata", "iiextmetadatafilter": "LicenseShortName|Artist|DateTimeOriginal|ImageDescription"})
        for p in d.get("query", {}).get("pages", {}).values():
            if "imageinfo" not in p:
                filas.append({"titulo": p["title"].removeprefix("File:"), "existe": False})
                continue
            ii = p["imageinfo"][0]
            meta = ii.get("extmetadata", {})
            limpio = lambda k: re.sub(r"<[^>]+>", "", meta.get(k, {}).get("value", "")).strip()
            dur = next((m["value"] for m in (ii.get("metadata") or []) if m.get("name") == "length"), None)
            filas.append({"titulo": p["title"].removeprefix("File:"), "existe": True,
                          "licencia": limpio("LicenseShortName"), "autor": limpio("Artist")[:120],
                          "fecha": limpio("DateTimeOriginal")[:40], "mime": ii.get("mime"),
                          "ancho": ii.get("width"), "alto": ii.get("height"), "bytes": ii.get("size"),
                          "duracion_seg": round(float(dur), 1) if dur else None,
                          "pagina": ii.get("descriptionurl")})
    tabla = pd.DataFrame(filas)
    if "licencia" in tabla:
        lic = tabla["licencia"].fillna("")
        tabla["licencia_ok"] = lic.str.contains(LICENCIAS_OK) & ~lic.str.contains(LICENCIAS_NO)
    return tabla


def buscar_commons(consulta: str, n: int = 15, audio: bool = False) -> list[str]:
    filtro = " filetype:audio|video" if audio else " filetype:bitmap"
    d = _get_json({"action": "query", "list": "search", "srsearch": consulta + filtro,
                   "srnamespace": 6, "srlimit": n})
    return [r["title"].removeprefix("File:") for r in d.get("query", {}).get("search", [])]


def candidatos() -> None:
    """Escribe datos/candidatos_documentos.csv y datos/candidatos_audio.csv para revisarlos a mano."""
    docs = [(t, tipo, d, "semilla") for t, tipo, d in SEMILLA_DOCUMENTOS]
    for tipo, consultas in BUSQUEDAS_DOCUMENTOS.items():
        for q in consultas:
            docs += [(t, tipo, "", q) for t in buscar_commons(q)]
    docs = pd.DataFrame(docs, columns=["titulo", "tipo", "descripcion", "busqueda"]).drop_duplicates("titulo")
    docs = docs.merge(info_commons(docs["titulo"].tolist()), on="titulo", how="left")
    docs.to_csv(AQUI / "datos" / "candidatos_documentos.csv", index=False)

    aud = [(t, tipo, d, "semilla") for t, tipo, d in SEMILLA_AUDIO]
    for q in BUSQUEDAS_AUDIO:
        aud += [(t, "", "", q) for t in buscar_commons(q, audio=True)]
    aud = pd.DataFrame(aud, columns=["titulo", "tipo", "descripcion", "busqueda"]).drop_duplicates("titulo")
    aud = aud.merge(info_commons(aud["titulo"].tolist()), on="titulo", how="left")
    aud.to_csv(AQUI / "datos" / "candidatos_audio.csv", index=False)
    print(f"{len(docs)} documentos candidatos ({docs['licencia_ok'].sum()} con licencia libre)")
    print(f"{len(aud)} audios candidatos, {aud.loc[aud['licencia_ok'] == True, 'duracion_seg'].sum() / 60:.0f} min con licencia libre")
    print("Revisa los CSV, copia las filas elegidas a datos/seleccion_documentos.csv y datos/seleccion_audio.csv")


def _bajar(titulo: str, destino: Path, ancho: int | None = None) -> Path:
    if destino.exists():
        return destino
    url = FILEPATH + urllib.parse.quote(titulo) + (f"?width={ancho}" if ancho else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        destino.write_bytes(r.read())
    time.sleep(PAUSA)
    return destino


def bajar_seleccion() -> pd.DataFrame:
    """Baja lo elegido y escribe datos/fuentes.csv (id, modalidad, fuente_url, licencia, acceso...).

    seleccion_documentos.csv: titulo, tipo, descripcion  (o archivo_local para fotos/manuscritos propios)
    seleccion_audio.csv:      titulo, tipo, descripcion
    """
    RAW_DOC.mkdir(parents=True, exist_ok=True)
    RAW_AUD.mkdir(parents=True, exist_ok=True)
    hoy = date.today().isoformat()
    fuentes = []

    docs = pd.read_csv(AQUI / "datos" / "seleccion_documentos.csv")
    info = info_commons(docs["titulo"].dropna().tolist()).set_index("titulo") if docs["titulo"].notna().any() else pd.DataFrame()
    for i, f in enumerate(docs.itertuples(), 1):
        did = f"doc_{i:03d}"
        if isinstance(f.titulo, str) and f.titulo:
            m = info.loc[f.titulo]
            if m.get("licencia_ok") is not True and m.get("licencia_ok") != True:
                print(f"  ✗ {f.titulo}: no existe o licencia «{m.get('licencia')}» no permitida, se omite")
                continue
            ext = Path(f.titulo).suffix.lower().replace(".jpeg", ".jpg")
            ruta = _bajar(f.titulo, RAW_DOC / f"{did}{ext if ext in ('.jpg', '.png') else '.jpg'}", ancho=1600)
            fuentes.append({"id": did, "modalidad": "documento", "tipo": f.tipo, "descripcion": f.descripcion,
                            "archivo": str(ruta.relative_to(AQUI)), "fuente_url": m["pagina"],
                            "licencia": m["licencia"], "autor": m["autor"], "fecha_extraccion": hoy,
                            "acceso": "descargas.py bajar (Wikimedia Commons, Special:FilePath, ancho 1600 px)"})
        else:  # captura propia ya copiada por la estudiante a datos/raw/documentos/
            fuentes.append({"id": did, "modalidad": "documento", "tipo": f.tipo, "descripcion": f.descripcion,
                            "archivo": f"datos/raw/documentos/{f.archivo_local}", "fuente_url": "",
                            "licencia": "CC BY 4.0 (captura propia, sin datos personales)", "autor": "Valeria Vicente",
                            "fecha_extraccion": hoy, "acceso": "captura propia; copia publicable en datos/ejemplos/ si aplica"})

    aud = pd.read_csv(AQUI / "datos" / "seleccion_audio.csv")
    info = info_commons(aud["titulo"].tolist()).set_index("titulo")
    for i, f in enumerate(aud.itertuples(), 1):
        m = info.loc[f.titulo]
        if m.get("licencia_ok") != True:
            print(f"  ✗ {f.titulo}: no existe o licencia «{m.get('licencia')}» no permitida, se omite")
            continue
        ruta = _bajar(f.titulo, RAW_AUD / f"fuente_{i:02d}{Path(f.titulo).suffix.lower()}")
        fuentes.append({"id": f"fuente_{i:02d}", "modalidad": "audio", "tipo": f.tipo, "descripcion": f.descripcion,
                        "archivo": str(ruta.relative_to(AQUI)), "fuente_url": m["pagina"], "licencia": m["licencia"],
                        "autor": m["autor"], "fecha_extraccion": hoy,
                        "acceso": "descargas.py bajar (Wikimedia Commons, Special:FilePath)"})
    tabla = pd.DataFrame(fuentes)
    tabla.to_csv(AQUI / "datos" / "fuentes_crudas.csv", index=False)
    print(tabla.groupby(["modalidad", "tipo"]).size())
    return tabla


def bajar_openslr73(n_por_sexo: int = 12) -> pd.DataFrame:
    """Frases leídas de español peruano (OpenSLR 73, Google, CC BY-SA 4.0) con su transcripción oficial.
    Reutiliza datos.py de la Sesión 13 (lee el zip por partes con HTTP Range)."""
    import datos  # copia de sessions/13-audio-a-texto/datos.py
    datos.CARPETA = RAW_AUD
    return datos.bajar_openslr73(n_por_sexo=n_por_sexo)


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "buscar"
    if accion == "buscar":
        candidatos()
    elif accion == "bajar":
        bajar_seleccion()
        print(f"OpenSLR 73: {len(bajar_openslr73())} frases")
