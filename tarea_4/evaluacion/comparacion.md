# Comparación: Claude Code sin y con MCP/Skills

> Basado en `evaluacion/resultados.csv` y `evaluacion/comparacion_auto.md`, que genera `uv run evaluacion/evaluar.py`.
> Modelo evaluado: haiku.

## Diseño
- 10 preguntas fijas (`preguntas.csv`): 4 BCRP, 4 ENAHO, 2 mixtas. Respuestas esperadas definidas **antes** de
  correr el agente (valores verificados de las sesiones 04 y 16 y `verdades.py`, que llama a la API del BCRP sin MCP).
- Tolerancias fijadas de antemano en `preguntas.csv`.
- Mismo modelo y misma instrucción en ambos modos; cada pregunta en una sesión nueva (`--no-session-persistence`).
- Modo A: sin herramientas, sin MCP, sin Skills. Modo B: MCP `bcrp` + Skills + Bash(uv run)/Read/Glob/Grep,
  con lectura de `evaluacion/` bloqueada.
- Mixtas: correcta si la cifra está dentro de la tolerancia **y** la fuente identifica al departamento correcto.

## Resultados
| Modo | Correctas | Incorrectas | No sabe | Tiempo promedio (s) |
|---|---|---|---|---|
| A · sin | 0 | 0 | 10 | 5.2 |
| B · con | 9 | 1 | 0 | 14.1 |

Aciertos por tipo en el modo B: BCRP 3 de 4, ENAHO 4 de 4, mixtas 2 de 2. En el modo A: 0 en todos los tipos.

**Por qué el modo A responde «no sabe» en las 10:** la instrucción del agente (`CLAUDE.md`) le pide no estimar
ni escribir cifras de memoria, y solo aceptar cifras del MCP `bcrp` o de las Skills de la ENAHO. Sin esas
herramientas, el modelo declaró en cada caso que no podía consultar la fuente y no dio ningún valor. Por eso el
modo A no tiene respuestas incorrectas: no hubo alucinaciones, pero tampoco respuestas útiles.

## Preguntas que mejoraron / empeoraron
- **Mejoraron (9):** pasaron de «no sabe» (A) a «acierta» (B) `bcrp_ipc_set26`, `bcrp_cobre_precio_ago26`,
  `bcrp_pbi_2025`, `enaho_nacional`, `enaho_rural`, `enaho_cajamarca`, `enaho_moquegua`, `mixta_cobre` y
  `mixta_oro`.
- **Empeoraron (0):** ninguna. `bcrp_cobre_prod_2024` pasó de «no sabe» a «se equivoca»; no cuenta como
  mejora y se analiza abajo.

## Principales errores
- **`bcrp_cobre_prod_2024` (modo B, se equivoca).** La pregunta pide la producción de cobre del Perú en 2024 en
  miles de toneladas métricas finas.
  - **Respuesta esperada:** **2,469.68**, de la serie nacional **PM05146AA** (año 2024), calculada por
    `verdades.py` con la API del BCRP. Tolerancia: ±10.
  - **Respuesta del modo B:** **2,732.64**. Buscó y usó **RD15516DA**, «Producción de productos mineros según
    departamentos – Cobre – Total (tm.f)», cuyo valor para 2024 es 2,732,642.16 tm.f, y lo dividió entre 1,000.
    URL: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/RD15516DA/json/2024/2024`.
  - **Diagnóstico:** el cálculo es correcto para esa serie, pero eligió una serie distinta a la de referencia. El
    BCRP publica dos medidas de producción de cobre que no coinciden: la serie nacional PM05146AA y el total de
    las series departamentales del MINEM (RD…DA). El agente tomó la segunda porque `buscar_series` la encontró y
    porque está ligada a la herramienta `produccion_minera_departamental`. La diferencia supera la tolerancia.
    No se verificó qué explica la brecha entre ambas series (cobertura o definición de «fino»).
  - **Corrección posible:** indicar en `CLAUDE.md` o en la descripción del MCP que, para la producción
    **nacional**, se use PM05146AA, y que las series RD…DA son solo para comparar departamentos.
- **Diferencias menores dentro de la tolerancia:** por ejemplo, la pobreza nacional de 27.53 % frente a 27.6 % y la
  de Moquegua de 10.88 % frente a 11.0 %. Vienen de redondeos de la referencia, no son errores.

## Conclusión
- **Exactitud:** con MCP y Skills el agente pasa de 0 a 9 respuestas correctas de 10. Cita en cada caso el código
  de serie, el periodo, la URL o el archivo de `salidas/`, y los valores de la ENAHO van ponderados con `facpob07`
  y validados.
- **Costo:** tarda más en promedio (14.1 s frente a 5.2 s), porque hace de 4 a 10 turnos para consultar
  herramientas.
- **Sin herramientas:** la regla de no estimar funcionó como se esperaba. El modelo prefirió decir «no sabe»
  antes que inventar cifras.
- **Único error:** fue de elección de serie, no de cálculo. Muestra que el acceso a datos oficiales no basta:
  la instrucción debe precisar qué serie corresponde a cada concepto cuando el BCRP publica más de una.
