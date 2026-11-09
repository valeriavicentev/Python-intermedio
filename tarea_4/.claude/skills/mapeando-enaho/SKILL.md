---
name: mapeando-enaho
description: Hace el mapa coroplético de la pobreza monetaria por departamento con la ENAHO 2024 del INEI y, encima, las unidades mineras del Perú como puntos. Une por código (ubigeo[:2] con FIRST_IDDP), exige los 25 departamentos con Lima y Callao separados y compara con la referencia del curso. Úsala cuando pidan un mapa de pobreza, de regiones o de minería y pobreza.
argument-hint: [--sin-minas]
---
# Mapear la ENAHO

1. Si no existe `salidas/personas_2024.parquet`, usa primero la skill `limpiando-enaho`.
2. Corre exactamente: `uv run ${CLAUDE_SKILL_DIR}/scripts/mapear.py` (agrega `--sin-minas` si piden solo pobreza).
3. El script une `ccdd` (= `ubigeo[:2]`) con `FIRST_IDDP` como texto — nunca por nombre —, se detiene si no
   hay 25 departamentos con dato y compara cada valor con `pobreza_departamento_2024.csv` (referencia de la
   Sesión 16). Reporta la diferencia máxima que imprime.
4. Responde con la ruta `mapas/pobreza_departamento.png` y los departamentos de mayor y menor pobreza.
