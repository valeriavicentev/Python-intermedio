"""Tarea 2 · Dashboard: voces y documentos peruanos, del archivo escaneado al texto buscable.

Solo lee los CSV generados por 01_extraccion.ipynb y 02_evaluacion.ipynb: no carga modelos.
    streamlit run app.py
"""
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "datos"
EJ = DATOS / "ejemplos"
# paleta categórica validada (orden fijo: el color sigue a la categoría, no a su posición)
SERIE = ["#2a78d6", "#eb6834", "#1baf7a"]
COLOR_TIPO = dict(zip(["impreso", "foto", "manuscrito"], SERIE))

st.set_page_config(page_title="Voces y documentos peruanos", page_icon="📜", layout="wide")


@st.cache_data
def _leer(nombre, version):
    return pd.read_csv(DATOS / nombre)


def leer(nombre):
    """La fecha de modificación entra a la clave de la caché: si el CSV cambia (o aparece), se vuelve a leer."""
    ruta = DATOS / nombre
    return _leer(nombre, ruta.stat().st_mtime) if ruta.exists() else pd.DataFrame()


def sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def contiene(serie, consulta):
    return serie.fillna("").map(sin_tildes).str.contains(re.escape(sin_tildes(consulta)), regex=True)


docs = leer("documentos.csv")
clips = leer("transcripciones.csv")
fuentes = leer("fuentes.csv")
llm = leer("extraccion_llm.csv")
comparativa = leer("metricas_modelos.csv")
ocr_caso = leer("metricas_ocr_por_caso.csv")
asr_caso = leer("metricas_asr_por_caso.csv")
auditoria = leer("auditoria_llm.csv")
campos = {r.id: json.loads(r.campos_json) for r in llm.itertuples()} if len(llm) else {}
info_fuente = fuentes.set_index("id") if len(fuentes) else pd.DataFrame()

# ───────────────────────────────────────────── encabezado
st.title("¿Podemos convertir documentos escaneados y entrevistas en audio en texto estructurado y buscable?")
st.markdown(
    "**Corpus:** 25 documentos peruanos (impresos, fotos de carteles y placas, manuscritos desde el siglo XVII) y "
    "entrevistas y noticiarios en español peruano, todos con licencia libre (Wikimedia Commons, Biblioteca Nacional del Perú "
    "vía Commons y OpenSLR 73). **Pipeline:** PaddleOCR → faster-whisper con VAD y diarización → seudonimización → "
    "extracción de campos con un LLM y auditoría humana. **Evaluación:** CER/WER sobre 10 documentos y 10 clips "
    "transcritos a mano. Los modelos corrieron en los notebooks; esta app solo explora sus resultados."
)

# ───────────────────────────────────────────── filtros (barra lateral)
with st.sidebar:
    st.header("Filtros")
    consulta = st.text_input("Buscar en los textos OCR y ASR", placeholder="p. ej. Lima, mercado, independencia")
    tipos = st.multiselect("Tipo de documento", ["impreso", "foto", "manuscrito"], default=["impreso", "foto", "manuscrito"])
    tipos_audio = sorted(clips["tipo_audio"].dropna().unique()) if len(clips) else []
    sel_audio = st.multiselect("Tipo de audio", tipos_audio, default=tipos_audio)
    dmax = float(clips["duracion_seg"].max()) if len(clips) else 60.0
    dur = st.slider("Duración del clip (s)", 0.0, dmax, (0.0, dmax))
    modelos = sorted(set(comparativa.get("modelo", pd.Series(dtype=str))))
    sel_modelos = st.multiselect("Modelos evaluados", modelos, default=modelos)

d_f = docs[docs["tipo"].isin(tipos)] if len(docs) else docs
c_f = clips[clips["tipo_audio"].isin(sel_audio) & clips["duracion_seg"].between(*dur)] if len(clips) else clips
if consulta:
    d_f = d_f[contiene(d_f["texto_ocr"], consulta)]
    c_f = c_f[contiene(c_f["texto_asr"], consulta)]

# ───────────────────────────────────────────── indicadores
def valor_mejor(metrica):
    sub = comparativa[(comparativa.get("metrica") == metrica) & comparativa["modelo"].isin(sel_modelos)] if len(comparativa) else pd.DataFrame()
    return sub.sort_values("valor").iloc[0] if len(sub) else None

k = st.columns(5)
k[0].metric("Documentos procesados", f"{len(d_f)} / {len(docs)}")
k[1].metric("Minutos de audio transcritos", f"{c_f['duracion_seg'].sum() / 60:.1f}" if len(c_f) else "0")
m_cer, m_wer = valor_mejor("CER"), valor_mejor("WER")
k[2].metric("Mejor CER (10 documentos)", f"{m_cer.valor:.1%}" if m_cer is not None else "—",
            help=m_cer.modelo if m_cer is not None else "Corre 02_evaluacion.ipynb")
k[3].metric("Mejor WER (10 clips)", f"{m_wer.valor:.1%}" if m_wer is not None else "—",
            help=m_wer.modelo if m_wer is not None else "Corre 02_evaluacion.ipynb")
if len(auditoria) and auditoria["correcto"].notna().all():
    k[4].metric("Concordancia LLM vs. auditoría", f"{auditoria['correcto'].mean():.0%}",
                help=f"{int(auditoria['correcto'].sum())}/{len(auditoria)} extracciones completamente correctas")
else:
    k[4].metric("Concordancia LLM vs. auditoría", "—")

tab_res, tab_doc, tab_aud, tab_mod = st.tabs(["📊 Resumen", "📄 Documentos", "🎙️ Audios", "⚖️ Modelos"])

# ───────────────────────────────────────────── resumen
with tab_res:
    a, b = st.columns(2)
    if len(d_f):
        cuenta = d_f["tipo"].value_counts().reindex(["impreso", "foto", "manuscrito"]).fillna(0).reset_index()
        cuenta.columns = ["tipo", "documentos"]
        fig = px.bar(cuenta, x="tipo", y="documentos", color="tipo", color_discrete_map=COLOR_TIPO, text="documentos",
                     title="Documentos por tipo (con los filtros actuales)")
        fig.update_traces(textposition="outside", marker_line_width=0)
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Documentos")
        a.plotly_chart(fig, width="stretch")
    if len(c_f):
        fig = px.histogram(c_f, x="duracion_seg", color="tipo_audio", nbins=25, barmode="stack",
                           color_discrete_sequence=SERIE + ["#eda100", "#e87ba4"],
                           title="Duración de los clips: la mayoría dura menos de un minuto")
        fig.update_layout(xaxis_title="Duración (s)", yaxis_title="Clips", legend_title="Tipo de audio", bargap=0.05)
        b.plotly_chart(fig, width="stretch")
    st.subheader("Resultados de la búsqueda" if consulta else "Corpus")
    tabla = pd.concat([
        d_f.assign(modalidad="documento", texto=d_f["texto_ocr"], modelo=d_f["modelo_ocr"], categoria=d_f["tipo"])[["id", "modalidad", "categoria", "modelo", "texto"]],
        c_f.assign(modalidad="audio", texto=c_f["texto_asr"], modelo=c_f["modelo_asr"], categoria=c_f["tipo_audio"])[["id", "modalidad", "categoria", "modelo", "texto"]],
    ]) if len(docs) and len(clips) else pd.DataFrame()
    st.dataframe(tabla, width="stretch", hide_index=True)
    st.download_button("Descargar CSV (textos revisados y seudonimizados)", tabla.to_csv(index=False).encode("utf-8"),
                       "corpus_filtrado.csv", "text/csv")

# ───────────────────────────────────────────── documentos
def mostrar_campos(id_):
    c = campos.get(id_)
    if not c:
        st.caption("Sin extracción del LLM para este registro.")
        return
    filas = [(k, ", ".join(v) if isinstance(v, list) else ("—" if v is None else v)) for k, v in c.items()]
    st.table(pd.DataFrame(filas, columns=["campo", "valor"]).set_index("campo"))

with tab_doc:
    if not len(d_f):
        st.info("Ningún documento coincide con los filtros.")
    else:
        did = st.selectbox("Documento", d_f["id"], format_func=lambda i: f"{i} · {d_f.set_index('id').at[i, 'tipo']}")
        d = d_f.set_index("id").loc[did]
        izq, der = st.columns([2, 3])
        img = EJ / "imagenes" / f"{did}.jpg"
        with izq:
            if img.exists():
                st.image(str(img), width="stretch")
            else:
                st.caption("Imagen no publicada (solo texto y metadatos).")
            st.caption(f"Fuente y licencia: {d['fuente']}")
        with der:
            st.markdown("**Texto OCR** · " + str(d["modelo_ocr"]))
            st.text_area("ocr", d["texto_ocr"], height=220, label_visibility="collapsed")
            st.markdown("**Campos extraídos por el LLM**")
            mostrar_campos(did)
            if isinstance(d.get("texto_referencia"), str) and d["texto_referencia"].strip():
                st.markdown("**Referencia manual** (documento de la muestra de evaluación)")
                st.text_area("ref", d["texto_referencia"], height=140, label_visibility="collapsed")
                if len(ocr_caso):
                    cer = ocr_caso[(ocr_caso["id"] == did) & ocr_caso["modelo"].isin(sel_modelos)][["modelo", "cer", "segundos"]]
                    st.dataframe(cer.style.format({"cer": "{:.1%}", "segundos": "{:.2f}"}), hide_index=True, width="stretch")

# ───────────────────────────────────────────── audios
with tab_aud:
    if not len(c_f):
        st.info("Ningún clip coincide con los filtros.")
    else:
        cid = st.selectbox("Clip", c_f["id"], format_func=lambda i: f"{i} · {c_f.set_index('id').at[i, 'tipo_audio']} · "
                                                                   f"{c_f.set_index('id').at[i, 'duracion_seg']:.0f} s")
        c = c_f.set_index("id").loc[cid]
        st.markdown(f"**Hablantes detectados:** {int(c['n_hablantes'])} · **Modelo:** {c['modelo_asr']} · "
                    f"**Fuente:** {c['fuente_id']}")
        if c["fuente_id"] in info_fuente.index:
            f = info_fuente.loc[c["fuente_id"]]
            st.caption(f"{f['fuente_url']} · {f['licencia']}")
        audio = EJ / "audio" / f"{cid}.ogg"
        if audio.exists():
            st.audio(str(audio))
        else:
            st.caption("Audio no publicado: contiene voces de personas privadas; se muestra solo la transcripción.")
        izq, der = st.columns([3, 2])
        with izq:
            st.markdown("**Transcripción**")
            texto = re.sub(r"\s*(\[HABLANTE_\d+\])", r"\n\n\1", str(c["texto_asr"])).strip()
            st.text_area("asr", texto, height=260, label_visibility="collapsed")
        with der:
            st.markdown("**Campos extraídos por el LLM**")
            mostrar_campos(cid)
        if len(asr_caso) and cid in set(asr_caso["id"]):
            st.markdown("**Comparación de modelos** (clip de la muestra de evaluación)")
            st.text_area("Referencia manual", c["texto_referencia"], height=100, key="ref_a")
            comp = asr_caso[(asr_caso["id"] == cid) & asr_caso["modelo"].isin(sel_modelos)][["modelo", "wer", "rtf", "texto"]]
            st.dataframe(comp.style.format({"wer": "{:.1%}", "rtf": "{:.2f}"}), hide_index=True, width="stretch")

# ───────────────────────────────────────────── modelos
with tab_mod:
    if not len(comparativa):
        st.info("Aún no hay métricas: corre 02_evaluacion.ipynb.")
    else:
        comp = comparativa[comparativa["modelo"].isin(sel_modelos)]
        st.dataframe(comp, hide_index=True, width="stretch")
        por_caso = pd.concat([
            ocr_caso.assign(metrica="CER (documentos)", error=ocr_caso["cer"], caso=ocr_caso["tipo"]),
            asr_caso.assign(metrica="WER (audio)", error=asr_caso["wer"], caso=asr_caso["tipo_audio"]),
        ])
        por_caso = por_caso[por_caso["modelo"].isin(sel_modelos)].groupby(["metrica", "caso", "modelo"], as_index=False)["error"].mean()
        orden = list(comparativa["modelo"])
        fig = px.bar(por_caso, x="caso", y="error", color="modelo", barmode="group", facet_col="metrica",
                     category_orders={"modelo": orden}, color_discrete_sequence=SERIE * 2,
                     title="Error medio por tipo de caso y modelo (más bajo es mejor)")
        fig.update_xaxes(matches=None, title=""); fig.update_yaxes(tickformat=".0%", title="")
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        st.plotly_chart(fig, width="stretch")

st.caption("Los textos publicados fueron revisados y seudonimizados. Licencias y atribución por archivo en datos/fuentes.csv.")
