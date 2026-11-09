# Prompt de la ejecución integrada (copiar y pegar en Claude Code, dentro de tarea_4/)

> **Pregunta de investigación:** ¿Son más pobres los departamentos y distritos donde se concentra la minería
> metálica en el Perú, y cuánto valor produce esa minería frente al canon minero que reciben sus regiones (2024)?
>
> Prepara primero un plan breve. Luego:
> 1. Con el MCP `bcrp`: llama a `produccion_minera_departamental(anio=2024)`; usa `resumen` con PN01760AM
>    (índice de minería metálica, 2015-01 a 2025-12) y con PN37897FM (canon y regalías, 2024-01 a 2024-12, usa la
>    suma) y con PN02229FM (transferencias por canon del gobierno central, 2024, suma); usa `resumen` con PD04638PD (tipo de cambio, 2024-01-01 a 2024-12-31) para el promedio; y
>    `graficar_serie` con PN01760AM 2015-01 a 2025-12.
> 2. Con las Skills: `limpiando-enaho` (y revisa la validación), `graficando-enaho --tipo todos`,
>    `mapeando-enaho` y `cruzando-mineria` pasando `--tc` con el promedio del tipo de cambio que te dio el MCP.
> 3. Escribe `informes/informe_final.md` con: pregunta y delimitación; fuentes y metodología; al menos 3
>    hallazgos con cifras citadas (código de serie o archivo de salidas/); las figuras `figuras/bcrp_PN01760AM.png`,
>    `figuras/pobreza_mineria.png`, `figuras/mineria_vs_pobreza.png` y `mapas/pobreza_departamento.png`;
>    interpretación; limitaciones (ENAHO no encuesta campamentos, no es representativa por distrito, valor de
>    producción aproximado con precios de exportación, canon solo si existe datos/canon_minero_2024.csv);
>    reproducibilidad (comandos y series).
> 4. Al final escribe `informes/verificacion.md` con 3 afirmaciones numéricas del informe (al menos una del BCRP
>    y una de la ENAHO) dejando espacio para que yo las compruebe a mano.
> No inventes cifras: si algo falla, repórtalo.
