---
name: cruzando-mineria
description: Cruza la producción minera por departamento del BCRP (herramienta MCP produccion_minera_departamental) y el canon minero transferido (MEF) con la pobreza monetaria de la ENAHO 2024. Produce una tabla por departamento, un gráfico de dispersión y correlaciones descriptivas. Úsala cuando pregunten si las regiones mineras son más o menos pobres, cuánto produce la minería frente al canon que recibe una región, o por la relación minería-pobreza.
---
# Cruzar minería, canon y pobreza

1. Si no existe `salidas/personas_2024.parquet`, usa primero la skill `limpiando-enaho`.
2. Si no existe `salidas/produccion_minera_2024.csv`, llama a la herramienta MCP
   `produccion_minera_departamental(anio=2024)` del servidor `bcrp` (con `guardar=true`). Si el MCP no está
   disponible, dilo y detente: no inventes la producción.
3. Corre exactamente: `uv run ${CLAUDE_SKILL_DIR}/scripts/cruzar.py --anio 2024`
4. El canon es opcional: el script lo lee de `datos/canon_minero_2024.csv` (columnas `ccdd,canon_minero_soles`,
   exportado del MEF). Si el archivo no está, el script lo dice; repórtalo como limitación y no estimes el canon.
5. Responde con las cifras que imprime el script, citando el código de serie del BCRP y «INEI, ENAHO 2024».
   Las correlaciones con 25 (o menos) departamentos son **descriptivas**: nunca digas que la minería causa o
   reduce la pobreza.
