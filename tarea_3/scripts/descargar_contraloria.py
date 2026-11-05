"""Descarga los PDF de los informes de control de la Contraloría usados en el dashboard.

Lee datos/procesados/informes_control_detalle.csv y guarda, por cada informe:
  - el resumen  (TIPOARCHIVO=RE)      -> <codigo>_<numero>_resumen.pdf
  - el informe  (TIPOARCHIVO=ADJUNTO) -> <codigo>_<numero>_informe.pdf
en datos/originales/contraloria/. Si un archivo ya existe, no lo vuelve a bajar.

Uso (desde la carpeta tarea_3):  python3 scripts/descargar_contraloria.py
"""
import csv
import re
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CSV = BASE / "datos" / "procesados" / "informes_control_detalle.csv"
DESTINO = BASE / "datos" / "originales" / "contraloria"
DESTINO.mkdir(parents=True, exist_ok=True)


def limpiar(texto):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", texto).strip("-")


def bajar(url, ruta, intentos=3):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                datos = r.read()
            if not datos.startswith(b"%PDF"):
                raise ValueError("la respuesta no es un PDF")
            ruta.write_bytes(datos)
            return len(datos)
        except Exception as e:
            print(f"   intento {i + 1} falló: {e}")
            time.sleep(3)
    return None


# Un mismo informe puede aparecer en varias filas (varios CUI del mismo paquete)
informes = {}
with open(CSV, encoding="utf-8") as f:
    for fila in csv.DictReader(f):
        informes.setdefault(fila["codigo"], fila)

print(f"{len(informes)} informes únicos")
fallidos = []
for n, (codigo, fila) in enumerate(sorted(informes.items()), 1):
    nombre = f"{codigo}_{limpiar(fila['numero'])}"
    for tipo, url in (("resumen", fila["url_resumen"]), ("informe", fila["url_informe"])):
        ruta = DESTINO / f"{nombre}_{tipo}.pdf"
        if ruta.exists() and ruta.stat().st_size > 0:
            continue
        print(f"[{n}/{len(informes)}] {ruta.name}")
        if bajar(url, ruta) is None:
            fallidos.append(ruta.name)
        time.sleep(1)  # pausa para no saturar el servidor

print(f"\nListo. Archivos en {DESTINO}")
if fallidos:
    print(f"No se pudieron bajar {len(fallidos)}: vuelve a correr el script para reintentarlos.")
    for x in fallidos:
        print("  -", x)
