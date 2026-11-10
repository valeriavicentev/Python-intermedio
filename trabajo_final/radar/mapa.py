"""Mapa interactivo con Folium: pobreza distrital + unidades mineras."""

from __future__ import annotations

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd

NEGRO = "#000000"
ROJO = "#F34213"
GRIS = "#F6F6F6"

# Escala de grises: más oscuro = más pobreza. El rojo queda libre para la minería.
ESCALA = cm.LinearColormap(
    ["#F6F6F6", "#BDBDBD", "#6E6E6E", "#262626"],
    vmin=0,
    vmax=80,
    caption="Pobreza monetaria del distrito (%)",
)


# Leyenda en HTML propio: la de branca depende de d3 desde un CDN externo y,
# si ese CDN falla, el mapa entero no se dibuja.
LEYENDA = """
<div style="position: fixed; bottom: 24px; left: 12px; z-index: 9999; background: white;
            padding: 8px 10px; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.25);
            font: 12px Inter, Arial, sans-serif; color: #000;">
  <div style="font-weight: 600; margin-bottom: 4px;">Pobreza del distrito</div>
  <div style="width: 160px; height: 10px;
              background: linear-gradient(to right, #F6F6F6, #BDBDBD, #6E6E6E, #262626);
              border: 1px solid #ccc;"></div>
  <div style="display: flex; justify-content: space-between; width: 160px;">
    <span>0 %</span><span>40 %</span><span>80 %</span></div>
  <div style="margin-top: 6px;"><span style="display:inline-block;width:10px;height:10px;
       border-radius:50%;background:#F34213;"></span> Unidad minera</div>
  <div><span style="display:inline-block;width:8px;height:8px;border-radius:50%;
       border:2px dashed #F34213;"></span> Ubicación por verificar</div>
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
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr="&copy; OpenStreetMap &copy; CARTO",
        name="Mapa base",
        control=False,
    ).add_to(mapa)

    def estilo(feature):
        p = feature["properties"]
        pobreza = p.get("pobreza")
        es_sel = p["IDDIST"] == seleccionado
        return {
            "fillColor": ESCALA(pobreza) if pobreza is not None else "#FFFFFF",
            "color": ROJO if es_sel else "#9E9E9E",
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
        highlight_function=lambda _: {"weight": 2, "color": NEGRO},
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
