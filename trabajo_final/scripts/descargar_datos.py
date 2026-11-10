"""Descarga las fuentes públicas del Radar Extractivo.

Se corre desde una computadora con salida normal a internet (los portales del
Estado peruano no siempre aceptan conexiones desde servidores en la nube):

    python3 descargar_datos.py                # RUIAS + último reporte de la Defensoría
    python3 descargar_datos.py --reportes 12  # los últimos 12 reportes
    python3 descargar_datos.py --reportes 0   # todos los reportes publicados

Solo usa la biblioteca estándar de Python: no hay que instalar nada.
Guarda todo en la carpeta ./datos_radar/
"""

from __future__ import annotations

import argparse
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

DESTINO = Path("datos_radar")
AGENTE = "Mozilla/5.0 (Radar Extractivo; proyecto periodistico)"

RUIAS = (
    "https://www.datosabiertos.gob.pe/sites/default/files/"
    "1a_Registro%20%C3%9Anico%20de%20Infractores%20Ambientales%20Sancionados.csv"
)
RUIAS_DICCIONARIO = (
    "https://www.datosabiertos.gob.pe/sites/default/files/"
    "1c_Formato_DiccionarioDatos_%20Registro%20%C3%9Anico%20de%20Infractores%20Ambientales%20Sancionados.xlsx"
)
DEFENSORIA = "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/"
PATRON_REPORTE = re.compile(
    r'href="(https://www\.defensoria\.gob\.pe/wp-content/uploads/[^"]*?'
    r'Reporte-de-conflictos-sociales-n-?(\d+)[^"]*?\.pdf)"',
    re.IGNORECASE,
)


def contexto_ssl() -> ssl.SSLContext:
    try:
        import certifi  # si está instalado, usa sus certificados

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CTX = contexto_ssl()


def bajar(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def guardar(url: str, ruta: Path) -> None:
    if ruta.exists() and ruta.stat().st_size > 0:
        print(f"  ya existe: {ruta.name}")
        return
    datos = bajar(url, timeout=180)
    ruta.write_bytes(datos)
    print(f"  ok: {ruta.name} ({len(datos) / 1e6:.1f} MB)")


def listar_reportes(max_paginas: int = 60) -> dict[int, str]:
    """Recorre el listado paginado de la Defensoría y junta los PDF por número."""
    encontrados: dict[int, str] = {}
    for pagina in range(1, max_paginas + 1):
        url = DEFENSORIA if pagina == 1 else f"{DEFENSORIA}page/{pagina}/"
        try:
            html = bajar(url).decode("utf-8", errors="ignore")
        except Exception as e:  # fin de la paginación (404) u otro error
            print(f"  listado: se detiene en la página {pagina} ({type(e).__name__})")
            break
        nuevos = 0
        for enlace, numero in PATRON_REPORTE.findall(html):
            n = int(numero)
            if n not in encontrados:
                encontrados[n] = enlace
                nuevos += 1
        print(f"  página {pagina}: {nuevos} reportes nuevos (total {len(encontrados)})")
        if nuevos == 0 and pagina > 3:
            break
        time.sleep(1)  # cortesía con el servidor
    return encontrados


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reportes", type=int, default=1, help="cuántos reportes recientes (0 = todos)")
    args = ap.parse_args()

    DESTINO.mkdir(exist_ok=True)
    (DESTINO / "defensoria").mkdir(exist_ok=True)
    errores = []

    print("1) OEFA - Registro Único de Infractores Ambientales Sancionados")
    for url, nombre in [(RUIAS, "oefa_ruias.csv"), (RUIAS_DICCIONARIO, "oefa_ruias_diccionario.xlsx")]:
        try:
            guardar(url, DESTINO / nombre)
        except Exception as e:
            errores.append(f"{nombre}: {e}")
            print(f"  ERROR {nombre}: {e}")

    print("2) Defensoría del Pueblo - Reportes de conflictos sociales")
    try:
        reportes = listar_reportes(max_paginas=3 if args.reportes and args.reportes <= 5 else 60)
        numeros = sorted(reportes, reverse=True)
        if args.reportes:
            numeros = numeros[: args.reportes]
        for n in numeros:
            try:
                guardar(reportes[n], DESTINO / "defensoria" / f"reporte_conflictos_{n:03d}.pdf")
                time.sleep(1)
            except Exception as e:
                errores.append(f"reporte {n}: {e}")
                print(f"  ERROR reporte {n}: {e}")
        if not numeros:
            errores.append("No se encontraron enlaces a reportes en el listado de la Defensoría.")
    except Exception as e:
        errores.append(f"listado Defensoría: {e}")

    print()
    if errores:
        print("Terminó con errores:")
        for e in errores:
            print(" -", e)
        if any("CERTIFICATE" in e.upper() for e in errores):
            print("\nSi el error es de certificados SSL, corre una vez:  pip3 install certifi  y vuelve a intentar.")
        sys.exit(1)
    print(f"Listo. Archivos en {DESTINO.resolve()}")


if __name__ == "__main__":
    main()
