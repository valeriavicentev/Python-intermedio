---
name: limpiando-enaho
description: Limpia los módulos 34 (sumaria), 02 (miembros) y 05 (empleo) de la ENAHO 2024 del INEI y arma una base de personas con pobreza monetaria, departamento, área, factor de expansión e indicadores de minería (distritos con unidades mineras y hogares con trabajadores mineros). Úsala cuando pidan limpiar, unir o validar la ENAHO, o calcular pobreza por región, área, sexo o en zonas mineras.
argument-hint: [año]
---
# Limpiar la ENAHO

1. Comprueba que existan `datos/966-Modulo34.zip` y `datos/966-Modulo02.zip` (y, para el empleo minero,
   `datos/966-Modulo05.zip`). Si faltan, pide al usuario que los baje del INEI (código 966 = 2024) y detente.
2. Corre exactamente, desde la raíz del proyecto:
   `uv run ${CLAUDE_SKILL_DIR}/scripts/limpiar.py --anio 2024` (por ahora solo está configurado 2024)
3. Lee `salidas/validacion.txt`. Si dice `FALLIDO`, o la pobreza nacional difiere de 27.6 % en más de 0.1
   puntos, **detente y reporta el error**: nunca ajustes cifras para que cuadren.
4. Responde con cifras de `salidas/indicadores.csv` o calculadas desde `salidas/personas_2024.parquet`,
   **siempre ponderadas con `facpob07`** (personas). Nunca uses promedios simples.
5. Informa el tamaño de muestra (`n_muestra`) cuando el grupo sea chico (< 300 personas): la ENAHO es
   representativa por departamento y área, no por distrito.
6. Antes de usar una variable que no está en la base, lee `reference.md`.
