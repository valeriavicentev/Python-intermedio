"""¿Mejoran MCP y Skills las respuestas de Claude Code? Las mismas 10 preguntas en dos modos, en sesiones aisladas.

    uv run evaluacion/verdades.py          # una vez, antes: completa las respuestas esperadas
    uv run evaluacion/evaluar.py           # modos A (sin) y B (con), modelo sonnet
    uv run evaluacion/evaluar.py --modelo haiku --paralelo 2

Modo A «sin»: sin herramientas de Claude Code, sin MCP y sin Skills (--tools "" --strict-mcp-config).
Modo B «con»: el MCP del BCRP (.mcp.json) + Skills + Bash/Read/Glob para correr los scripts de las Skills.
              Se le prohíbe leer evaluacion/ para que no vea las respuestas esperadas.
Cada pregunta corre con claude -p --no-session-persistence (sesión nueva, sin memoria de las anteriores).
Escribe evaluacion/resultados.csv y evaluacion/comparacion_auto.md.
"""
import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
RAIZ = AQUI.parent
ESQUEMA = {"type": "object", "required": ["valor", "fuente"],
           "properties": {"valor": {"type": ["number", "null"]}, "unidad": {"type": "string"},
                          "fuente": {"type": "string"}}}
INSTRUCCION = ("Responde con un solo número en «valor», en la unidad que pide la pregunta. Si no puedes saberlo "
               "con certeza, pon valor null: no estimes. En «fuente» di de dónde sale la cifra (serie, archivo o "
               "cálculo). No leas la carpeta evaluacion/.\n\n")
MODOS = {
    "sin": ["--tools", "", "--strict-mcp-config", "--disallowedTools", "Skill"],
    "con": ["--strict-mcp-config", "--mcp-config", str(RAIZ / ".mcp.json"),
            "--tools", "Bash,Read,Glob,Grep,Skill",
            "--allowedTools", "mcp__bcrp", "Skill", "Read", "Glob", "Grep", "Bash(uv run:*)", "Bash(ls:*)",
            "--disallowedTools", "Read(./evaluacion/**)", "Grep(./evaluacion/**)", "Bash(cat:*)"],
}
HERRAMIENTAS_HABILITADAS = {"sin": "ninguna (solo el conocimiento del modelo)",
                            "con": "MCP bcrp (6 herramientas), Skills del proyecto, Bash(uv run/ls), Read, Glob, Grep"}


def preguntar(pregunta, modo, modelo):
    cmd = ["claude", "-p", INSTRUCCION + pregunta, "--output-format", "stream-json", "--verbose",
           "--json-schema", json.dumps(ESQUEMA), "--no-session-persistence", "--model", modelo, *MODOS[modo]]
    t = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=RAIZ)
        salida = proc.stdout
    except subprocess.TimeoutExpired as e:
        salida = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    usadas, final = [], {}
    for linea in salida.splitlines():
        try:
            ev = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for bloque in ev.get("message", {}).get("content", []):
                if bloque.get("type") == "tool_use":
                    nombre = bloque["name"]
                    if nombre == "Skill":
                        nombre = f"Skill:{bloque.get('input', {}).get('skill', '?')}"
                    usadas.append(nombre)
        elif ev.get("type") == "result":
            final = ev
    r = final.get("structured_output") or {}
    return {"valor": r.get("valor"), "unidad": r.get("unidad", ""),
            "fuente": r.get("fuente", (final.get("result") or salida[-300:])),
            "herramientas": ";".join(dict.fromkeys(usadas)), "segundos": round(time.time() - t, 1),
            "turnos": final.get("num_turns"), "error": "" if final else "sin respuesta / timeout"}


def calificar(valor, verdad, tolerancia):
    if valor is None:
        return "no sabe"
    return "acierta" if abs(float(valor) - verdad) <= tolerancia else "se equivoca"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--modos", nargs="+", default=["sin", "con"], choices=list(MODOS))
    p.add_argument("--modelo", default="sonnet")
    p.add_argument("--paralelo", type=int, default=2)
    a = p.parse_args()
    q = pd.read_csv(AQUI / "preguntas.csv")
    if q.verdad.isna().any():
        raise SystemExit("Faltan respuestas esperadas: corre primero  uv run evaluacion/verdades.py")
    casos = [(f, m) for f in q.itertuples() for m in a.modos]
    print(f"{len(casos)} llamadas a claude -p con {a.modelo}...")
    with ThreadPoolExecutor(a.paralelo) as ex:
        resp = list(ex.map(lambda c: preguntar(c[0].pregunta, c[1], a.modelo), casos))
    filas = [{"id": f.id, "tipo": f.tipo, "modo": m, "pregunta": f.pregunta, "verdad": f.verdad,
              "tolerancia": f.tolerancia, **r, "resultado": calificar(r["valor"], f.verdad, f.tolerancia),
              "herramientas_habilitadas": HERRAMIENTAS_HABILITADAS[m], "modelo": a.modelo}
             for (f, m), r in zip(casos, resp)]
    res = pd.DataFrame(filas)
    res.to_csv(AQUI / "resultados.csv", index=False)

    tabla = res.groupby("modo").resultado.value_counts().unstack(fill_value=0)
    tabla["segundos_promedio"] = res.groupby("modo").segundos.mean().round(1)
    por_tipo = res.pivot_table(index="tipo", columns="modo", values="resultado",
                               aggfunc=lambda s: (s == "acierta").sum())
    piv = res.pivot(index="id", columns="modo", values="resultado")
    md = [f"# Comparación automática ({a.modelo})", "", tabla.to_markdown(), "", "## Aciertos por tipo", "",
          por_tipo.to_markdown(), "", "## Resultado por pregunta", "", piv.to_markdown()]
    if {"sin", "con"} <= set(piv.columns):
        mejora = piv[(piv.sin != "acierta") & (piv.con == "acierta")].index.tolist()
        empeora = piv[(piv.sin == "acierta") & (piv.con != "acierta")].index.tolist()
        md += ["", f"Mejoraron con MCP/Skills: {mejora or 'ninguna'}", f"Empeoraron: {empeora or 'ninguna'}"]
    (AQUI / "comparacion_auto.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
