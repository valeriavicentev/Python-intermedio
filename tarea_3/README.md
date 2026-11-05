# El dinero de El Niño (2023–2026)

**Tarea 3 · Python Intermedio (d2cml-ai)** · Valeria Vicente Vásquez

**Dashboard:** https://valeriavicentev.github.io/Python-intermedio/tarea_3/web/
**Publicación de LinkedIn:** _(pendiente)_

## 1. Tema y pregunta de investigación

Entre 2023 y 2026 el Estado peruano autorizó más de S/ 7 mil millones, mediante decretos de urgencia, decretos supremos y leyes, para prevenir y responder al Fenómeno El Niño (FEN). Ahora se declara un nuevo Niño costero.

> **¿A dónde se destinó el dinero autorizado por las normas FEN, quiénes lo ejecutaron (entidades y empresas contratistas) y en qué estado están las obras?**

Cobertura: Perú, años fiscales 2023, 2024 y 2026. El archivo de 2025 del MEF no tiene registros.

## 2. Descripción

El dashboard sigue el dinero en cuatro pasos:

1. **Cuándo:** la norma que lo autorizó y cuánto se devengó.
2. **Dónde:** el mapa del gasto por región y de las intervenciones listadas en los anexos de los decretos.
3. **Quién:** las unidades ejecutoras y los contratistas del SEACE.
4. **Obras:** el estado y el avance físico de los proyectos con código único de inversión (CUI).

Tiene 5 indicadores, 10 visualizaciones, 4 filtros globales (año, nivel de gobierno, departamento y tipo de norma), capas del mapa que se activan y desactivan, y una tabla con búsqueda y orden.

## 3. Fuentes y metodología

| Fuente | Qué aporta | Archivo |
|---|---|---|
| [MEF – Ejecución del gasto de emergencias FEN](https://www.datosabiertos.gob.pe/) (Datos Abiertos), descargado el 28/10/2026 | Marco y devengado por norma, ejecutora, departamento y genérica | `datos/originales/20XX-Gasto-Emergencias-FEN.csv` |
| MEF – Banco de Inversiones (detalle de inversiones), 3/11/2026 | Estado, avance físico, modalidad y coordenadas por CUI | `DETALLE_INVERSIONES.csv` (248 MB, no se sube) |
| MEF – Avance mensual por componente, 3/11/2026 | Valorizaciones y etapa por CUI | `PROCESO_SELECCION.csv` (1,2 GB, no se sube) |
| [MEF – Seguimiento de Inversiones (SSI)](https://ofi5.mef.gob.pe/ssi/), 4/11/2026 | Contratos del SEACE (OECE) e informes de la Contraloría por CUI | `datos/procesados/_contratos_grupos.txt`, `informes_control.csv` |
| [OECE – Contrataciones abiertas (OCDS)](https://data.open-contracting.org/en/publication/135), años 2023 y 2026, 4/11/2026 | Contratos, proveedores y procedimiento de las ejecutoras FEN (actividades sin CUI) | `datos/originales/ocds/` (no se sube) → `datos/procesados/seace_fen.csv` |
| [Contraloría – Infobras](https://infobras.contraloria.gob.pe/InfobrasWeb/), 4/11/2026 | Último avance físico, paralizaciones y comentarios de cada obra vinculada a un CUI | `datos/procesados/infobras_avance.csv` |
| Contraloría – fichas resumen de control simultáneo (vía ficha SSI) | 134 informes sobre 38 proyectos; situaciones adversas clasificadas por tipo | `datos/procesados/informes_control_detalle.csv`, `quebradas_cgr.csv` |
| [OECE – Ficha Única del Proveedor](https://apps.osce.gob.pe/perfilprov-ui/), 4/11/2026 | Sanciones del Tribunal de Contrataciones y penalidades de 132 proveedores con RUC | `datos/procesados/sanciones_tce.csv`, `penalidades_oece.csv` |
| Decretos de urgencia y anexos publicados en [El Peruano](https://diariooficial.elperuano.pe/) | Transferencias e intervenciones (puntos críticos, coordenadas UTM), sistematizadas a mano | `DU_Fenomeno_El_Nino_2023.xlsx`, `DU_Fenomeno_El_Nino_2026.xlsx` |
| INEI vía [juaneladio/peru-geojson](https://github.com/juaneladio/peru-geojson) | Límites departamentales y distritales | `peru_*.geojson` |

**Procesamiento** (`scripts/procesar_datos.py`):

- Se unen los archivos del MEF (4 833 líneas, sin duplicados) y se normalizan los nombres de las normas, los departamentos y los niveles de gobierno.
- Se agrega el gasto por norma, ejecutora, departamento, genérica y función. "Autorizado" es el marco presupuestal y "devengado" es el gasto reconocido.
- Los 49 CUI del archivo FEN se cruzan con el Banco de Inversiones y la ficha SSI de cada uno. De la ficha SSI se toman el estado, el registro de cierre, el avance físico, el devengado acumulado, el costo actualizado, las fechas de ejecución, los contratos del SEACE y los informes de control. La columna `PERIODO` del archivo de avance por componente es el cronograma programado, no la fecha de un reporte, por eso no se usa como fecha de avance. Un contrato se considera **previo** si su fecha de suscripción es anterior a la publicación de la norma FEN que financió el proyecto.
- Con `scripts/cruce_seace_ocds.py`, para las actividades sin CUI se toman los contratos del SEACE de las 20 ejecutoras con más gasto FEN firmados entre la publicación de la norma y el fin del año fiscal. Se clasifican en dos grupos: **cita FEN**, cuando el texto menciona El Niño, el decreto o el peligro inminente, y **tema**, cuando se trata de descolmatación, defensas ribereñas, quebradas, maquinaria o módulos de emergencia. El resto no se atribuye al FEN.
- Las 880 intervenciones de los anexos se ubican con sus coordenadas UTM (119) o con el centroide del distrito o la provincia. 40 no pudieron ubicarse.
- La coincidencia de puntos entre 2023 y 2026 viene de la hoja "Repeticiones 2023-2026", basada en el nombre del cauce, el distrito y la distancia entre coordenadas.

## 4. Hallazgos principales

1. **42 de los 58 contratos** vinculados a proyectos FEN se firmaron **antes** de la norma que les asignó el dinero: S/ 1 589 M de S/ 1 896 M. Puentes contratados en 2019 y obras de la Reconstrucción con Cambios de 2020–2021 recibieron fondos "por El Niño". Ese dinero financió obras que ya estaban en curso.
2. **21 quebradas de Lima Este** (ANA, Ley 31912 de 2023) recibieron S/ 49,4 M del FEN y figuran como **cerradas sin culminar** en el Banco de Inversiones. Según la Contraloría, el ejecutor fue el **Consorcio SQA - LGQ**, contratado por contratación directa sin contrato ni registro en el SEACE. Sus cartas fianza por adelanto directo suman S/ 7,16 M, casi lo mismo que el devengado FEN de las quebradas (S/ 7,16 M), y ninguna obra registra avance en Infobras. La Contraloría advirtió además que la ANA aprobó y pagó expedientes técnicos sin el contenido mínimo. El DU 008-2026 vuelve a asignar 12 barreras dinámicas en 10 de esas quebradas.
3. Del dinero autorizado para el nuevo Niño (S/ 2 508 M entre agosto y octubre de 2026), solo se había devengado el **14,9%** al 28 de octubre. En 2023 se llegó al 71,7%. El PSI recibió S/ 354 M y devengó 2,3%.
4. El **85,3% del monto** de los 202 contratos del SEACE identificados para las actividades FEN (S/ 449 M) se adjudicó por **contratación directa**. El mayor es de septiembre de 2026: S/ 34,6 M al Consorcio Barreras Dinámicas, para barreras en las quebradas de Lima Este.
5. **97 de 134 informes de control** de la Contraloría advierten situaciones adversas (193 en total) en 37 de los 46 proyectos: pagos y valorizaciones observados, expedientes técnicos deficientes, retrasos, contratos inexistentes, resueltos o nulos, y documentación inexacta. Infobras registra 6 obras paralizadas y 8 proyectos con contratos resueltos. Además, 18 de los 132 proveedores revisados tienen antecedentes de sanción del Tribunal de Contrataciones (4 vigentes hoy, 3 de ellas por documentos falsos); ninguna inhabilitación temporal estaba vigente al firmar su contrato FEN.
6. El **85,2%** del dinero lo ejecutan entidades nacionales que lo registran con meta en Lima, por lo que no se puede saber en qué región se gastó.

## 5. Limitaciones

- Más del 90% del dinero corresponde a **actividades sin CUI**. El cruce con el SEACE solo identifica proveedores para el 12,9% del devengado en actividades, porque las compras menores a 8 UIT y las órdenes de servicio no figuran en los datos OCDS. El vínculo "tema" es inferido y podría incluir contratos financiados con otras fuentes.
- El gasto del Gobierno Nacional se registra mayormente con meta en Lima. Por eso el mapa por región lo excluye por defecto.
- 2026 está en ejecución, con datos al 28/10/2026.
- Los informes de control simultáneo advierten riesgos; no determinan responsabilidades ni sanciones. Las sanciones del Tribunal se revisaron solo para los 132 proveedores con RUC; los consorcios sin RUC propio (p. ej., Consorcio SQA - LGQ) no pudieron revisarse.
- Para proyectos con varios paquetes, Infobras reporta el avance por paquete; en esos casos se usa el avance del Banco de Inversiones.
- La ficha SSI advierte que sus vínculos con el SEACE e Infobras son referenciales. Algunos contratos cubren varios CUI y se cuentan una sola vez en los totales.
- Las coincidencias "probable" y "posible" entre puntos de 2023 y 2026 requieren verificación en campo.

## 6. Cómo reproducirlo

```bash
cd tarea_3
pip install -r requirements.txt
# 1. Descargar los CSV del MEF en datos/originales/ (ver tabla de fuentes)
# 2. Descargar los .tar.gz OCDS 2023 y 2026 en datos/originales/ocds/ y correr: python scripts/cruce_seace_ocds.py
# 3. (Opcional) Actualizar contratos e informes: ejecutar scripts/consultar_ssi.js en la consola del navegador
#    sobre una ficha SSI y copiar el resultado a datos/procesados/
python scripts/procesar_datos.py      # genera web/data/* (luego vuelve a correr cruce_seace_ocds.py)
python -m http.server -d web 8000     # abrir http://localhost:8000
```

Estructura:

```
tarea_3/
├── datos/originales/    # fuentes (los archivos de más de 100 MB se descargan aparte)
├── datos/procesados/    # contratos, informes de control, repeticiones, avance por componente
├── scripts/             # procesar_datos.py, consultar_ssi.js
├── web/                 # dashboard (index.html, assets/, data/)
└── reel/                # guion, subtítulos y recursos del reel
```

## 7. Uso de inteligencia artificial

El procesamiento de datos, el código del dashboard y la redacción de textos se hicieron con asistencia de Claude (Anthropic). La sistematización de los decretos y anexos se hizo a mano y se revisó contra los textos de El Peruano. Las cifras del dashboard y de este README se verificaron contra los archivos originales del repositorio.
