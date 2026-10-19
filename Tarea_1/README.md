# 🗞️ Tarea 1 – Noticias peruanas: del titular al clasificador

## 1. Pregunta del proyecto

**¿Pueden convertir titulares peruanos en un clasificador de noticias?**

Sí. Un `distilbert-base-multilingual-cased` ajustado con 268 titulares de entrenamiento clasifica noticias de El Comercio en 4 categorías (`politica`, `economia`, `deportes`, `ciencia_tecnologia`) con un **F1 macro de 0,86 en el conjunto de test reservado**, frente a 0,66 de un modelo zero-shot sin entrenar.

| Modelo | F1 macro (test) | Latencia por titular | Comentario |
|---|---|---|---|
| Zero-shot (`Recognai/bert-base-spanish-wwm-cased-xnli`) | 0,66 | ~77 ms | Línea base sin entrenamiento (40 titulares) |
| LLM débil (Gemini 3.1 Flash-Lite) | 0,90 | ~446 ms | Etiquetó los 383 titulares; auditoría humana 20/20 |
| **DistilBERT fine-tuned** | **0,86** | **~12 ms** | Modelo elegido: local, rápido y sin costo por consulta |

## 2. Medio y fechas de extracción

- **Medio:** El Comercio (`elcomercio.pe`) — **opción B**, 383 noticias (95–99 por categoría).
- **Fuentes:** RSS oficiales por sección (`/arc/outboundfeeds/google-news-feed/category/{sección}/`) y sitemaps de noticias (`/sitemap/news/{sección}/`), respetando `robots.txt`, con pausas de 1,5 s y máximo 1 reintento.
- **Fecha de descarga:** 2026-10-19.
- **Rango de publicación de las noticias:** _AAAA-MM-DD_ a _AAAA-MM-DD_ (ver gráfico 2 de `01_recoleccion.ipynb`; el dashboard también lo muestra en su encabezado).
- **Cambio de opción C → B:** el plan inicial era comparar La República y El Comercio (200 + 200). La República solo expuso 54 noticias válidas por sus canales permitidos (sus RSS y sitemaps traen ~25 notas por sección y su `robots.txt` prohíbe recorrer `/archivo/` y la paginación `/pag/`), por lo que se pasó a la opción B. El detalle está documentado en `01_recoleccion.ipynb`.

## 3. Hallazgos analíticos

1. **El LLM etiqueta mejor, pero el modelo pequeño es el más práctico.** Gemini alcanzó el mayor F1 (0,90) y coincidió con la revisión humana en 20 de 20 casos, pero durante el etiquetado hubo errores 503 (modelo saturado) y 429 (cuota agotada) que obligaron a reintentar lotes. DistilBERT queda solo 3 puntos por debajo (0,86), responde en ~12 ms por titular en una laptop (unas 37 veces más rápido que los ~446 ms de Gemini) y no depende de una API. La combinación natural es usar el LLM para **etiquetar** y el modelo pequeño para **clasificar**.
2. **Deportes es trivial; la frontera difícil es economía.** `deportes` obtuvo F1 1,00 por su vocabulario exclusivo (clubes, jugadores, marcadores). `economia` fue la peor categoría (F1 0,76) porque absorbe errores: 5 noticias de la sección Tecnología con contenido empresarial o ambiental ("Netflix despedirá a unos 1.000 empleados", "Trump llama a Musk un tesoro nacional") fueron predichas como economía. Política y economía también se confunden cuando comparten actores del Estado (ministros, ONP).

## 4. Limitaciones técnicas

1. **Etiquetas ruidosas y un solo medio.** La etiqueta "real" sale de la sección donde el diario publicó la nota, y la sección Tecnología de El Comercio incluye ecología, salud y negocios. Parte de los "errores" del modelo son en realidad notas ambiguas. Además, al usar solo El Comercio, el modelo podría rendir peor con el estilo de titulación de otros diarios.
2. **Datos pocos y recientes.** Con 383 noticias, el test tiene solo 58 titulares: un acierto más o menos mueve el F1 en ~2 puntos. Las noticias cubren pocas semanas (los feeds priorizan lo reciente), así que temas muy coyunturales (El Niño, elecciones) pesan más de lo normal. Por su tamaño (~540 MB), los pesos del modelo no se suben a GitHub (ver `.gitignore`): hay que regenerarlos ejecutando `02_clasificacion.ipynb`.

## 5. Cómo ejecutar en local

```bash
# 1. Clonar el repositorio y entrar a la carpeta
git clone https://github.com/valeriavicentev/Python-intermedio.git
cd Python-intermedio/tarea_1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. (Solo si quieres regenerar datos y modelo)
#    crear un archivo .env con:  GEMINI_API_KEY=tu_clave
#    y ejecutar en orden 01_recoleccion.ipynb y 02_clasificacion.ipynb

# 4. Abrir el dashboard
streamlit run app.py
```

El dashboard se abre en `http://localhost:8501` e incluye filtros por medio y categoría, indicadores clave, gráfico interactivo, tabla descargable y un **probador en vivo** para clasificar titulares nuevos.

## Estructura

```
tarea_1/
├── 01_recoleccion.ipynb      # Scraping (RSS + sitemaps), limpieza, mapeo y EDA
├── 02_clasificacion.ipynb    # Zero-shot, Gemini, auditoría, fine-tuning y evaluación
├── app.py                    # Dashboard Streamlit
├── requirements.txt
├── README.md
├── .gitignore
├── datos/
│   ├── noticias.csv          # 383 noticias, 7 columnas
│   ├── etiquetas_llm.csv     # Etiquetas de Gemini
│   ├── auditoria_llm.csv     # 20 casos revisados a mano
│   └── raw/                  # Respaldo crudo de la descarga
└── modelo/
    ├── config.json, tokenizer*.json   # Artefactos livianos
    ├── metricas.json, comparativa.csv # Métricas que usa el dashboard
    └── model.safetensors              # (no se sube a GitHub)
```
