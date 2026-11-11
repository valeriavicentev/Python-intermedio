"""Escáner Minero · Gallo Negro

Buscador de empresas mineras del Perú: dónde operan, cómo viven esos distritos,
cómo las ha sancionado el OEFA, qué obras financiaron por Obras por Impuestos y
en qué conflictos sociales aparecen.

    streamlit run app.py
"""

from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from radar import mapa as M
from radar import pauta as P
from radar.buscador import FUENTES, METALES, PROC, Base

st.set_page_config(page_title="Escáner Minero · Gallo Negro", page_icon="◉", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
    /* Paleta "sentinela quad": #FA2400 rojo, #2C00FA azul, #FADD00 amarillo,
       #00FA8C verde, #A59837 oliva, #7A463D marrón. Fondo negro, texto #F6F6F6. */
    html, body, [class*="css"], .stMarkdown { font-family: 'Inter', sans-serif; }
    .stApp { background: #000000; color: #F6F6F6; }
    .marca { font-weight: 800; letter-spacing: -0.03em; font-size: 3rem; line-height: 1.05; color: #00FA8C; }
    .bajada { color: #F6F6F6; font-weight: 300; font-size: 1.1rem; line-height: 1.6; margin: .6rem 0 1.2rem; max-width: 54rem; }
    .bajada a, .stMarkdown a { color: #00FA8C !important; text-decoration: underline; }
    .empresa { font-weight: 800; font-size: 1.9rem; letter-spacing: -0.02em; line-height: 1.1; color: #FADD00; }
    .chip { display: inline-block; border-radius: 999px; padding: 1px 10px; margin: 2px 4px 2px 0;
            font-size: .82rem; font-weight: 600; }
    .chip.produccion { border: 1px solid #00FA8C; color: #000000; background: #00FA8C; }
    .chip.mineral { border: 1px solid #A59837; color: #F6F6F6; background: #000000; }
    .chip.unidad { border: 1px solid #00FA8C; color: #00FA8C; background: #000000; }
    .chip.sancion { border: 1px solid #FA2400; color: #000000; background: #FA2400; }
    .chip.oxi { border: 1px solid #2C00FA; color: #FFFFFF; background: #2C00FA; }
    .chip.conflicto { border: 1px solid #FADD00; color: #000000; background: #FADD00; }
    .nota { color: #CFCFCF; font-size: .85rem; }
    .verificado { border-left: 4px solid #00FA8C; padding: .4rem .8rem; background: #0D0D0D; color: #F6F6F6; }
    .alerta { border-left: 4px solid #FA2400; padding: .4rem .8rem; background: #0D0D0D; color: #F6F6F6; }
    .fragmento { font-size: .88rem; color: #F6F6F6; background: #0D0D0D; border-left: 3px solid #FADD00;
                 padding: .6rem .8rem; border-radius: 4px; }
    [data-testid="stMetricValue"] { color: #FADD00; }
    [data-testid="stMetricLabel"] p { color: #F6F6F6; }
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #CFCFCF !important; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-color: #A59837 !important; }
    div[data-testid="stTextInput"] input { background: #F6F6F6; color: #000000; font-size: 1.05rem; caret-color: #000000; }
    div[data-testid="stTextInput"] input::placeholder { color: #555555; opacity: 1; }
    .stButton button[kind="primary"], .stDownloadButton button { background: #FADD00; color: #000000;
            border: none; font-weight: 600; }
    .stButton button[kind="secondary"] { border-color: #FADD00; color: #FADD00; background: #000000; }
    h4, h5 { color: #F6F6F6; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="Cargando registros…")
def base() -> Base:
    return Base.cargar()


@st.cache_resource(show_spinner=False)
def distritos() -> gpd.GeoDataFrame:
    return gpd.read_file(PROC / "distritos.geojson")


def clave_gemini() -> str | None:
    try:
        clave = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        clave = None
    return clave or os.getenv("GEMINI_API_KEY")


def soles(x: float) -> str:
    if x >= 1_000_000:
        return f"S/ {x / 1_000_000:.1f} mill."
    if x >= 1_000:
        return f"S/ {x / 1_000:.0f} mil"
    return f"S/ {x:,.0f}"


def ir_a(empresa_id: str | None) -> None:
    if empresa_id:
        st.query_params["empresa"] = empresa_id
    else:
        st.query_params.clear()


def n(x: int, uno: str, varios: str) -> str:
    return f"{x} {uno if x == 1 else varios}"


def chips(f: pd.Series) -> str:
    partes = []
    if f["n_unidades"]:
        partes.append(f'<span class="chip unidad">{n(f["n_unidades"], "unidad", "unidades")}</span>')
    if pd.notna(f.get("participacion_principal")) and f["participacion_principal"] >= 0.01:
        partes.append(f'<span class="chip produccion">{f["participacion_principal"] * 100:.0f} % del '
                      f'{f["metal_principal"]} del Perú (2025)</span>')
    if f["minerales"]:
        partes.append(f'<span class="chip mineral">{", ".join(f["minerales"][:5])}</span>')
    if f["n_multas"]:
        partes.append(f'<span class="chip sancion">{n(f["n_multas"], "multa firme", "multas firmes")}</span>')
    if f.get("n_expedientes_ruias", 0):
        partes.append(f'<span class="chip sancion">{n(f["n_expedientes_ruias"], "expediente OEFA", "expedientes OEFA")}</span>')
    if f["n_obras_oxi"]:
        partes.append(f'<span class="chip oxi">{n(f["n_obras_oxi"], "obra por impuestos", "obras por impuestos")}</span>')
    if f.get("n_reportes_conflicto", 0):
        partes.append(f'<span class="chip conflicto">en {n(f["n_reportes_conflicto"], "reporte", "reportes")} de conflictos</span>')
    return "".join(partes)


def tarjeta(f: pd.Series, key: str) -> None:
    with st.container(border=True):
        izq, der = st.columns([3, 1])
        ruc = f"RUC {f['ruc']}" if isinstance(f["ruc"], str) else "RUC no disponible"
        izq.markdown(f"**{f['nombre']}**  \n<span class='nota'>{ruc}</span><br>{chips(f)}", unsafe_allow_html=True)
        der.button("Abrir", key=key, on_click=ir_a, args=(f["empresa_id"],), use_container_width=True)


B = base()
E = B.empresas
elegida = st.query_params.get("empresa")

# =====================================================================
# Portada y búsqueda
# =====================================================================
if not elegida or elegida not in set(E["empresa_id"]):
    st.markdown('<div class="marca">Escáner Minero</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="bajada">Esta es una radiografía de la actividad minera en el Perú. Busca a una empresa '
        "para saber si opera en el país, dónde se encuentran sus unidades de producción y el nivel de pobreza "
        "de la zona. También puedes conocer si tiene sanciones del "
        "Organismo de Evaluación y Fiscalización Ambiental (OEFA), "
        "si figura en reportes de conflictos sociales de la Defensoría del Pueblo y la inversión pública que ha "
        "realizado.</div>",
        unsafe_allow_html=True,
    )
    consulta = st.text_input(
        "Buscar empresa",
        placeholder="Nombre o RUC: Antamina, Southern, Las Bambas, 20100017572…",
        label_visibility="collapsed",
    )

    todos = sorted({m for ms in E["minerales"] for m in ms}, key=lambda m: (m not in METALES.values(), m))
    filtro = st.multiselect("Filtrar por mineral", todos, placeholder="Todos los minerales (cobre, oro, zinc…)")
    if filtro:
        E = E[E["minerales"].apply(lambda ms: any(m in ms for m in filtro))]

    c = st.columns(5)
    c[0].metric("Empresas mineras", len(E))
    c[1].metric("Unidades en producción", int(E["n_unidades"].sum()))
    c[2].metric("Expedientes OEFA", int(E.get("n_expedientes_ruias", pd.Series([0])).sum()))
    c[3].metric("Obras por impuestos", int(B.oxi.loc[B.oxi["empresa_id"].isin(E["empresa_id"]), "obra"].nunique()))
    c[4].metric("Menciones en conflictos",
                0 if B.conflictos is None else int(B.conflictos["empresa_id"].isin(E["empresa_id"]).sum()))

    if consulta:
        res = B.buscar(consulta)
        res = res[res["empresa_id"].isin(E["empresa_id"])]
        st.markdown(f"**{len(res)} resultado{'s' if len(res) != 1 else ''}** para «{consulta}»")
        if res.empty:
            st.caption("Prueba con una parte del nombre (por ejemplo «Bambas») o con el RUC.")
        for i, (_, f) in enumerate(res.head(30).iterrows()):
            tarjeta(f, f"r{i}")
    else:
        st.write("")
        a, b, c3 = st.columns(3, gap="large")
        with a:
            st.markdown("#### Más expedientes en el OEFA")
            st.caption("Registro Único de Infractores Ambientales Sancionados, 2017–2023")
            for i, (_, f) in enumerate(E.nlargest(6, "n_expedientes_ruias").iterrows()):
                tarjeta(f, f"a{i}")
        with b:
            st.markdown("#### Más inversión por impuestos")
            st.caption("Ranking de ProInversión, 2009–2025")
            for i, (_, f) in enumerate(E.nlargest(6, "oxi_ranking_mill").iterrows()):
                tarjeta(f, f"b{i}")
        with c3:
            st.markdown("#### Mencionadas en conflictos")
            st.caption("Reportes de la Defensoría del Pueblo n.º 268–270")
            top = E.sort_values(["n_reportes_conflicto", "n_expedientes_ruias"], ascending=False).head(6)
            for i, (_, f) in enumerate(top.iterrows()):
                tarjeta(f, f"c{i}")

    st.divider()
    st.caption(
        "Cruce por RUC cuando la fuente lo trae y por nombre normalizado cuando no. "
        "Los registros no prueban responsabilidad: son puntos de partida para verificar. "
        "Fuentes: MINEM, INEI, OEFA, ProInversión y Defensoría del Pueblo."
    )
    st.stop()

# =====================================================================
# Perfil de empresa
# =====================================================================
p = B.perfil(elegida)
f = p.fila

st.button("← Volver al buscador", on_click=ir_a, args=(None,))
st.markdown(f'<div class="empresa">{p.nombre}</div>', unsafe_allow_html=True)
ruc = f"RUC {f['ruc']}" if isinstance(f["ruc"], str) else "RUC no disponible en las fuentes"
fuentes_en = sorted(p.alias["fuente"].unique())
st.markdown(
    f"<span class='nota'>{ruc} · aparece en: {', '.join(fuentes_en)}</span>",
    unsafe_allow_html=True,
)
if f["minerales"]:
    st.markdown("Produce: " + "".join(f'<span class="chip mineral">{m}</span>' for m in f["minerales"]),
                unsafe_allow_html=True)
st.write("")

k = st.columns(6)
k[0].metric("Unidades mineras", len(p.unidades))
k[1].metric(
    "Pobreza media donde opera",
    "—" if p.unidades["pobreza"].dropna().empty else f"{p.unidades['pobreza'].mean():.1f} %",
)
k[2].metric("Multas firmes", soles(p.multas["multa_soles"].sum()) if not p.multas.empty else "0")
k[3].metric("Expedientes OEFA", len(p.ruias))
k[4].metric("Obras por impuestos", f"{len(p.oxi)}")
k[5].metric("Reportes de conflictos", p.conflictos["reporte"].nunique() if not p.conflictos.empty else 0)

t_op, t_prod, t_san, t_oxi, t_conf, t_ficha, t_met = st.tabs(
    ["Dónde opera", "Producción y canon", "Sanciones ambientales", "Obras por Impuestos", "Conflictos",
     "Ficha de pauta (IA)", "Cómo se cruzó"]
)

with t_prod:
    a, b2 = st.columns(2)
    inv25 = f.get("inversion_2025_usd")
    a.metric("Inversión minera 2025", "—" if pd.isna(inv25) else f"US$ {inv25 / 1e6:,.1f} mill.")
    inv24 = f.get("inversion_2024_usd")
    b2.metric("Inversión minera 2024", "—" if pd.isna(inv24) else f"US$ {inv24 / 1e6:,.1f} mill.")
    st.markdown("##### Producción declarada al MINEM")
    if p.produccion.empty:
        st.caption("No figura entre las empresas productoras de metales del Anuario Minero 2025.")
    else:
        pr = p.produccion.pivot_table(index=["metal", "unidad"], columns="anio", values=["cantidad", "participacion"])
        tabla = pd.DataFrame({
            "Metal": [m.capitalize() for m, _ in pr.index],
            "Unidad": [u for _, u in pr.index],
            "2024": pr[("cantidad", 2024)].values if ("cantidad", 2024) in pr else None,
            "2025": pr[("cantidad", 2025)].values if ("cantidad", 2025) in pr else None,
            "% del país 2025": (pr[("participacion", 2025)].values * 100) if ("participacion", 2025) in pr else None,
        }).sort_values("% del país 2025", ascending=False)
        st.dataframe(tabla, hide_index=True, use_container_width=True, column_config={
            "2024": st.column_config.NumberColumn(format="%,.0f"),
            "2025": st.column_config.NumberColumn(format="%,.0f"),
            "% del país 2025": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100),
        })
        st.caption("Fuente: MINEM, Anuario Minero 2025 (datos de 2025 preliminares).")
    st.markdown("##### Canon y regalías de los departamentos donde opera (2025)")
    t = p.transferencias_donde_opera()
    if t.empty:
        st.caption("Sin unidades mineras ubicadas en el registro usado.")
    else:
        st.dataframe(
            t.assign(departamento=t["departamento"].str.title()).rename(columns={
                "departamento": "Departamento", "canon minero": "Canon minero (S/)",
                "regalías mineras": "Regalías (S/)", "derecho de vigencia y penalidad": "Derecho de vigencia (S/)"}),
            hide_index=True, use_container_width=True,
            column_config={c: st.column_config.NumberColumn(format="%,.0f") for c in
                           ["Canon minero (S/)", "Regalías (S/)", "Derecho de vigencia (S/)"]},
        )
        st.caption("Transferencias del MEF a todo el departamento por toda la actividad minera de la región, "
                   "no solo por esta empresa. Fuente: MEF e INGEMMET, vía Anuario Minero 2025.")

with t_op:
    if p.unidades.empty:
        st.info("Esta empresa no tiene unidades en la lista de unidades mineras en producción del MINEM usada aquí.")
    else:
        D = distritos()
        deps = set(p.unidades["region"].str.upper())
        vista = D[D["NOMBDEP"].isin(deps)]
        col_m, col_t = st.columns([1.5, 1], gap="large")
        with col_m:
            st_folium(M.construir(vista, p.unidades, None, encuadrar=True), height=460,
                      use_container_width=True, returned_objects=[], key=f"mapa-{elegida}")
        with col_t:
            tabla = p.unidades.assign(
                Distrito=p.unidades["distrito"].str.title(),
                Región=p.unidades["region"].str.title(),
                Ubicación=p.unidades["punto_coincide"].map({True: "coincide", False: "por verificar"}),
            )[["unidad", "Distrito", "Región", "producto", "pobreza", "Ubicación"]]
            st.dataframe(
                tabla.rename(columns={"unidad": "Unidad", "producto": "Producto", "pobreza": "Pobreza (%)"}),
                hide_index=True, use_container_width=True,
                column_config={"Pobreza (%)": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100)},
            )
            st.caption(
                "Pobreza monetaria del distrito (INEI). «Por verificar»: las coordenadas del registro "
                "caen fuera del distrito que declara su UBIGEO."
            )

with t_san:
    st.markdown("##### Multas firmes (OEFA, 2024–2025)")
    if p.multas.empty:
        st.caption("Sin multas firmes registradas en este periodo.")
    else:
        st.dataframe(
            p.multas[["anio", "unidad", "distrito", "infraccion", "expediente", "multa_soles"]]
            .sort_values("multa_soles", ascending=False)
            .rename(columns={"anio": "Año", "unidad": "Unidad", "distrito": "Distrito", "infraccion": "Infracción",
                             "expediente": "Expediente", "multa_soles": "Multa (S/)"}),
            hide_index=True, use_container_width=True,
            column_config={"Multa (S/)": st.column_config.NumberColumn(format="%.2f")},
        )
    st.markdown("##### Historial de sanciones (RUIAS, 2017–2023)")
    if p.ruias.empty:
        st.caption("Sin expedientes en el Registro Único de Infractores Ambientales Sancionados.")
    else:
        r = p.ruias.copy()
        r["multa_uit"] = pd.to_numeric(r["multa_uit"], errors="coerce")
        st.dataframe(
            r[["anio", "expediente", "unidad", "distrito", "sancion", "infracciones", "multa_uit"]]
            .sort_values("anio", ascending=False)
            .rename(columns={"anio": "Año", "expediente": "Expediente", "unidad": "Unidad", "distrito": "Distrito",
                             "sancion": "Sanción", "infracciones": "Tipo de infracción", "multa_uit": "Multa (UIT)"}),
            hide_index=True, use_container_width=True,
        )
        st.caption(
            "Montos en UIT según el diccionario del OEFA. Son sanciones impuestas, no necesariamente firmes: "
            "no se suman con la tabla de multas firmes."
        )

with t_oxi:
    if p.oxi.empty:
        st.info("No figura como financista en la lista de obras por impuestos de ProInversión.")
    else:
        donde = p.obras_donde_opera()
        a, b, c3 = st.columns(3)
        a.metric("Inversión total de sus obras", f"S/ {p.oxi['monto_mill'].sum():,.1f} millones")
        b.metric("Obras en consorcio", int((p.oxi["n_empresas"] > 1).sum()))
        c3.metric("Obras en distritos donde opera", len(donde))
        por_fun = p.oxi.groupby("funcion")["monto_mill"].sum().sort_values()
        st.bar_chart(por_fun, horizontal=True, color="#FADD00", x_label="Millones de soles", y_label="")
        st.dataframe(
            p.oxi.assign(en_su_distrito=p.oxi["IDDIST"].isin(p.distritos_operacion).map({True: "sí", False: ""}))[
                ["anio", "obra", "funcion", "estado", "distrito", "departamento", "pobreza", "monto_mill",
                 "n_empresas", "en_su_distrito", "cui"]
            ]
            .sort_values("anio", ascending=False)
            .rename(columns={"anio": "Año", "obra": "Obra", "funcion": "Función", "estado": "Estado",
                             "distrito": "Distrito", "departamento": "Departamento", "pobreza": "Pobreza (%)",
                             "monto_mill": "Monto (S/ mill.)", "n_empresas": "Empresas financistas",
                             "en_su_distrito": "Donde opera", "cui": "CUI"}),
            hide_index=True, use_container_width=True,
            column_config={"CUI": st.column_config.NumberColumn(format="%d"),
                           "Pobreza (%)": st.column_config.NumberColumn(format="%.1f")},
        )
        st.caption(
            "Monto total de cada obra según ProInversión; si hubo varias empresas financistas, el monto es "
            "compartido. Con el CUI se puede revisar cada obra en Invierte.pe."
        )

with t_conf:
    if p.conflictos.empty:
        st.info("No aparece mencionada en los reportes de conflictos sociales n.º 268, 269 y 270.")
    else:
        for n, grupo in p.conflictos.groupby("reporte", sort=False):
            st.markdown(f"##### Reporte n.º {n} · [abrir el original]({grupo['url'].iloc[0]})")
            for frag in grupo["fragmento"].head(3):
                st.markdown(f"<div class='fragmento'>…{frag}…</div>", unsafe_allow_html=True)
                st.write("")
        st.caption(
            "Fragmentos extraídos automáticamente del PDF. El diseño a dos columnas del reporte desordena "
            "el texto: lee siempre el caso en el original."
        )

with t_ficha:
    clave = clave_gemini()
    if not clave:
        clave = st.text_input("Clave de Gemini (opcional)", type="password",
                              help="Sin clave, la ficha se arma con reglas fijas. La clave no se guarda.") or None
    if st.button("Generar ficha de pauta", type="primary"):
        modo = "Gemini (salida estructurada)" if clave else "modo sin IA (reglas fijas)"
        try:
            with st.spinner("Escribiendo la ficha…"):
                ficha = P.generar_con_gemini(p, clave) if clave else P.generar_sin_ia(p)
        except Exception as e:
            st.warning(f"No se pudo usar Gemini ({type(e).__name__}). Uso el modo sin IA.")
            ficha, modo = P.generar_sin_ia(p), "modo sin IA (respaldo)"
        st.session_state["ficha"] = (elegida, ficha, modo)

    guardada = st.session_state.get("ficha")
    if guardada and guardada[0] == elegida:
        _, ficha, modo = guardada
        sueltas = P.verificar(ficha, p)
        if sueltas:
            st.markdown('<div class="alerta"><b>Revisar:</b> estas cifras no están en los registros: '
                        + "; ".join(sueltas) + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="verificado">Cada cifra de la ficha está en los registros del escáner.</div>',
                        unsafe_allow_html=True)
        md = P.como_markdown(ficha, p.nombre, modo)
        st.markdown(md.split("\n", 3)[3].replace("\n## ", "\n#### ", 1).replace("\n## ", "\n##### "))
        st.download_button("Descargar ficha (.md)", md, file_name=f"pauta_{elegida}.md")
    else:
        st.caption("La IA recibe solo los registros de esta empresa y propone titular, pregunta, datos con fuente, "
                   "actores, preguntas de entrevista, lo que falta verificar y riesgos de campo.")
    with st.expander("Contexto exacto que recibe la IA"):
        st.code(p.como_texto(), language=None)

with t_met:
    st.markdown("Ninguna fuente usa un identificador común. El escáner cruza **por RUC** cuando la fuente lo trae "
                "y **por nombre normalizado** cuando no (sin tildes, puntuación ni forma societaria). "
                "Estos son los nombres que se unieron en este perfil:")
    st.dataframe(p.alias[["fuente", "nombre_en_fuente", "coincidencia"]].rename(
        columns={"fuente": "Fuente", "nombre_en_fuente": "Nombre en la fuente", "coincidencia": "Cruce"}),
        hide_index=True, use_container_width=True)
    st.markdown("**Fuentes**\n\n" + "\n".join(f"- [{k}] {v}" for k, v in FUENTES.items()))
