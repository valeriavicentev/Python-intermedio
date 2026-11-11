# Datos

## Fuentes (data/raw/)

| Archivo | Qué es | Origen |
|---|---|---|
| `MINING.csv` | 142 unidades mineras en producción: titular, producto, coordenadas | MINEM, vía dataset de la sesión 06 del curso ([Hugging Face `aquiro1994/ds-python-up`](https://huggingface.co/datasets/aquiro1994/ds-python-up)) |
| `Poverty.csv` | Pobreza monetaria por distrito; PBI per cápita e IDH por departamento | INEI, mismo dataset |
| `peru_distrital_simple.geojson` | Límites distritales simplificados | Mismo dataset |
| `oefa/multas_firmes_2019_2025.csv` | Resoluciones con multa firme (filas de 2024 y 2025) | [OEFA datos abiertos](https://datosabiertos.oefa.gob.pe/dataviews/262240/resolucion-con-multa-firmes-2019-2025/), descarga manual |
| `oefa/oefa_ruias.csv` + diccionario | Registro Único de Infractores Ambientales Sancionados, con RUC | [Plataforma Nacional de Datos Abiertos](https://www.datosabiertos.gob.pe/dataset/registro-%C3%BAnico-de-infractores-ambientales-sancionados-organismo-de-evaluaci%C3%B3n-y), con `scripts/descargar_datos.py` |
| `oxi/oxi_adjudicados_concluidos.xlsx` | Inversiones en ejecución y concluidas por Obras por Impuestos 2009–2025, con empresas financistas | ProInversión, descarga manual |
| `oxi/oxi_ranking_empresas.xlsx` | Ranking de empresas por monto invertido en OxI 2009–2025, con RUC | ProInversión, descarga manual |
| `oxi/oxi_convocatorias_20261110.xlsx` | Convocatorias OxI en proceso y adjudicadas (sin empresa financista; no se usa en el cruce) | ProInversión, descarga manual |
| `minem/anuario_minero_2025_anexos.xlsx` | Anexos del Anuario Minero 2025: producción por empresa (cobre, oro, zinc, plata, plomo, molibdeno, hierro, estaño), inversión por empresa y transferencias de canon, regalías y derecho de vigencia por departamento | MINEM, descarga manual |
| `manual/ubicaciones_manuales.csv` | Distrito de siete productoras que no están en la lista del MINEM ni tienen distrito en el OEFA, con la fuente pública de cada una | Búsqueda propia |
| `defensoria/reporte_conflictos_268.pdf` … `270.pdf` | Reportes mensuales de conflictos sociales (julio a agosto 2026) | [Defensoría del Pueblo](https://www.defensoria.gob.pe/categorias_de_documentos/reportes/), con `scripts/descargar_datos.py` |

## Procesados (data/processed/)

Salidas de `scripts/preparar_datos.py` y `scripts/preparar_empresas.py`. Todas las
tablas de empresa llevan `empresa_id`. `empresa_alias.csv` registra con qué nombre
aparece cada empresa en cada fuente y cómo se unió (por RUC o por nombre exacto
normalizado).

**Pendiente de verificar:** el año de referencia de la pobreza distrital y de la lista
de unidades mineras; los archivos no lo indican.
