# Verificación manual de cifras del informe final

Instrucciones: compruebe cada cifra con la fuente indicada, sin usar el agente, y llene las tres últimas columnas.

| # | Afirmación del informe | Fuente | Valor del informe | Cómo verificarlo | Valor verificado | ¿Coincide? | Diferencia / nota |
|---|---|---|---|---|---|---|---|
| 1 | Pobreza monetaria nacional 2024 (personas, ponderada con `facpob07`) | ENAHO | **27.53 %** | Revisar `salidas/validacion.txt` y compararlo con la cifra oficial del INEI (27.6 %, Informe Técnico de Pobreza 2024) | 27.53 % en `salidas/validacion.txt`; INEI: 27.6 % | Sí | 0.07 pp, dentro de la tolerancia |
| 2 | Ingresos por canon y regalías del gobierno general en 2024 (`PN37897FM`, suma de enero a diciembre) | BCRP | **6,743.3 millones de S/** | Abrir <https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PN37897FM/json/2024-1/2024-12>, copiar los 12 valores a Excel y sumarlos | 6,743 millones de S/ (suma de los 12 meses en la web del BCRP) | Sí | Solo diferencia de redondeo |
| 3 | Producción de cobre de Moquegua en 2024, el mayor productor de cobre (`RD15529DA`) | BCRP | **475,929.95 tm.f** (valor estimado: 4,035.68 millones de US$ con un precio promedio de 384.627169 según `PN38784BM`) | Abrir la serie RD15529DA en estadisticas.bcrp.gob.pe (año 2024) y compararla con Arequipa (RD15519DA) y Áncash (RD15517DA) | 475,930 tm.f (web del BCRP, RD15529DA) | Sí | Solo diferencia de redondeo. Al principio consulté por error RD15530DA, que corresponde a Pasco; luego corregí a RD15529DA (Moquegua) |
| 4 | Pobreza de Cajamarca 2024, el departamento más pobre | ENAHO | **44.99 %** | Revisar `salidas/pobreza_departamento_mapa.csv` y la referencia del curso (45.0 %) | 45.0 % (referencia de la Sesión 16) | Sí | 0.01 pp |

Notas de la revisión:

- Las cuatro cifras coinciden con sus fuentes, con diferencias de redondeo o menores a 0.1 pp.
- En la cifra 3 hubo un error de consulta: el código RD15530DA es de Pasco, no de Moquegua. Un código vecino da
  otro departamento, así que conviene confirmar el nombre de la serie antes de comparar.
- La cifra 3 viene de `produccion_minera_departamental` (fila cobre, ccdd 18). El precio está en las unidades que
  usa la serie del BCRP; compruébelas en la página de la serie.
