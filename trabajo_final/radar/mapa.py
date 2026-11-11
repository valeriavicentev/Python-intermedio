"""Mapa interactivo con Folium: pobreza distrital + unidades mineras."""

from __future__ import annotations

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd

NEGRO = "#000000"
ROJO = "#FA2400"
AMARILLO = "#FADD00"
GRIS = "#F6F6F6"

# Escala de grises: más oscuro = más pobreza. El rojo queda libre para la minería.
# Fondo negro: más pobreza = gris más claro (más visible). El rojo queda para la minería.
ESCALA = cm.LinearColormap(
    ["#262626", "#6E6E6E", "#BDBDBD", "#F6F6F6"],
    vmin=0,
    vmax=80,
    caption="Pobreza monetaria del distrito (%)",
)


# Leyenda en HTML propio: la de branca depende de d3 desde un CDN externo y,
# si ese CDN falla, el mapa entero no se dibuja.
LEYENDA = """
<div style="position: fixed; bottom: 24px; left: 12px; z-index: 9999; background: #000000; border: 1px solid #F6F6F6;
            padding: 8px 10px; border-radius: 6px; 
            font: 12px Inter, Arial, sans-serif; color: #F6F6F6;">
  <div style="font-weight: 600; margin-bottom: 4px;">Pobreza del distrito</div>
  <div style="width: 160px; height: 10px;
              background: linear-gradient(to right, #262626, #6E6E6E, #BDBDBD, #F6F6F6);
              border: 1px solid #6E6E6E;"></div>
  <div style="display: flex; justify-content: space-between; width: 160px;">
    <span>0 %</span><span>40 %</span><span>80 %</span></div>
  <div style="margin-top: 6px;"><span style="display:inline-block;width:10px;height:10px;
       border-radius:50%;background:#FA2400;"></span> Unidad minera</div>
  <div><span style="display:inline-block;width:8px;height:8px;border-radius:50%;
       border:2px dashed #FA2400;"></span> Ubicación por verificar</div>
</div>
"""


def construir(
    distritos: gpd.GeoDataFrame,
    unidades: pd.DataFrame,
    seleccionado: str | None = None,
    encuadrar: bool = False,
) -> folium.Map:
    if seleccionado and (distritos["IDDIST"] == seleccionado).any():
        foco = distritos.loc[distritos["IDDIST"] == seleccionado].geometry.iloc[0].centroid
        centro, zoom = [foco.y, foco.x], 9
    else:
        b = distritos.total_bounds
        centro, zoom = [(b[1] + b[3]) / 2, (b[0] + b[2]) / 2], 6

    mapa = folium.Map(location=centro, zoom_start=zoom, tiles=None, control_scale=True)
    folium.TileLayer(
        # CARTO ahora exige clave de API; Esri ofrece su mapa base gris oscuro sin clave
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap",
        max_zoom=16,
        name="Mapa base",
        control=False,
    ).add_to(mapa)

    def estilo(feature):
        p = feature["properties"]
        pobreza = p.get("pobreza")
        es_sel = p["IDDIST"] == seleccionado
        return {
            "fillColor": ESCALA(pobreza) if pobreza is not None else "#FFFFFF",
            "color": AMARILLO if es_sel else "#000000",
            "weight": 3 if es_sel else 0.3,
            "fillOpacity": 0.75,
        }

    capa = distritos[
        ["IDDIST", "NOMBDIST", "NOMBDEP", "pobreza", "unidades_dentro", "unidades_20km", "geometry"]
    ].copy()
    capa["pobreza_txt"] = capa["pobreza"].map(lambda v: "sin dato" if pd.isna(v) else f"{v:.1f} %")
    capa["pobreza"] = capa["pobreza"].astype(object).where(capa["pobreza"].notna(), None)

    folium.GeoJson(
        capa,
        name="Pobreza distrital",
        style_function=estilo,
        highlight_function=lambda _: {"weight": 2, "color": AMARILLO},
        tooltip=folium.GeoJsonTooltip(
            fields=["NOMBDIST", "NOMBDEP", "pobreza_txt", "unidades_dentro", "unidades_20km"],
            aliases=["Distrito", "Departamento", "Pobreza", "Unidades dentro", "Unidades a 20 km"],
        ),
    ).add_to(mapa)

    grupo = folium.FeatureGroup(name="Unidades mineras").add_to(mapa)
    for _, u in unidades.iterrows():
        verificar = not u["punto_coincide"]
        folium.CircleMarker(
            location=[u["LATITUD"], u["LONGITUD"]],
            radius=6,
            color=ROJO,
            weight=2,
            fill=not verificar,
            fill_color=ROJO,
            fill_opacity=0.9,
            dash_array="3" if verificar else None,
            tooltip=(
                f"<b>{u['unidad']}</b><br>{u['titular']}<br>{u['producto']}"
                + ("<br><i>Coordenadas fuera de su distrito: verificar</i>" if verificar else "")
            ),
        ).add_to(grupo)

    if encuadrar and len(unidades):
        lat, lon = unidades["LATITUD"], unidades["LONGITUD"]
        mapa.fit_bounds([[lat.min() - 0.6, lon.min() - 0.6], [lat.max() + 0.6, lon.max() + 0.6]])

    mapa.get_root().html.add_child(folium.Element(LEYENDA))
    folium.LayerControl(collapsed=True).add_to(mapa)
    return mapa


def ficha_unidad(u: pd.Series, produccion_html: str = "", aproximada: bool = False) -> str:
    """Recuadro al pasar sobre una unidad: ubicación, minerales y producción declarada."""
    from radar.buscador import minerales

    def t(x):
        return str(x).title() if pd.notna(x) else "—"

    prod = (
        f"<div style='margin-top:6px;font-weight:600;'>Producción 2025 de la empresa declarada al MINEM</div>{produccion_html}"
        if produccion_html else
        "<div style='margin-top:6px;color:#666;'>La empresa no figura entre las productoras del Anuario Minero 2025.</div>"
    )
    return (
        "<div style='font:13px Inter,Arial,sans-serif;width:300px;white-space:normal;'>"
        f"<div style='font-weight:700;font-size:14px;'>{u['unidad']}</div>"
        f"<div>{u['titular']}</div>"
        f"<div style='margin-top:6px;'><b>Distrito:</b> {t(u['distrito'])}<br><b>Provincia:</b> {t(u['provincia'])}"
        f"<br><b>Región:</b> {t(u['region'])}</div>"
        + (f"<div style='margin-top:6px;color:#7A463D;'>Ubicación aproximada: centro del distrito."
           f" Fuente: {u.get('fuente_ubicacion') or 'OEFA'}."
           f"{' Distritos de la unidad: ' + u['distritos_oefa'] + '.' if isinstance(u.get('distritos_oefa'), str) else ''}</div>"
           if aproximada else
           f"<div style='margin-top:6px;'><b>Minerales:</b> {', '.join(minerales(u['producto'])) or '—'}</div>")
        + f"{prod}</div>"
    )


# ---------------------------------------------------------------------
# Portada: mapa de calor de la actividad minera en todo el Perú
# ---------------------------------------------------------------------
def mapa_calor(unidades: pd.DataFrame, produccion: dict[str, str] | None = None,
               aproximadas: pd.DataFrame | None = None) -> folium.Map:
    """Mapa base topográfico (verdes y azules, al estilo de Google Maps), calor por densidad
    de unidades mineras y un punto por unidad para ubicarlas al hacer zoom."""
    from folium.plugins import HeatMap

    mapa = folium.Map(location=[-9.3, -75.0], zoom_start=5, tiles=None, control_scale=True,
                      min_zoom=4, max_bounds=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, USGS, &copy; OpenStreetMap",
        name="Relieve", max_zoom=17,
    ).add_to(mapa)
    folium.TileLayer("OpenStreetMap", name="Calles").add_to(mapa)

    puntos = unidades[["LATITUD", "LONGITUD"]].dropna().values.tolist()
    HeatMap(
        puntos, name="Concentración de unidades", radius=26, blur=22, min_opacity=0.35, max_zoom=9,
        gradient={0.2: "#2C00FA", 0.55: "#00B4D8", 0.85: "#00FA8C", 1.0: "#FADD00"},
    ).add_to(mapa)

    grupo = folium.FeatureGroup(name="Unidades mineras").add_to(mapa)
    for _, u in unidades.dropna(subset=["LATITUD", "LONGITUD"]).iterrows():
        folium.CircleMarker(
            location=[u["LATITUD"], u["LONGITUD"]], radius=4, color="#000000", weight=1,
            fill=True, fill_color="#FA2400", fill_opacity=0.95,
            tooltip=folium.Tooltip(ficha_unidad(u, (produccion or {}).get(u["empresa_id"], "")), sticky=True),
        ).add_to(grupo)

    if aproximadas is not None and len(aproximadas):
        grupo2 = folium.FeatureGroup(name="Unidades con ubicación aproximada (OEFA o fuente pública)").add_to(mapa)
        for _, u in aproximadas.dropna(subset=["LATITUD", "LONGITUD"]).iterrows():
            folium.CircleMarker(
                location=[u["LATITUD"], u["LONGITUD"]], radius=5, color="#FADD00", weight=2.5,
                fill=True, fill_color="#000000", fill_opacity=0.6,
                tooltip=folium.Tooltip(ficha_unidad(u, (produccion or {}).get(u["empresa_id"], ""), aproximada=True),
                                       sticky=True),
            ).add_to(grupo2)

    mapa.get_root().html.add_child(folium.Element(
        """<div style="position: fixed; bottom: 24px; left: 12px; z-index: 9999; background: #000; color: #F6F6F6;
        border: 1px solid #F6F6F6; padding: 8px 10px; border-radius: 6px; font: 12px Inter, Arial, sans-serif;">
        <div style="font-weight:600;margin-bottom:4px;">Concentración de unidades mineras</div>
        <div style="width:160px;height:10px;background:linear-gradient(to right,#2C00FA,#00B4D8,#00FA8C,#FADD00);"></div>
        <div style="display:flex;justify-content:space-between;width:160px;"><span>menos</span><span>más</span></div>
        <div style="margin-top:6px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
        background:#FA2400;border:1px solid #000;"></span> Unidad en producción (MINEM)</div>
        <div><span style="display:inline-block;width:8px;height:8px;border-radius:50%;
        background:#000;border:2px solid #FADD00;"></span> Ubicación aproximada (centro del distrito)</div></div>"""
    ))
    folium.LayerControl(collapsed=True).add_to(mapa)
    return mapa
