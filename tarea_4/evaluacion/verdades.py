"""Calcula las respuestas esperadas que faltan en preguntas.csv, SIN usar el MCP ni las Skills.

    uv run evaluacion/verdades.py

Llama directo a la API del BCRP con httpx y usa la referencia departamental de la Sesión 16. Se corre UNA vez,
antes de evaluar, y no se vuelve a tocar después de ver las respuestas del agente.
"""
import unicodedata
from pathlib import Path

import httpx
import pandas as pd

AQUI = Path(__file__).parent
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
REF = AQUI.parent / ".claude" / "skills" / "mapeando-enaho" / "pobreza_departamento_2024.csv"
CCDD = {"ancash": "02", "apurimac": "03", "arequipa": "04", "ayacucho": "05", "cajamarca": "06", "cusco": "08",
        "huancavelica": "09", "huanuco": "10", "ica": "11", "junin": "12", "la libertad": "13", "lambayeque": "14",
        "lima": "15", "madre de dios": "17", "moquegua": "18", "pasco": "19", "puno": "21", "tacna": "23"}


def anual(codigos, anio=2024):
    r = httpx.get(f"{API}/{'-'.join(codigos)}/json/{anio}/{anio}", timeout=60).json()
    nombres = [s["name"] for s in r["config"]["series"]]
    return dict(zip(nombres, map(float, r["periods"][0]["values"])))


if __name__ == "__main__":
    q = pd.read_csv(AQUI / "preguntas.csv", dtype={"verdad": "float"})
    ref = pd.read_csv(REF, dtype={"ccdd": str}).set_index("ccdd").pobreza_pct
    cobre = anual(["PM05146AA"])
    q.loc[q.id == "bcrp_cobre_prod_2024", "verdad"] = round(list(cobre.values())[0], 2)
    # series departamentales anuales de 2024 (catálogo BCRP): cobre RD15516DA-RD15532DA, oro RD15543DA-RD15560DA
    cu = [f"RD{n}DA" for n in range(15516, 15533)]
    au = [f"RD{n}DA" for n in range(15543, 15561)]
    for qid, cods in (("mixta_cobre", cu), ("mixta_oro", au)):
        todos = {}
        for i in range(0, len(cods), 10):
            todos.update(anual(cods[i:i + 10]))
        nombre = max((k for k in todos if "Total" not in k), key=todos.get)
        depto = nombre.split(" - ")[-1].split("(")[0].strip()
        cd = CCDD[unicodedata.normalize("NFD", depto.lower()).encode("ascii", "ignore").decode()]
        q.loc[q.id == qid, "verdad"] = ref[cd]
        q.loc[q.id == qid, "fuente_verdad"] += f" → {depto} ({todos[nombre]:,.0f}); pobreza {ref[cd]} %"
        print(f"{qid}: {depto} produjo {todos[nombre]:,.0f}; pobreza {ref[cd]} %")
    print(f"bcrp_cobre_prod_2024: {q.loc[q.id == 'bcrp_cobre_prod_2024', 'verdad'].item()} miles de t")
    q.to_csv(AQUI / "preguntas.csv", index=False)
    print("preguntas.csv completo:", q.verdad.notna().sum(), "de", len(q), "respuestas esperadas")
