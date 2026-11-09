# Tarea 4 · Agente de investigación: minería, canon y pobreza en el Perú

**Estudiante:** Valeria Vicente (@valeriavicentev) · Python Intermedio, d2cml-ai · Issue #201

## 1. Objetivo

Construir un agente en Claude Code que responda, con datos oficiales y cálculos reproducibles:

> **¿Son más pobres los departamentos y distritos donde se concentra la minería metálica en el Perú, y cuánto
> valor produce esa minería frente al canon minero que reciben sus regiones (2024)?**

Combina el **BCRP** (producción minera por departamento, precios de metales, canon y regalías, actividad minera)
vía un servidor **MCP**, y la **ENAHO 2024** del INEI (pobreza monetaria, zonas y hogares mineros) vía **Skills**.
Todas las asociaciones son descriptivas: no se afirma causalidad.

## 2. Arquitectura

```
Pregunta en lenguaje natural
        │
   Claude Code (CLAUDE.md: reglas del agente)
        ├── MCP bcrp (mcp/server.py) ──► API del BCRP ──► producción minera, precios, canon, gráficos
        │                                   └─► salidas/produccion_minera_2024.csv
        └── Skills (.claude/skills/)
              limpiando-enaho ──► salidas/personas_2024.parquet, indicadores.csv, validacion.txt
              graficando-enaho ─► figuras/pobreza_*.png
              mapeando-enaho ───► mapas/pobreza_departamento.png (con unidades mineras)
              cruzando-mineria ─► salidas/cruce_mineria_2024.csv, figuras/mineria_vs_pobreza.png
        │
   informes/informe_final.md  +  informes/verificacion.md
```

## 3. Herramientas MCP (`mcp/server.py`)

| Herramienta | Qué hace |
|---|---|
| `buscar_series` | Busca códigos en el catálogo oficial del BCRP (17 mil series) |
| `serie` | Descarga una serie entre dos fechas (mensual, trimestral, diaria, anual) |
| `resumen` | Primero, último, cambio, variación %, promedio, **suma**, máximo y mínimo |
| `produccion_minera_departamental` **(propia)** | Producción de cobre, oro, plata, zinc, plomo y molibdeno por departamento (series anuales RD…DA, una llamada por cada 10 series), valorizada en millones de US$ con el precio promedio de exportación del año (PN387…BM); comprueba que la suma de departamentos reproduzca la serie «Total» y guarda `salidas/produccion_minera_<año>.csv` |
| `graficar_serie` **(propia)** | Guarda un PNG de una serie oficial en `figuras/` con código, periodo y fuente |
| `comparar_paises` | Banco Mundial (de la Sesión 04) |
| Recurso `bcrp://serie/{codigo}` | Ficha descriptiva de una serie |
| Prompts `informe(tema)`, `informe_minero(anio)` | Informes reutilizables que exigen citar código y periodo |

Series clave: PN01760AM (índice de minería metálica), PM05146AA (producción nacional de cobre), PN37897FM
(canon y regalías, ingresos del gobierno general), PN02229FM (transferencias por canon), PD04638PD (tipo de
cambio), RD15516DA–RD15560DA (cobre y oro por departamento).

## 4. Skills (`.claude/skills/`)

| Skill | Entra | Sale |
|---|---|---|
| `limpiando-enaho` | Módulos 34, 02 y 05 de la ENAHO 2024 + `datos/unidades_mineras.csv` | Base de personas, indicadores y `validacion.txt` (se detiene si falla) |
| `graficando-enaho` | La base limpia | Pobreza por área, sexo, departamento y zonas/hogares mineros |
| `mapeando-enaho` | La base limpia + GeoJSON del curso | Coroplético por `ubigeo[:2]`↔`FIRST_IDDP`, 25 departamentos, unidades mineras como puntos, comparación con la referencia de la Sesión 16 |
| `cruzando-mineria` (adicional) | Salida del MCP + base limpia + canon (opcional) | Tabla departamental, correlaciones descriptivas, pobreza en distritos mineros vs. resto |

Las Skills de gráficos, mapas y cruce ejecutan primero `limpiando-enaho` si no existe la base procesada.

**Cómo se define «zona minera»:**
1. *Distrito minero*: el `ubigeo` del hogar tiene una unidad minera metálica (subterránea o superficial) del
   listado del MINEM del repositorio del curso (`sessions/06-geoespacial/lab/Data/MINING.csv`, 91 unidades
   metálicas en 69 distritos).
2. *Hogar minero*: algún residente ocupado trabaja en minería (CIIU rev. 4: divisiones 05, 07, 08 y 0990; módulo 05).

## 5. Datos

| Fuente | Archivo | Dónde va |
|---|---|---|
| INEI ENAHO 2024 módulo 34 | [966-Modulo34.zip](https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo34.zip) | `datos/` |
| INEI ENAHO 2024 módulo 02 | [966-Modulo02.zip](https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo02.zip) | `datos/` |
| INEI ENAHO 2024 módulo 05 (empleo) | [966-Modulo05.zip](https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo05.zip) | `datos/` |
| Límites departamentales | GeoJSON del curso (ya incluido en `.claude/skills/mapeando-enaho/`) | — |
| Unidades mineras (MINEM) | `MINING.csv` del curso, copiado como `datos/unidades_mineras.csv` (incluido) | — |
| BCRP | API pública, sin clave; el catálogo se descarga solo a `datos/catalogo_bcrp.csv` | — |
| Canon minero por departamento (opcional) | MEF, Transparencia Económica → transferencias → canon minero 2024 por departamento, guardado como `datos/canon_minero_2024.csv` con columnas `ccdd,canon_minero_soles` | `datos/` |

Los microdatos no se suben a GitHub (`.gitignore`).

## 6. Instalación

```bash
cd tarea_4
uv sync
```

## 7. Conectar el MCP a Claude Code

`.mcp.json` ya lo declara (`uv run mcp/server.py`). Al abrir `claude` dentro de `tarea_4/` aprueben el servidor
`bcrp` y compruébenlo con `/mcp`. Equivalente: `claude mcp add --scope project bcrp -- uv run mcp/server.py`.

## 8. Reproducir

```bash
uv run pytest -q                                                       # 10 passed
uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio 2024   # validación ENAHO
uv run .claude/skills/graficando-enaho/scripts/graficar.py --tipo todos
uv run .claude/skills/mapeando-enaho/scripts/mapear.py
# producción minera: desde Claude Code con el MCP, o sin él:
uv run python -c "import sys; sys.path.insert(0,'mcp'); import server; server.produccion_minera_departamental(2024)"
uv run .claude/skills/cruzando-mineria/scripts/cruzar.py --anio 2024 --tc <promedio PD04638PD 2024>
uv run evaluacion/verdades.py && uv run evaluacion/evaluar.py         # experimento con y sin MCP/Skills
```

La ejecución integrada (MCP + Skills en una sola sesión) se hace con el prompt de
[`agente/prompt_investigacion.md`](agente/prompt_investigacion.md).

## 9. Resultados de la evaluación

10 preguntas (4 BCRP, 4 ENAHO, 2 mixtas) en `evaluacion/preguntas.csv`; respuestas esperadas de valores
verificados en las sesiones 04 y 16 o calculadas con `evaluacion/verdades.py` (API del BCRP directa, sin MCP).
Resultados en `evaluacion/resultados.csv` y análisis en [`evaluacion/comparacion.md`](evaluacion/comparacion.md).

| Modo | Correctas | Incorrectas | No sabe | Tiempo promedio |
|---|---|---|---|---|
| A · sin MCP ni Skills | 0 | 0 | 10 | 5.2 s |
| B · con MCP y Skills | 9 | 1 | 0 | 14.1 s |

En el modo A el modelo responde «no sabe» en las 10 preguntas porque la instrucción le pide no estimar. El único
error del modo B (`bcrp_cobre_prod_2024`) fue de elección de serie: usó RD15516DA (2,732.64 miles de tm.f) en lugar
de PM05146AA (2,469.68).

## 10. Limitaciones

- La ENAHO **no encuesta viviendas colectivas**: los campamentos mineros no están en la muestra; solo los
  trabajadores mineros que son residentes habituales de un hogar particular.
- La ENAHO es representativa por departamento y área, **no por distrito ni provincia**: los resultados de
  distritos mineros son descriptivos y se reportan con su tamaño de muestra.
- El valor de la producción es una **aproximación** (cantidad × precio promedio de exportación), no el valor
  bruto de producción oficial; cubre solo metales con serie departamental.
- El BCRP publica canon y regalías **a nivel nacional**; el canon por departamento viene del MEF y es opcional.
- El listado de unidades mineras es un corte del MINEM del repositorio del curso, no necesariamente de 2024.
- Datos de corte transversal con 25 departamentos: correlaciones descriptivas, sin causalidad.
- El mapa usa pobreza ponderada con `facpob07` y difiere hasta **0.52 pp** de la referencia de la Sesión 16
  (Puno: 40.42 % frente a 39.9 %).
- En la salida del MCP `produccion_minera_departamental`, Apurímac aparece **duplicado** («Apurimac» y «Apurímac»),
  porque la serie de plata trae el nombre con tilde. No afecta el total, porque `cruzando-mineria` agrupa por el
  código `ccdd` (2,877.1 millones de US$ en 2024).

## 11. Ejemplo de ejecución completa

Ver `evidencias_ia/integracion/` (transcripción de la sesión de Claude Code que usó `produccion_minera_departamental`,
`resumen`, `graficar_serie` y las Skills `limpiando-enaho`, `graficando-enaho`, `mapeando-enaho` y `cruzando-mineria`).

## 12. Evidencias del uso de IA

`evidencias_ia/` contiene las conversaciones exportadas: `mcp/` (servidor), `skills/`, `integracion/` y
`evaluacion/`, con claves y datos personales ocultos. El proyecto se desarrolló con Claude (claude.ai) y se
ejecutó con Claude Code.
