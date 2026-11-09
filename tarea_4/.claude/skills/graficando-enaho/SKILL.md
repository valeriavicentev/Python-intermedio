---
name: graficando-enaho
description: Hace gráficos de pobreza monetaria con la ENAHO 2024 del INEI, ponderados con el factor de expansión: por área urbana y rural, por sexo, por departamento, y en zonas mineras (distritos con unidades mineras, hogares con trabajadores mineros). Úsala cuando pidan graficar, comparar o visualizar la pobreza de la ENAHO.
argument-hint: [area|sexo|departamento|mineria|todos]
---
# Graficar la ENAHO

1. Si no existe `salidas/personas_2024.parquet`, usa primero la skill `limpiando-enaho` y espera a que su
   validación diga APROBADO.
2. Elige el tipo según el pedido: `area` (urbano/rural), `sexo`, `departamento`, `mineria` o `todos`.
   Si el pedido pide otro grupo, dilo y usa el más cercano.
3. Corre exactamente: `uv run ${CLAUDE_SKILL_DIR}/scripts/graficar.py --tipo <tipo>`
4. El script imprime las cifras ponderadas (con `facpob07`) y las rutas en `figuras/`. Responde con esas cifras
   tal cual, cita «INEI, ENAHO 2024» y muestra la ruta del PNG.

Reglas que el script ya cumple (no las cambies): barras desde cero y ordenadas, valor escrito en cada barra,
título que dice qué y cuándo, unidad «% de personas», nota de fuente, PNG a 200 dpi. En los gráficos de minería
el script escribe el tamaño de muestra, porque la ENAHO no es representativa por distrito.
