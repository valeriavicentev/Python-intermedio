# Tarea 2 · Voces y documentos peruanos: del archivo escaneado al texto buscable

> **Pregunta:** ¿Podemos convertir documentos escaneados y entrevistas en audio en un archivo de texto estructurado y buscable?

**Dashboard público:** _(enlace de Streamlit Community Cloud)_

## Resumen

Se construyó un pipeline que lee **25 documentos peruanos** (8 impresos, 8 fotos de carteles y placas, 9 manuscritos)
con PaddleOCR y transcribe **~52 minutos de audio** en español peruano (entrevistas en la calle de Lima, Cusco y Arequipa,
dirigentes sociales, noticiarios antiguos de la Biblioteca Nacional del Perú y habla leída de OpenSLR 73) con faster-whisper,
VAD y diarización. Los textos se seudonimizan, un LLM (Gemini) extrae campos estructurados y una auditoría humana los revisa.
Los modelos se comparan con CER/WER sobre 10 documentos y 10 clips transcritos a mano.

| Resultado (muestra de evaluación) | Valor |
|---|---|
| CER del OCR elegido | _(02_evaluacion.ipynb)_ |
| WER del ASR elegido | _(02_evaluacion.ipynb)_ |
| Acuerdo LLM–humano | _(x/20)_ |

## Hallazgos

1. _(completar con los resultados)_
2. _(completar con los resultados)_

## Limitaciones técnicas

1. _(completar)_
2. _(completar)_

## Estructura

| Archivo | Qué hace |
|---|---|
| `01_extraccion.ipynb` | OCR (PaddleOCR) + ASR (faster-whisper, VAD, diarización), seudonimización, limpieza, EDA y exportación |
| `02_evaluacion.ipynb` | Referencias manuales, CER/WER de 3 modelos por modalidad, extracción con LLM y auditoría de 20 casos |
| `app.py` | Dashboard de Streamlit (solo lee CSV; no corre modelos) |
| `descargas.py` | Busca candidatos en Wikimedia Commons, verifica licencias y descarga (User-Agent con contacto, 1,5 s entre pedidos) |
| `herramientas.py` | OCR, corte de audios en clips, limpieza por hash y seudonimización |
| `voz.py`, `datos.py` | Copias de la Sesión 13 (VAD, transcripción, diarización, SRT/TXT, WER/CER; OpenSLR 73) |
| `llm.py` | Extracción estructurada con Gemini por API REST (clave en `.env`, no versionada) |
| `datos/documentos.csv` | Corpus OCR (25 documentos) |
| `datos/transcripciones.csv` | Corpus ASR (clips de ~45 s) |
| `datos/extraccion_llm.csv` | Campos extraídos por el LLM |
| `datos/fuentes.csv` | Fuente, licencia, autor, fecha y forma de acceso de cada archivo |
| `datos/referencias/` | Transcripciones manuales de los 10 documentos y 10 clips evaluados |
| `datos/ejemplos/` | Imágenes (900 px) y audios publicables que muestra el dashboard |

## Corpus y fuentes

Fecha de extracción: **2026-10-22**. Todo proviene de Wikimedia Commons (verificado con la API: dominio público, CC0, CC BY o
CC BY-SA) y de OpenSLR 73. Los archivos originales (~1 GB) no se versionan (`datos/raw/` está en `.gitignore`); se recuperan
con `descargas.py bajar`.

### Documentos

| id | tipo | documento | licencia |
|---|---|---|---|
| doc_001 | impreso | [Resolución de alcaldía de Mache (2016)](https://commons.wikimedia.org/wiki/File:Acta_de_Creaci%C3%B3n_de_los_S%C3%ADmbolos_para_el_Distrito_de_Mache.jpg) | CC BY 4.0 |
| doc_002 | impreso | [Mercurio Peruano, 13 de enero de 1791](https://commons.wikimedia.org/wiki/File:Pisco-punch-mercurio-peruano-1791.jpg) | Public domain |
| doc_003 | impreso | [Mercurio Peruano, 2 de enero de 1791 (Idea general del Perú)](https://commons.wikimedia.org/wiki/File:Mercurio_Peruano1.jpg) | Public domain |
| doc_004 | impreso | [Portada de la Constitución Política de 1823 (impresa en 1825)](https://commons.wikimedia.org/wiki/File:Constituci%C3%B3n_Pol%C3%ADtica_de_la_Rep%C3%BAblica_Peruana_de_1823.jpg) | Public domain |
| doc_005 | impreso | [El Peruano Independiente, prospecto (1825)](https://commons.wikimedia.org/wiki/File:Primera_edici%C3%B3n_de_El_Peruano_(1825).jpg) | Public domain |
| doc_006 | impreso | [El Comercio, primer número (1839)](https://commons.wikimedia.org/wiki/File:El_Comercio_Issue_1.jpg) | Public domain |
| doc_007 | impreso | [El Comercio, número 12 (1839)](https://commons.wikimedia.org/wiki/File:El_Comercio_Issue_12.jpg) | CC BY-SA 4.0 |
| doc_008 | impreso | [El Comercio, 3 de marzo de 1842](https://commons.wikimedia.org/wiki/File:El_Comercio_-_Lima._Per%C3%BA_y_Ecuador._3-3-1842.jpg) | Public domain |
| doc_009 | foto | [Placa de la Calle Capón, Lima (inclinada, sombra)](https://commons.wikimedia.org/wiki/File:Placa_Calle_Capon.jpg) | CC BY 3.0 |
| doc_010 | foto | [Pizarra de menú escrita con tiza, Lince](https://commons.wikimedia.org/wiki/File:Menu_Levaggi_09052010.jpg) | CC BY-SA 3.0 |
| doc_011 | foto | [Cartel «Picante de cuy» pintado a mano, Junín](https://commons.wikimedia.org/wiki/File:Cartel_Picante_de_cuy.JPG) | Public domain |
| doc_012 | foto | [Afiches chicha superpuestos, Lima](https://commons.wikimedia.org/wiki/File:Carteles_chicha.jpg) | CC BY-SA 2.0 |
| doc_013 | foto | [Letrero del Ministerio de Cultura, Necrópolis de Ancón](https://commons.wikimedia.org/wiki/File:Letrero-Cartel_del_Ministerio_de_Cultura_dando_aviso_de_la_Necr%C3%B3polis_de_Anc%C3%B3n.jpg) | CC BY-SA 4.0 |
| doc_014 | foto | [Placa conmemorativa, Facultad de Ciencias Físicas UNMSM](https://commons.wikimedia.org/wiki/File:Placa_conmemorativa_Te%C3%B3filo_Miranda_Rojas.jpg) | CC BY-SA 4.0 |
| doc_015 | foto | [Placa de inauguración de mercados, Lima (1945)](https://commons.wikimedia.org/wiki/File:Placa_conmemorativa_Mercado_Minorista_La_Parada.jpg) | CC0 |
| doc_016 | foto | [Placa de mármol en la Catedral de Lima (1988)](https://commons.wikimedia.org/wiki/File:LimaPlacaCatedral1988.JPG) | CC BY-SA 3.0 |
| doc_017 | manuscrito | [Recibo de la Peruvian Telephone Company llenado a mano (1895)](https://commons.wikimedia.org/wiki/File:Peruvian_Telephone_Company_receipt_Lima_1895.JPG) | Public domain |
| doc_018 | manuscrito | [Tarjeta manuscrita de Ricardo Palma (1912) – recortada sin la transcripción impresa](https://commons.wikimedia.org/wiki/File:Tarjeta_de_Ricardo_Palma_a_Luis_Antonio_Eguiguren_Escudero_24_octubre_1912.png) | Public domain |
| doc_019 | manuscrito | [Acta de la Independencia del Perú (1821)](https://commons.wikimedia.org/wiki/File:Acta_de_Independencia_Peru.jpg) | Public domain |
| doc_020 | manuscrito | [Guaman Poma, Nueva corónica, p. 862 (c. 1615)](https://commons.wikimedia.org/wiki/File:%22El_primer_nueva_cr%C3%B3nica_y_buen_gobierno%22_by_Felipe_Guam%C3%A1n_Poma_de_Ayala,_pg_862.png) | Public domain |
| doc_021 | manuscrito | [Guaman Poma, Nueva corónica, p. 538 (c. 1615)](https://commons.wikimedia.org/wiki/File:Guaman_Poma_-_Nueva_cr%C3%B3nica_-_Pag_538.jpg) | Public domain |
| doc_022 | manuscrito | [Guaman Poma, Nueva corónica, p. 360 (facsímil 1936)](https://commons.wikimedia.org/wiki/File:Nueva_cor%C3%B3nica_y_buen_gobierno_(1936_facsimile)_p360.png) | Public domain |
| doc_023 | manuscrito | [Guaman Poma, Nueva corónica – Manco Inca](https://commons.wikimedia.org/wiki/File:Guaman_Poma_de_Ayala_-_Manco_Inca.jpg) | Public domain |
| doc_024 | manuscrito | [Guaman Poma, Nueva corónica – Topa Inga Yupanqui](https://commons.wikimedia.org/wiki/File:Tupac_Yupanqui_por_Guaman_Poma_de_Ayala.jpg) | Public domain |
| doc_025 | manuscrito | [Guaman Poma, Nueva corónica – Fraile mercedario](https://commons.wikimedia.org/wiki/File:Guaman_Poma_-_Fraile_mercedario_Morua.jpg) | Public domain |

### Audio

| id | tipo | grabación | licencia |
|---|---|---|---|
| fuente_01 | entrevista | [Entrevista en la calle a una vendedora, El Agustino, Lima (2022)](https://commons.wikimedia.org/wiki/File:Entrevista_1_en_la_Av._Rivag%C3%BCero_-_El_Agustino.ogg) | CC BY-SA 4.0 |
| fuente_02 | entrevista | [Entrevista a dos vendedoras, El Agustino, Lima (2022) – multihablante](https://commons.wikimedia.org/wiki/File:Entrevista_2_en_la_Av._Rivag%C3%BCero_-_El_Agustino.ogg) | CC BY-SA 4.0 |
| fuente_03 | entrevista | [Dirigente de Fenmucarinap, conferencia de prensa (2022)](https://commons.wikimedia.org/wiki/File:Entrevista-Aurora_Coronado-organizaci%C3%B3n_de_mujeres_ind%C3%ADgenas-fiestas_patrias.ogg) | CC BY-SA 4.0 |
| fuente_04 | entrevista | [Dirigente de mujeres indígenas, protesta (2022)](https://commons.wikimedia.org/wiki/File:Entrevista_a_Luz_Merida-Organizaci%C3%B3n_de_mujeres_ind%C3%ADgenas-fiestas_patrias-protesta.ogg) | CC BY-SA 4.0 |
| fuente_05 | entrevista | [Entrevista en la calle, Magdalena, Lima (2022)](https://commons.wikimedia.org/wiki/File:Entrevista_en_Magdalena_por_Fiestas_Patrias_Per%C3%BA_2022_(1).webm) | CC BY-SA 4.0 |
| fuente_06 | entrevista | [Entrevista en la calle, Magdalena, Lima (2022)](https://commons.wikimedia.org/wiki/File:Entrevista_en_Magdalena_por_Fiestas_Patrias_Per%C3%BA_2022_(2).webm) | CC BY-SA 4.0 |
| fuente_07 | entrevista | [Entrevista en la calle, Magdalena, Lima (2022)](https://commons.wikimedia.org/wiki/File:Entrevista_en_Magdalena_por_Fiestas_Patrias_Per%C3%BA_2022_(3).webm) | CC BY-SA 4.0 |
| fuente_08 | entrevista | [Entrevista por el aniversario de la independencia (2022)](https://commons.wikimedia.org/wiki/File:Entrevista_por_el_aniversario_201_de_la_independencia_del_Per%C3%BA_III.webm) | CC BY 3.0 |
| fuente_09 | entrevista | [Entrevista a un adulto mayor, Cusco](https://commons.wikimedia.org/wiki/File:Entrevista_a_un_adulto_mayor.webm) | CC BY-SA 4.0 |
| fuente_10 | entrevista | [Entrevista a una vendedora, Cusco](https://commons.wikimedia.org/wiki/File:Entrevista_a_una_vendedora_de_chucherias.webm) | CC BY-SA 4.0 |
| fuente_11 | entrevista | [Entrevista a un tatuador, Cusco](https://commons.wikimedia.org/wiki/File:Entrevista_a_un_tatuador_01.webm) | CC BY-SA 4.0 |
| fuente_12 | entrevista | [Entrevista a un poblador de Chuyas](https://commons.wikimedia.org/wiki/File:Entrevista_a_un_integrante_del_pueblo_de_Chuyas.webm) | CC BY-SA 4.0 |
| fuente_14 | entrevista | [Entrevista, Encuentro de cine Corriente, Arequipa](https://commons.wikimedia.org/wiki/File:Entrevista_a_Bel%C3%A9n_Valdivia_-_12%C2%B0_Encuentro_de_cine_Corriente.webm) | CC BY 4.0 |
| fuente_15 | entrevista | [Entrevista, Encuentro de cine Corriente, Arequipa](https://commons.wikimedia.org/wiki/File:Entrevista_a_Rodrigo_Alatrista_-_12%C2%B0_Encuentro_de_cine_Corriente.webm) | CC BY 4.0 |
| fuente_17 | noticiario | [Noticiario de los años 40 (BNP) – narración con música](https://commons.wikimedia.org/wiki/File:Del_Viejo_Lima_(Los_Descalzos).webm) | PDM-owner |
| fuente_18 | noticiario | [Noticiario de los años 40 (BNP) – narración con música](https://commons.wikimedia.org/wiki/File:Verano_En_La_Punta.webm) | PDM-owner |
| fuente_19 | noticiario | [Noticiario antiguo (BNP) – narración con música](https://commons.wikimedia.org/wiki/File:En_las_ruinas_de_Chan_Chan.webm) | PDM-owner |
| openslr73 | habla leída | [Crowdsourced high-quality Peruvian Spanish speech data set (Google)](https://www.openslr.org/73/) | CC BY-SA 4.0 |

Dos grabaciones descargadas (fuente_13, 9 min, y fuente_16, 13 min) se dejaron fuera para acotar el cómputo en CPU.

**Datos personales:** los nombres de personas privadas se reemplazaron por seudónimos y los DNI, RUC, teléfonos y correos por
etiquetas (sección 4 de `01_extraccion.ipynb`). Las figuras públicas o históricas en documentos públicos se conservan. El
dashboard solo reproduce audio de fuentes sin personas privadas (noticiarios de dominio público y OpenSLR 73).

## Cómo ejecutar

### Dashboard (local)

```bash
cd tarea_2
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Notebooks (entorno del curso)

```bash
CLASE="<ruta>/Data-Science-Python"           # repositorio de la clase
(cd "$CLASE" && uv sync --group docai --group audio --group geo --group deploy)
brew install tesseract tesseract-lang         # para el OCR alternativo de la Parte 2
cd tarea_2
uv run --project "$CLASE" python descargas.py bajar
uv run --project "$CLASE" jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=-1 01_extraccion.ipynb
# 02_evaluacion.ipynb: requiere las referencias manuales en datos/referencias/, la clave GEMINI_API_KEY en .env
# y la auditoría en datos/auditoria_llm.csv
```

## Uso de IA

El desarrollo se apoyó en Claude (asistente de programación). Las capturas de la conversación completa están en `evidencias_ia/`.
Las transcripciones de referencia y la auditoría de las extracciones del LLM se hicieron a mano.
