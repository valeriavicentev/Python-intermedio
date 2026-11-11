"""Cruza las empresas del escáner con el Padrón Reducido del RUC de la SUNAT.

    python scripts/cruzar_sunat.py

Lee data/raw/sunat/padron_reducido_ruc.zip sin descomprimirlo (1.5 GB de texto) y
guarda en data/processed/empresa_sunat.csv, para cada empresa:
- el RUC (si la empresa no lo tenía, se busca por nombre normalizado),
- el estado del contribuyente (ACTIVO, BAJA DE OFICIO, SUSPENSION TEMPORAL...),
- la condición de domicilio (HABIDO, NO HABIDO...).

El padrón no se sube a GitHub (pesa cientos de MB); solo la tabla resultante.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from radar.empresas import clave  # noqa: E402

PADRON = RAIZ / "data" / "raw" / "sunat" / "padron_reducido_ruc.zip"
PROC = RAIZ / "data" / "processed"


def main() -> None:
    emp = pd.read_csv(PROC / "empresas.csv", dtype={"ruc": str})
    al = pd.read_csv(PROC / "empresa_alias.csv")

    por_ruc = {r: i for r, i in zip(emp["ruc"], emp["empresa_id"]) if isinstance(r, str)}
    # Claves de todos los nombres con que aparece cada empresa
    por_clave: dict[str, str] = {}
    for n, i in list(zip(al["nombre_en_fuente"], al["empresa_id"])) + list(zip(emp["nombre"], emp["empresa_id"])):
        c = clave(n)
        if c:
            por_clave.setdefault(c, i)

    # Filtro rápido: la palabra más larga de cada clave debe aparecer en la línea
    anclas = sorted({max(c.split(), key=len) for c in por_clave}, key=len, reverse=True)
    filtro = re.compile("|".join(re.escape(a) for a in anclas).encode())

    filas = []
    with zipfile.ZipFile(PADRON) as z, z.open(z.infolist()[0]) as f:
        f.readline()  # encabezado
        for linea in f:
            if not linea.startswith(b"20"):  # personas jurídicas
                continue
            ruc = linea[:11].decode()
            en_ruc = ruc in por_ruc
            if not en_ruc and not filtro.search(linea.upper()):
                continue
            partes = linea.decode("latin-1").split("|")
            nombre, estado, condicion = partes[1].strip(), partes[2].strip(), partes[3].strip()
            if en_ruc:
                filas.append({"empresa_id": por_ruc[ruc], "ruc": ruc, "razon_social_sunat": nombre,
                              "estado": estado, "condicion": condicion, "cruce": "por RUC"})
                continue
            c = clave(nombre)
            if c in por_clave:
                filas.append({"empresa_id": por_clave[c], "ruc": ruc, "razon_social_sunat": nombre,
                              "estado": estado, "condicion": condicion, "cruce": "por nombre"})

    df = pd.DataFrame(filas)
    # Si una empresa ya tenía RUC, manda ese. Si por nombre hay varios RUC, se prefiere el ACTIVO
    # y se marca para verificar.
    df["orden"] = (df["cruce"] != "por RUC").astype(int) * 10 + (df["estado"] != "ACTIVO").astype(int)
    df = df.sort_values(["empresa_id", "orden"])
    varios = df[df["cruce"] == "por nombre"].groupby("empresa_id")["ruc"].nunique()
    df = df.drop_duplicates("empresa_id").drop(columns="orden")
    df["varios_ruc_mismo_nombre"] = df["empresa_id"].map(varios).fillna(1).astype(int) > 1
    df.to_csv(PROC / "empresa_sunat.csv", index=False)

    sin_ruc = set(emp.loc[emp["ruc"].isna(), "empresa_id"])
    print(f"Empresas en el padrón: {len(df)} de {len(emp)}")
    print(f"RUC nuevos (antes sin RUC): {df['empresa_id'].isin(sin_ruc).sum()} de {len(sin_ruc)}")
    print(df["estado"].value_counts().to_string())


if __name__ == "__main__":
    main()
