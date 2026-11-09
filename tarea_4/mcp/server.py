"""Servidor MCP del BCRP para la Tarea 4: series oficiales + producción minera por departamento.

    uv run pytest                                  # 8 pruebas originales + 2 de las herramientas propias
    uv run mcp/server.py                           # el servidor, por stdio
    claude mcp add --scope project bcrp -- uv run mcp/server.py

Las cuentas las hace Python, no el modelo: cada cifra sale de una llamada que se puede repetir.

Herramientas
    buscar_series                     buscar códigos en el catálogo oficial (17 mil series)
    serie                             descargar datos de una serie entre dos fechas
    resumen                           primero, último, cambio, variación %, promedio, máximo y mínimo
    produccion_minera_departamental   (propia) producción minera por departamento y su valor estimado en US$
    graficar_serie                    (propia) gráfico PNG de una serie oficial, guardado en figuras/
    comparar_paises                   (propia, Sesión 04) comparación internacional con el Banco Mundial
Recurso   bcrp://serie/{codigo}       ficha descriptiva de una serie
Prompts   informe(tema), informe_minero(anio)
"""
import re
import time
import unicodedata
from functools import cache
from pathlib import Path

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

AQUI = Path(__file__).parent
RAIZ = AQUI.parent
CATALOGO = RAIZ / "datos" / "catalogo_bcrp.csv"
SALIDAS = RAIZ / "salidas"
FIGURAS = RAIZ / "figuras"
URL_CATALOGO = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}

mcp = FastMCP("bcrp", instructions=(
    "Series oficiales del Banco Central de Reserva del Perú (BCRP). Primero busca el código con buscar_series; "
    "luego usa resumen para variaciones, promedios y extremos, y serie para los datos. Para la minería por "
    "departamento usa produccion_minera_departamental. No calcules a mano: cita siempre el código de la serie, "
    "el periodo y la URL de la fuente."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


@cache
def catalogo():
    """El catálogo oficial: 17 mil series en unos 7 MB. Se baja una vez y queda en datos/."""
    if not CATALOGO.exists():
        CATALOGO.parent.mkdir(exist_ok=True)
        r = httpx.get(URL_CATALOGO, timeout=120)
        r.raise_for_status()
        CATALOGO.write_text(r.content.decode("latin-1"), encoding="utf-8")
    df = pd.read_csv(CATALOGO, sep=";", dtype=str).fillna("")
    df = df.rename(columns={"Código de serie": "codigo", "Categoría de serie": "categoria", "Grupo de serie": "grupo",
                            "Nombre de serie": "nombre", "Frecuencia": "frecuencia",
                            "Fecha de actualización": "actualizada", "Fecha de inicio": "inicio"})
    df["texto"] = (df.categoria + " " + df.grupo + " " + df.nombre).map(_sin_tildes)
    return df


def _ficha(codigo):
    fila = catalogo().query("codigo == @codigo")
    if fila.empty:
        raise ToolError(f"No existe el código de serie {codigo!r}. Búsquenlo con buscar_series.")
    f = fila.iloc[0]
    return {"codigo": f.codigo, "nombre": f"{f.grupo} - {f.nombre}", "categoria": f.categoria,
            "frecuencia": f.frecuencia, "inicio": f.inicio, "actualizada": f.actualizada}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_series(texto: str, frecuencia: str | None = None, limite: int = 10) -> list[dict]:
    """Busca series del BCRP por palabras: todas deben aparecer en la categoría, el grupo o el nombre.

    Ejemplos: "ipc 12 meses", "tipo de cambio interbancario venta", "reservas internacionales netas",
    "tasa de referencia", "cobre precio", "canon regalias", "mineros departamentos cobre".
    frecuencia: "Diaria", "Mensual", "Trimestral" o "Anual".
    Devuelve el código, el nombre completo, la frecuencia y desde cuándo hay datos. Si no hay resultados,
    prueben con menos palabras.
    """
    df = catalogo()
    m = pd.Series(True, index=df.index)
    for palabra in _sin_tildes(texto).split():
        m &= df.texto.str.contains(re.escape(palabra))
    if frecuencia:
        m &= df.frecuencia.str.lower() == frecuencia.lower()
    # primero las series vigentes y, entre ellas, las de nombre más corto (las más generales)
    sel = df[m]
    orden = sel.assign(vieja=sel.actualizada < "2025", largo=(sel.grupo + sel.nombre).str.len())
    return [_ficha(c) for c in orden.sort_values(["vieja", "largo"]).head(limite).codigo]


MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
_descargas = {}


def _fecha_api(fecha, frecuencia, final=False):
    """Convierte "2025-01", "2025-T1", "2025-01-15" o "2025" al formato que pide la API según la frecuencia."""
    partes = str(fecha).strip().upper().replace("/", "-").split("-")
    anio = int(partes[0])
    frecuencia = frecuencia.lower()
    if frecuencia == "anual":
        return f"{anio}"
    if frecuencia == "trimestral":
        if len(partes) == 1:
            return f"{anio}-{4 if final else 1}"
        if partes[1].startswith("T"):
            return f"{anio}-{int(partes[1][1:])}"
        return f"{anio}-{(int(partes[1]) - 1) // 3 + 1}"   # un mes: su trimestre
    if frecuencia == "diaria":
        mes = int(partes[1]) if len(partes) > 1 else (12 if final else 1)
        if len(partes) > 2:
            dia = int(partes[2])
        else:
            dia = pd.Period(f"{anio}-{mes:02d}", "M").days_in_month if final else 1
        return f"{anio}-{mes:02d}-{dia:02d}"
    mes = int(partes[1]) if len(partes) > 1 else (12 if final else 1)   # mensual
    return f"{anio}-{mes}"


def _periodo(nombre):
    """Pasa los nombres de la API a ISO: "Ene.2025" -> "2025-01", "01.Oct.26" -> "2026-10-01",
    "T1.25" -> "2025-T1", "2025" -> "2025"."""
    p = nombre.split(".")
    if len(p) == 1:
        return p[0]
    if len(p) == 3:
        return f"20{p[2][-2:]}-{MESES[p[1][:3].lower()]:02d}-{int(p[0]):02d}"
    if p[0].upper().startswith("T"):
        return f"20{p[1][-2:]}-T{p[0][1:]}"
    return f"{p[1]}-{MESES[p[0][:3].lower()]:02d}"


def _descargar(url, intentos=4):
    """Pide la URL a la API; si responde HTML (límite de pedidos), espera y reintenta. Guarda en caché."""
    if url not in _descargas:
        for i in range(intentos):
            try:
                r = httpx.get(url, timeout=60, headers={"User-Agent": "mcp-bcrp/0.2"})
                _descargas[url] = r.json()
                break
            except (ValueError, httpx.HTTPError):
                if i == intentos - 1:
                    raise ToolError(f"El BCRP no respondió con datos para {url}. Reintenten en unos segundos.")
                time.sleep(2 * (i + 1))
    return _descargas[url]


def _valor(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None   # "n.d." y similares


@mcp.tool(annotations=SOLO_LECTURA)
def serie(codigo: str, desde: str, hasta: str) -> dict:
    """Descarga los datos de una serie del BCRP entre dos fechas. Úsenla cuando necesiten los valores periodo a
    periodo; para variaciones, promedios o extremos usen resumen.

    codigo: el código de buscar_series, por ejemplo "PN01273PM". desde/hasta según la frecuencia de la serie:
    mensual "2025-01", trimestral "2025-T1", diaria "2026-10-15", anual "2025".
    Devuelve el nombre, la frecuencia, los datos [{"periodo", "valor"}] y la URL de la fuente.
    """
    codigo = codigo.strip().upper()
    ficha = _ficha(codigo)
    url = (f"{API}/{codigo}/json/{_fecha_api(desde, ficha['frecuencia'])}/"
           f"{_fecha_api(hasta, ficha['frecuencia'], final=True)}")
    respuesta = _descargar(url)
    datos = [{"periodo": _periodo(p["name"]), "valor": v} for p in respuesta.get("periods", [])
             if (v := _valor(p["values"][0])) is not None]
    if not datos:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}. Su primer dato es {ficha['inicio']}.")
    return {"codigo": codigo, "nombre": ficha["nombre"], "frecuencia": ficha["frecuencia"], "datos": datos,
            "fuente": url}


@mcp.tool(annotations=SOLO_LECTURA)
def resumen(codigo: str, desde: str, hasta: str) -> dict:
    """Resume una serie del BCRP entre dos fechas: primer y último valor, cambio absoluto, variación porcentual,
    promedio, suma, máximo y mínimo (con su periodo). Úsenla siempre en vez de hacer cuentas a mano.

    Mismos argumentos que serie, por ejemplo codigo="PN01273PM", desde="2025-12", hasta="2026-09".
    """
    s = serie(codigo, desde, hasta)
    d = pd.DataFrame(s["datos"])
    primero, ultimo = d.iloc[0], d.iloc[-1]
    punto = lambda f: {"periodo": f.periodo, "valor": float(f.valor)}
    return {"codigo": s["codigo"], "nombre": s["nombre"], "frecuencia": s["frecuencia"], "n": len(d),
            "primero": punto(primero), "ultimo": punto(ultimo),
            "cambio": round(float(ultimo.valor - primero.valor), 6),
            "variacion_pct": (round(float((ultimo.valor / primero.valor - 1) * 100), 4) if primero.valor else None),
            "promedio": round(float(d.valor.mean()), 6), "suma": round(float(d.valor.sum()), 6),
            "maximo": punto(d.loc[d.valor.idxmax()]), "minimo": punto(d.loc[d.valor.idxmin()]),
            "fuente": s["fuente"]}


# ---------------------------------------------------------------------------------------------------------------
# Herramienta propia 1 · producción minera por departamento
# ---------------------------------------------------------------------------------------------------------------
GRUPO_MINERO = "Producción de productos mineros según departamentos"
# Precio promedio de exportación (BCRP, mensual) y factor para pasar la unidad de producción a la unidad del precio.
#   tm.f -> libras: 2204.62 lb; el precio está en ¢US$/lb, por eso /100.   grs.f -> onzas troy: /31.1035.
PRECIOS = {
    "cobre": ("PN38784BM", 2204.62 / 100),
    "oro": ("PN38793BM", 1 / 31.1035),
    "plata": ("PN38796BM", 1000 / 31.1035),      # producción en kg.f
    "zinc": ("PN38802BM", 2204.62 / 100),
    "plomo": ("PN38799BM", 2204.62 / 100),
    "molibdeno": ("PN38805BM", 2204.62 / 100),
}
CCDD = {"amazonas": "01", "ancash": "02", "apurimac": "03", "arequipa": "04", "ayacucho": "05", "cajamarca": "06",
        "callao": "07", "cusco": "08", "huancavelica": "09", "huanuco": "10", "ica": "11", "junin": "12",
        "la libertad": "13", "lambayeque": "14", "lima": "15", "loreto": "16", "madre de dios": "17",
        "moquegua": "18", "pasco": "19", "piura": "20", "puno": "21", "san martin": "22", "tacna": "23",
        "tumbes": "24", "ucayali": "25"}


def _series_mineras(metal):
    """Las series anuales del grupo minero departamental para un metal: [(codigo, departamento, unidad)]."""
    df = catalogo()
    sel = df[(df.grupo == GRUPO_MINERO) & (df.frecuencia == "Anual")]
    filas = []
    for f in sel.itertuples():
        m = re.match(r"\s*(\w+)\s*-\s*(.+?)\s*\(([^)]+)\)", f.nombre)
        if m and _sin_tildes(m.group(1)) == metal:
            filas.append((f.codigo, m.group(2).strip(), m.group(3).strip()))
    return filas


def _anual_varias(codigos, anio):
    """Pide hasta 10 series anuales en una sola llamada a la API (los códigos van unidos con "-")."""
    valores = {}
    for i in range(0, len(codigos), 10):
        grupo = codigos[i:i + 10]
        url = f"{API}/{'-'.join(grupo)}/json/{anio}/{anio}"
        r = _descargar(url)
        periodos = r.get("periods", [])
        for j, c in enumerate(grupo):
            valores[c] = _valor(periodos[0]["values"][j]) if periodos else None
    return valores


@mcp.tool(annotations=SOLO_LECTURA)
def produccion_minera_departamental(anio: int = 2024, metales: str = "cobre,oro,plata,zinc,plomo",
                                    guardar: bool = True) -> dict:
    """Producción minera metálica por departamento para un año, con su valor estimado en millones de US$.

    Úsenla cuando pregunten cuánto produce la minería en cada región o qué departamentos son mineros.
    Fuente: BCRP, «Producción de productos mineros según departamentos» (series anuales RD…DA, datos del MINEM),
    y los precios promedio de exportación del BCRP (PN387…BM) del mismo año.
    metales: lista separada por comas entre cobre, oro, plata, zinc, plomo y molibdeno.
    valor_musd = cantidad × precio promedio anual × factor de unidades. Es una VALORIZACIÓN APROXIMADA a precios
    de exportación, no el valor bruto de producción oficial.
    Devuelve las filas por departamento y metal (con el código de cada serie), el total valorizado por
    departamento, la cobertura frente a la serie «Total» de cada metal y las URL usadas. Con guardar=True escribe
    salidas/produccion_minera_<anio>.csv para que las Skills la crucen con la ENAHO.
    """
    pedidos = [_sin_tildes(m.strip()) for m in metales.split(",") if m.strip()]
    malos = [m for m in pedidos if m not in PRECIOS]
    if malos or not pedidos:
        raise ToolError(f"Metal no soportado: {malos or metales!r}. Usen: {', '.join(PRECIOS)}.")
    filas, cobertura, fuentes = [], {}, []
    for metal in pedidos:
        series = _series_mineras(metal)
        if not series:
            raise ToolError(f"No hay series departamentales anuales para {metal} en el catálogo del BCRP.")
        valores = _anual_varias([c for c, _, _ in series], anio)
        fuentes.append(f"{API}/{'-'.join(c for c, _, _ in series[:10])}/json/{anio}/{anio}")
        cod_precio, factor = PRECIOS[metal]
        try:
            precio = resumen(cod_precio, f"{anio}-01", f"{anio}-12")["promedio"]
            fuentes.append(f"{API}/{cod_precio}/json/{anio}-1/{anio}-12")
        except ToolError:
            precio = None
        total = None
        for codigo, depto, unidad in series:
            v = valores.get(codigo)
            if _sin_tildes(depto) == "total":
                total = v
                continue
            if v is None:
                continue
            filas.append({"metal": metal, "ccdd": CCDD.get(_sin_tildes(depto), ""), "departamento": depto,
                          "cantidad": v, "unidad": unidad, "codigo_serie": codigo,
                          "precio_promedio": precio, "codigo_precio": cod_precio,
                          "valor_musd": round(v * factor * precio / 1e6, 3) if precio else None})
        suma = sum(f["cantidad"] for f in filas if f["metal"] == metal)
        cobertura[metal] = {"total_nacional": total, "suma_departamentos": round(suma, 3),
                            "cobertura_pct": round(100 * suma / total, 2) if total else None}
    if not filas:
        raise ToolError(f"El BCRP no tiene datos de producción minera departamental para {anio}.")
    df = pd.DataFrame(filas)
    por_depto = (df.groupby(["ccdd", "departamento"], as_index=False).valor_musd.sum()
                 .sort_values("valor_musd", ascending=False))
    if guardar:
        SALIDAS.mkdir(exist_ok=True)
        df.to_csv(SALIDAS / f"produccion_minera_{anio}.csv", index=False)
    return {"anio": anio, "metales": pedidos, "filas": filas,
            "valor_por_departamento_musd": por_depto.round(3).to_dict("records"),
            "cobertura": cobertura, "archivo": str(SALIDAS / f"produccion_minera_{anio}.csv") if guardar else None,
            "nota": "Valor estimado = cantidad × precio promedio de exportación del año; aproximación, no VBP oficial.",
            "fuente": fuentes}


# ---------------------------------------------------------------------------------------------------------------
# Herramienta propia 2 · gráfico de una serie oficial
# ---------------------------------------------------------------------------------------------------------------
@mcp.tool
def graficar_serie(codigo: str, desde: str, hasta: str, titulo: str | None = None) -> dict:
    """Grafica una serie del BCRP entre dos fechas y guarda un PNG en figuras/bcrp_<codigo>.png.

    El gráfico lleva el nombre y el código de la serie, el periodo y la fuente. Devuelve la ruta del archivo,
    el número de datos y la URL usada. Mismos argumentos que serie.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = serie(codigo, desde, hasta)
    d = pd.DataFrame(s["datos"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(range(len(d)), d.valor, color="#1f4e79", lw=2)
    paso = max(1, len(d) // 10)
    ax.set_xticks(range(0, len(d), paso), d.periodo[::paso], rotation=45, ha="right")
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(titulo or f"{s['nombre']}\n{d.periodo.iloc[0]} a {d.periodo.iloc[-1]}", fontsize=11, loc="left")
    fig.text(0.01, 0.01, f"Fuente: BCRP, serie {s['codigo']} ({s['frecuencia'].lower()}).", fontsize=8, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    FIGURAS.mkdir(exist_ok=True)
    ruta = FIGURAS / f"bcrp_{s['codigo']}.png"
    fig.savefig(ruta, dpi=200)
    plt.close(fig)
    return {"archivo": str(ruta), "codigo": s["codigo"], "n": len(d), "fuente": s["fuente"]}


# ---------------------------------------------------------------------------------------------------------------
# Herramienta de la Sesión 04 · comparación internacional
# ---------------------------------------------------------------------------------------------------------------
@mcp.tool(annotations=SOLO_LECTURA)
def comparar_paises(indicador: str = "NY.GDP.MKTP.KD.ZG", paises: str = "PER;CHL;COL;MEX;BRA",
                    desde: int = 2015, hasta: int = 2025) -> dict:
    """Compara al Perú con otros países usando la API del Banco Mundial (el BCRP solo publica datos del Perú).

    indicador: código del Banco Mundial, por ejemplo "NY.GDP.MKTP.KD.ZG" (crecimiento del PBI real, %),
    "FP.CPI.TOTL.ZG" (inflación, %), "SI.POV.NAHC" (pobreza nacional, %). paises: ISO3 separados por ";".
    """
    url = (f"https://api.worldbank.org/v2/country/{paises}/indicator/{indicador}"
           f"?format=json&date={desde}:{hasta}&per_page=1000")
    try:
        r = httpx.get(url, timeout=60, follow_redirects=True)
        meta, filas = r.json()
    except (ValueError, httpx.HTTPError):
        raise ToolError(f"El Banco Mundial no respondió con datos para {url}.")
    if not filas:
        raise ToolError(f"Sin datos para el indicador {indicador!r} y los países {paises!r}.")
    valores = {}
    for f in filas:
        if f["value"] is not None:
            valores.setdefault(f["country"]["value"], {})[f["date"]] = round(f["value"], 4)
    return {"indicador": indicador, "nombre": filas[0]["indicator"]["value"],
            "valores": {p: dict(sorted(v.items())) for p, v in valores.items()}, "fuente": url}


# ---------------------------------------------------------------------------------------------------------------
# Recurso y prompts
# ---------------------------------------------------------------------------------------------------------------
@mcp.resource("bcrp://serie/{codigo}", mime_type="application/json")
def ficha_serie(codigo: str) -> dict:
    """Ficha de una serie del BCRP: nombre, categoría, frecuencia, desde cuándo hay datos y última actualización."""
    return _ficha(codigo.strip().upper())


@mcp.prompt
def informe(tema: str) -> str:
    """Pide un informe breve sobre un tema económico del Perú con cifras oficiales del BCRP."""
    return (f"Escribe un informe breve sobre «{tema}» en el Perú con datos oficiales del BCRP.\n"
            "1. Usa buscar_series para encontrar las series relevantes.\n"
            "2. Usa resumen (no cuentas a mano) para la evolución del último año y serie si necesitas el detalle.\n"
            "3. Cita el código de serie, el periodo y la URL de la fuente de cada cifra.\n"
            "4. Cierra con tres puntos clave. Si un dato no existe, dilo en vez de estimarlo.")


@mcp.prompt
def informe_minero(anio: int = 2024) -> str:
    """Pide interpretar la minería por departamento frente a la pobreza de la ENAHO, sin conclusiones causales."""
    return (f"Analiza la minería peruana en {anio}.\n"
            f"1. Llama a produccion_minera_departamental(anio={anio}) y reporta los 5 departamentos con mayor valor.\n"
            "2. Usa resumen con PN01760AM (índice de minería metálica) y PN37897FM (canon y regalías) para el contexto.\n"
            "3. Cruza con la pobreza monetaria de la ENAHO usando la skill cruzando-mineria.\n"
            "4. Cita el código de serie y el periodo de cada cifra; describe asociaciones, nunca causalidad.")


if __name__ == "__main__":
    mcp.run()
