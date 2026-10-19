"""Dashboard – Tarea 1: ¿Pueden convertir titulares peruanos en un clasificador de noticias?

Ejecutar en local:  streamlit run app.py
"""
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

BASE = Path(__file__).parent
DATOS = BASE / "datos"
MODELO = BASE / "modelo"
CATEGORIAS = ["politica", "economia", "deportes", "ciencia_tecnologia"]
NOMBRES = {"politica": "Política", "economia": "Economía",
           "deportes": "Deportes", "ciencia_tecnologia": "Ciencia y tecnología"}
COLORES = {"politica": "#1F4E79", "economia": "#2E8B57",
           "deportes": "#E07B00", "ciencia_tecnologia": "#7B3FA0"}

st.set_page_config(page_title="Clasificador de titulares peruanos", page_icon="🗞️", layout="wide")


# ---------- carga de datos y modelo ----------
@st.cache_data
def cargar_noticias():
    return pd.read_csv(DATOS / "noticias.csv", parse_dates=["fecha"])


@st.cache_data
def cargar_metricas():
    ruta = MODELO / "metricas.json"
    return json.loads(ruta.read_text()) if ruta.exists() else {}


@st.cache_resource(show_spinner="Cargando el modelo…")
def cargar_clasificador():
    from transformers import pipeline
    # En local se usa la carpeta modelo/. En Streamlit Cloud (donde los pesos no están en GitHub)
    # se puede indicar un modelo publicado en Hugging Face con la variable HF_MODEL_ID.
    origen = os.getenv("HF_MODEL_ID") or str(MODELO)
    return pipeline("text-classification", model=origen, tokenizer=origen, top_k=None)


def modelo_disponible():
    if os.getenv("HF_MODEL_ID"):
        return True
    pesos = list(MODELO.glob("*.safetensors")) + list(MODELO.glob("*.bin"))
    return (MODELO / "config.json").exists() and len(pesos) > 0


df = cargar_noticias()
met = cargar_metricas()

# ---------- encabezado ----------
st.title("🗞️ ¿Pueden convertir titulares peruanos en un clasificador de noticias?")
st.markdown(
    f"""
Se recolectaron **{len(df)} noticias de {', '.join(sorted(df['medio'].unique()))}** mediante sus canales
oficiales (RSS y sitemaps, respetando `robots.txt`), entre el **{df['fecha'].min():%d/%m/%Y}** y el
**{df['fecha'].max():%d/%m/%Y}**. Cada noticia se etiquetó en 4 categorías a partir de su sección
(`politica`, `economia`, `deportes`, `ciencia_tecnologia`), se comparó un modelo **zero-shot**, un **LLM (Gemini)**
como etiquetador débil y un **DistilBERT multilingüe** ajustado (*fine-tuning*) con un split 70/15/15.
Abajo puedes explorar los datos y **probar el clasificador con cualquier titular**.
"""
)

# ---------- filtros ----------
st.sidebar.header("Filtros")
medios = sorted(df["medio"].unique())
sel_medios = st.sidebar.multiselect("Medio", medios, default=medios)
sel_cats = st.sidebar.multiselect("Categoría", CATEGORIAS, default=CATEGORIAS, format_func=NOMBRES.get)
filtrado = df[df["medio"].isin(sel_medios) & df["etiqueta"].isin(sel_cats)]
st.sidebar.caption(f"{len(filtrado)} de {len(df)} noticias seleccionadas")

# ---------- métricas ----------
c1, c2, c3 = st.columns(3)
c1.metric("Noticias recolectadas", f"{len(df)}", f"{len(filtrado)} con los filtros", delta_color="off")
if met:
    c2.metric("F1 macro en test (DistilBERT)", f"{met['f1_macro_test']:.2f}",
              f"{met['f1_macro_test'] - met['f1_zero_shot']:+.2f} vs. zero-shot")
    c3.metric("Acuerdo LLM vs. auditoría humana", f"{met['pct_acuerdo_llm_humano']:.0%}",
              f"{met['acuerdo_llm_humano']}/20 casos", delta_color="off")
else:
    c2.metric("F1 macro en test", "—")
    c3.metric("Acuerdo LLM-humano", "—")
    st.info("Ejecuta `02_clasificacion.ipynb` para generar `modelo/metricas.json`.")

# ---------- gráfico y tabla ----------
izq, der = st.columns([1, 1.4])
with izq:
    conteo = (filtrado["etiqueta"].value_counts().reindex(sel_cats, fill_value=0)
              .rename_axis("etiqueta").reset_index(name="noticias"))
    conteo["categoria"] = conteo["etiqueta"].map(NOMBRES)
    if len(filtrado):
        lider = conteo.loc[conteo["noticias"].idxmax(), "categoria"]
        titulo = f"«{lider}» concentra más noticias en la selección"
    else:
        titulo = "Sin noticias para los filtros elegidos"
    fig = px.bar(conteo, x="categoria", y="noticias", color="etiqueta", text="noticias",
                 color_discrete_map=COLORES, title=titulo,
                 labels={"categoria": "Categoría", "noticias": "Noticias"})
    fig.update_layout(showlegend=False, title_font_size=15)
    st.plotly_chart(fig, width="stretch")

with der:
    st.subheader("Noticias")
    tabla = filtrado[["fecha", "etiqueta", "titular", "bajada", "medio", "seccion_original", "url"]] \
        .sort_values("fecha", ascending=False)
    st.dataframe(tabla, width="stretch", hide_index=True, height=360,
                 column_config={"url": st.column_config.LinkColumn("url"),
                                "fecha": st.column_config.DateColumn("fecha", format="YYYY-MM-DD")})
    st.download_button("⬇️ Descargar CSV filtrado", tabla.to_csv(index=False).encode("utf-8"),
                       file_name="noticias_filtradas.csv", mime="text/csv")

# ---------- probador en vivo ----------
st.divider()
st.header("🔮 Prueba el clasificador")
titular = st.text_input("Escribe o pega un titular",
                        placeholder="Ej.: Congreso aprueba nuevo retiro de fondos de AFP")
if st.button("Clasificar", type="primary"):
    if not titular.strip():
        st.warning("Escribe un titular primero.")
    elif not modelo_disponible():
        st.error("No se encontró el modelo entrenado en `modelo/`. Ejecuta `02_clasificacion.ipynb` "
                 "(los pesos no se suben a GitHub por su tamaño).")
    else:
        salida = cargar_clasificador()(titular.strip())
        if salida and isinstance(salida[0], list):   # algunas versiones anidan el resultado
            salida = salida[0]
        probs = (pd.DataFrame(salida).rename(columns={"label": "etiqueta", "score": "probabilidad"})
                 .sort_values("probabilidad", ascending=False))
        top = probs.iloc[0]
        st.success(f"**Categoría predicha: {NOMBRES.get(top['etiqueta'], top['etiqueta'])}** "
                   f"— confianza {top['probabilidad']:.1%}")
        probs["categoria"] = probs["etiqueta"].map(NOMBRES).fillna(probs["etiqueta"])
        figp = px.bar(probs, x="probabilidad", y="categoria", orientation="h", color="etiqueta",
                      color_discrete_map=COLORES, text=probs["probabilidad"].map("{:.1%}".format),
                      range_x=[0, 1], labels={"probabilidad": "Probabilidad", "categoria": ""})
        figp.update_layout(showlegend=False, height=260, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(figp, width="stretch")
        if top["probabilidad"] < 0.5:
            st.caption("Confianza baja: el titular podría pertenecer a más de una categoría.")

st.caption("Tarea 1 – Data Science con Python · Datos: El Comercio (RSS y sitemaps oficiales) · "
           "Modelo: distilbert-base-multilingual-cased ajustado")
