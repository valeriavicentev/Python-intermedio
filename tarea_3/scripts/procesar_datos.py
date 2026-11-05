"""Procesa los datos originales del proyecto FEN y genera los archivos que usa el dashboard.

Entradas (datos/originales/):
  - 20XX-Gasto-Emergencias-FEN.csv   : MEF, Datos Abiertos, "Ejecucion del gasto de emergencias - FEN"
  - DETALLE_INVERSIONES.csv          : MEF, Banco de Inversiones (inversiones activas)
  - PROCESO_SELECCION.csv            : MEF, avance y valorizaciones mensuales por componente
  - DU_Fenomeno_El_Nino_2023/2026.xlsx: revision propia de los decretos de urgencia y sus anexos
  - peru_departamental.geojson, peru_distrital_simple.geojson
Salidas: datos/procesados/ y web/data/
"""
import glob, json, re, unicodedata
from pathlib import Path
import pandas as pd
from pyproj import Transformer

BASE = Path(__file__).resolve().parents[1]
ORI, PRO, WEB = BASE/'datos/originales', BASE/'datos/procesados', BASE/'web/data'
PRO.mkdir(parents=True, exist_ok=True); WEB.mkdir(parents=True, exist_ok=True)

def norm(s):
    if pd.isna(s): return ''
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s.upper().replace('-', ' ')).strip()

def num(s): return pd.to_numeric(s, errors='coerce').fillna(0)

# ---------- 1. Gasto FEN del MEF ----------
fen = pd.concat([pd.read_csv(f, dtype=str, encoding='utf-8') for f in sorted(glob.glob(str(ORI/'20*-Gasto-Emergencias-FEN.csv')))], ignore_index=True)
n0 = len(fen); fen = fen.drop_duplicates(); dup = n0 - len(fen)
for c in ['MARCO_PRESUPUESTAL', 'MONTO_CERTIFICADO', 'MONTO_COMPROMETIDO_ANUAL', 'MONTO_DEVENGADO']: fen[c] = num(fen[c])
fen['FECHA'] = pd.to_datetime(fen.FECHA_PUBLICACION, format='%d/%m/%Y', errors='coerce')
fen['NORMA'] = fen.DISPOSITIVO_LEGAL_NOMBRE.str.replace(r'\s*-\s*(ART|DCF|D\.C\.F|NUM).*$', '', regex=True).str.replace('Nº', 'N°').str.strip()
fen['TIPO_NORMA'] = fen.NORMA.str.extract(r'^(D\.U\.|D\.S\.|LEY)', expand=False).map({'D.U.': 'Decreto de urgencia', 'D.S.': 'Decreto supremo', 'LEY': 'Ley'}).fillna('Otra')
fen['DEP'] = fen.DEPARTAMENTO_META_NOMBRE.map(norm).replace({'PROVINCIA CONSTITUCIONAL DEL CALLAO': 'CALLAO'})
fen['NIVEL'] = fen.NIVEL_GOBIERNO_NOMBRE.str.title()
fen['TIPO'] = fen.TIPO_ACT_PROY_NOMBRE.str.title()
fen['EJECUTORA'] = fen.EJECUTORA_NOMBRE.str.strip()
fen['PLIEGO'] = fen.PLIEGO_NOMBRE.str.strip()

keys = ['ANO_EJE', 'NORMA', 'TIPO_NORMA', 'FECHA', 'NIVEL', 'PLIEGO', 'SEC_EJEC', 'EJECUTORA', 'DEP', 'TIPO', 'GENERICA_NOMBRE', 'FUNCION_NOMBRE']
gasto = fen.groupby(keys, dropna=False)[['MARCO_PRESUPUESTAL', 'MONTO_DEVENGADO']].sum().reset_index()
gasto.columns = ['anio', 'norma', 'tipo_norma', 'fecha', 'nivel', 'pliego', 'sec_ejec', 'ejecutora', 'departamento', 'tipo', 'generica', 'funcion', 'marco', 'devengado']
gasto['fecha'] = gasto.fecha.dt.strftime('%Y-%m-%d')
gasto['generica'] = gasto.generica.str.title(); gasto['funcion'] = gasto.funcion.str.title()
gasto[['marco', 'devengado']] = gasto[['marco', 'devengado']].round(0)
gasto.to_csv(WEB/'gasto.csv', index=False)

normas = (fen.groupby(['ANO_EJE', 'NORMA', 'TIPO_NORMA', 'FECHA']).agg(marco=('MARCO_PRESUPUESTAL', 'sum'), devengado=('MONTO_DEVENGADO', 'sum'),
          lineas=('MARCO_PRESUPUESTAL', 'size'), ejecutoras=('SEC_EJEC', 'nunique'), descripcion=('DISPOSITIVO_LEGAL_DESCRIPCION', 'first')).reset_index())
normas.columns = ['anio', 'norma', 'tipo_norma', 'fecha', 'marco', 'devengado', 'lineas', 'ejecutoras', 'descripcion']
normas['fecha'] = normas.fecha.dt.strftime('%Y-%m-%d')
normas['pct_ejec'] = (100*normas.devengado/normas.marco).round(1)
normas = normas.sort_values('fecha'); normas[['marco', 'devengado']] = normas[['marco', 'devengado']].round(0)
normas.to_csv(WEB/'normas.csv', index=False)

# ---------- 2. Proyectos con CUI ----------
proy = fen[fen.TIPO == 'Proyecto']
j = lambda x: ', '.join(sorted(set(x)))
p = (proy.groupby('PRODUCTO_PROYECTO').agg(nombre=('PRODUCTO_PROYECTO_NOMBRE', 'first'), anio=('ANO_EJE', j), norma=('NORMA', j),
     ejecutora=('EJECUTORA', 'first'), nivel=('NIVEL', 'first'), departamento=('DEP', 'first'),
     marco_fen=('MARCO_PRESUPUESTAL', 'sum'), dev_fen=('MONTO_DEVENGADO', 'sum')).reset_index().rename(columns={'PRODUCTO_PROYECTO': 'cui'}))
cuis = set(p.cui)
cols = ['CODIGO_UNICO', 'ESTADO', 'SITUACION', 'COSTO_ACTUALIZADO', 'CTRL_CONCURR', 'DES_MODALIDAD', 'AVANCE_FISICO', 'AVANCE_EJECUCION',
        'LATITUD', 'LONGITUD', 'DISTRITO', 'FEC_FIN_EJECUCION', 'ULTIMO_DEVENGADO', 'TIENE_F9', 'INFORME_CIERRE']
det = pd.concat([c[c.CODIGO_UNICO.isin(cuis)] for c in pd.read_csv(ORI/'DETALLE_INVERSIONES.csv', dtype=str, encoding='utf-8-sig', usecols=cols, chunksize=50000)])
det = det.drop_duplicates('CODIGO_UNICO').rename(columns={'CODIGO_UNICO': 'cui'})
for c in ['COSTO_ACTUALIZADO', 'CTRL_CONCURR', 'AVANCE_FISICO', 'AVANCE_EJECUCION', 'LATITUD', 'LONGITUD']: det[c] = pd.to_numeric(det[c], errors='coerce')
det.loc[(det.LATITUD == 0) | (det.LONGITUD == 0), ['LATITUD', 'LONGITUD']] = None

av = pd.concat([c[c.CODIGO_UNICO.isin(cuis)] for c in pd.read_csv(ORI/'PROCESO_SELECCION.csv', dtype=str, encoding='utf-8-sig', chunksize=500000)])
av.to_csv(PRO/'avance_componentes_fen.csv', index=False)
av['COSTO_INVERSION'] = num(av.COSTO_INVERSION); av['VALORIZ_ACUM'] = num(av.VALORIZ_ACUM); av['PERIODO'] = av.PERIODO.fillna('')
fis = av[av.DES_ETAPA.str.contains('Ejecuci', na=False)]
last = fis.groupby('CODIGO_UNICO').PERIODO.max().rename('periodo_avance').reset_index()
fl = fis.merge(last, left_on=['CODIGO_UNICO', 'PERIODO'], right_on=['CODIGO_UNICO', 'periodo_avance'])
avc = fl.groupby('CODIGO_UNICO').agg(periodo_avance=('PERIODO', 'first'), costo_comp=('COSTO_INVERSION', 'sum'), valoriz=('VALORIZ_ACUM', 'sum')).reset_index()
avc['avance_valorizado'] = (100*avc.valoriz/avc.costo_comp.where(avc.costo_comp > 0)).round(1)
etapa = av.sort_values('PERIODO').groupby('CODIGO_UNICO').DES_ETAPA.last().rename('ultima_etapa').reset_index()
avc = avc.merge(etapa, on='CODIGO_UNICO', how='outer').rename(columns={'CODIGO_UNICO': 'cui'})

p = p.merge(det, on='cui', how='left').merge(avc[['cui', 'periodo_avance', 'avance_valorizado', 'ultima_etapa']], on='cui', how='left')
p['avance'] = p.AVANCE_FISICO.where(p.AVANCE_FISICO.notna(), p.avance_valorizado)
GENERICOS = {'2000351', '2000270', '2001621'}  # codigos presupuestales genericos, no son obras
def estado(r):
    if r.cui in GENERICOS: return 'Código genérico (no es obra)'
    if pd.isna(r.ESTADO) and pd.isna(r.ultima_etapa): return 'Sin registro en el Banco de Inversiones'
    if str(r.INFORME_CIERRE).upper() in ('SI', 'SÍ', 'S', '1') or str(r.TIENE_F9).upper() in ('SI', 'SÍ', 'S', '1'): return 'Con cierre registrado'
    a = r.avance
    if pd.isna(a): return 'Activo, sin avance reportado'
    if a == 0: return 'Avance 0%'
    if a >= 99: return 'Culminado (≥ 99%)'
    return 'En ejecución'
p['estado_obra'] = p.apply(estado, axis=1)
out = p.rename(columns={'COSTO_ACTUALIZADO': 'costo_actualizado', 'CTRL_CONCURR': 'control_concurrente', 'DES_MODALIDAD': 'modalidad', 'LATITUD': 'lat', 'LONGITUD': 'lon',
                        'FEC_FIN_EJECUCION': 'fin_previsto', 'ULTIMO_DEVENGADO': 'ultimo_devengado', 'ESTADO': 'estado_bi', 'SITUACION': 'situacion_bi', 'DISTRITO': 'distrito'})
out = out[['cui', 'nombre', 'anio', 'norma', 'nivel', 'ejecutora', 'departamento', 'distrito', 'marco_fen', 'dev_fen', 'costo_actualizado', 'modalidad', 'control_concurrente',
           'estado_bi', 'situacion_bi', 'avance', 'periodo_avance', 'ultima_etapa', 'fin_previsto', 'ultimo_devengado', 'estado_obra', 'lat', 'lon']].copy()
out[['marco_fen', 'dev_fen']] = out[['marco_fen', 'dev_fen']].round(0)

# Estado oficial según la ficha SSI del MEF (servicio traeDetInvSSI, consultado el 4/11/2026; ver scripts/consultar_ssi.js)
CORTE = pd.Timestamp('2026-11-04')
ss = pd.read_csv(PRO/'estado_ssi.csv', dtype={'cui': str})
ss['fin_ejecucion'] = pd.to_datetime(ss.fin_ejecucion, dayfirst=True, format='mixed', errors='coerce')
ss['inicio_ejecucion'] = pd.to_datetime(ss.inicio_ejecucion, dayfirst=True, format='mixed', errors='coerce')
ss['avance_fisico_ssi'] = ss.avance_fisico_ssi.where(ss.avance_fisico_ssi >= 0)
ss['avance_financiero'] = (100*ss.devengado_acumulado/ss.costo_actualizado_ssi.where(ss.costo_actualizado_ssi > 0)).round(1)
out = out.drop(columns=['estado_obra', 'avance', 'periodo_avance', 'fin_previsto']).merge(ss, on='cui', how='left')
out['avance'] = out.avance_fisico_ssi
def estado2(r):
    if r.cui in GENERICOS: return 'Código genérico (no es obra)'
    if r.estado_ssi == 'CERRADO': return 'Cerrado sin culminar' if str(r.cierre_registrado).startswith('No') else 'Cerrado y culminado'
    if pd.notna(r.avance) and r.avance > 0: return 'En ejecución'
    if pd.notna(r.fin_ejecucion) and r.fin_ejecucion < CORTE: return 'Plazo vencido, sin avance registrado'
    return 'En plazo, sin avance registrado'
out['estado_obra'] = out.apply(estado2, axis=1)
# Avance según Infobras (Contraloría): último reporte de cada obra vinculada al CUI (ver scripts/consultar_ssi.js)
ib = pd.read_csv(PRO/'infobras_avance.csv', dtype={'cui': str, 'obra_infobras': str})
ib['fisico_real'] = pd.to_numeric(ib.fisico_real, errors='coerce')
ibr = ib[ib.periodo.notna()].sort_values(['cui', 'periodo', 'fisico_real'])
ult = ibr.groupby('cui').tail(1).set_index('cui')
ult['paralizada'] = pd.to_numeric(ult.paralizada, errors='coerce').eq(1)
# Si varias obras (paquetes) reportan en el mismo último periodo, el avance de Infobras es por paquete, no del proyecto
multi = ibr.merge(ult[['periodo']].reset_index(), on=['cui', 'periodo']).groupby('cui').obra_infobras.nunique()
ult['por_paquetes'] = ult.index.map(multi).fillna(1) > 1
resueltos = ib[ib.comentario.str.contains(r'resuel|resoluci|nulidad', case=False, na=False)].groupby('cui').size()
out['ib_avance'] = out.cui.map(ult.fisico_real.where(~ult.por_paquetes))
out['ib_por_paquetes'] = out.cui.map(ult.por_paquetes).fillna(False)
out['ib_periodo'] = out.cui.map(ult.periodo)
out['ib_paralizada'] = out.cui.map(ult.paralizada).fillna(False)
out['ib_comentario'] = out.cui.map(ult.comentario)
out['ib_obras'] = out.cui.map(ib.groupby('cui').size()).fillna(0).astype(int)
out['contratos_resueltos'] = out.cui.map(resueltos).fillna(0).astype(int)
def avance_txt(r):
    a, b = r.avance, r.ib_avance
    if pd.notna(a) and pd.notna(b):
        return 'coincide' if abs(a - b) <= 5 else 'difiere'
    if pd.notna(b): return 'solo Infobras'
    if pd.notna(a): return 'solo Banco de Inversiones' + (' (Infobras reporta por paquetes)' if r.ib_por_paquetes else '')
    return 'sin registro'
out['avance_fuentes'] = out.apply(avance_txt, axis=1)
out['avance_consolidado'] = out.avance.where(out.avance.notna(), out.ib_avance)
def estado3(r):
    if r.cui in GENERICOS: return 'Código genérico (no es obra)'
    if r.estado_ssi == 'CERRADO': return 'Cerrado sin culminar' if str(r.cierre_registrado).startswith('No') else 'Cerrado y culminado'
    if bool(r.ib_paralizada): return 'Paralizada'
    a = r.avance_consolidado
    if pd.notna(a) and a >= 99.5: return 'Culminada, sin cierre'
    vencido = pd.notna(r.fin_ejecucion) and r.fin_ejecucion < CORTE
    if pd.notna(a) and a > 0: return 'En ejecución, plazo vencido' if vencido else 'En ejecución'
    return 'Sin avance registrado'
out['estado_obra'] = out.apply(estado3, axis=1)
for c in ['fin_ejecucion', 'inicio_ejecucion']: out[c] = out[c].dt.strftime('%Y-%m-%d')
out.sort_values('marco_fen', ascending=False).to_csv(PRO/'proyectos_base.csv', index=False)

# Contratos SEACE e informes de control por CUI (MEF, Seguimiento de Inversiones - SSI; ver scripts/consultar_ssi.js)
ct = pd.read_csv(PRO/'contratistas.csv', dtype={'cui': str}, parse_dates=['fecha'])
fecha_fen = proy.groupby('PRODUCTO_PROYECTO').FECHA.min().rename('fecha_norma')
ct = ct.merge(fecha_fen, left_on='cui', right_index=True, how='left')
ct['antes_de_la_norma'] = (ct.fecha < ct.fecha_norma).astype(int)
ob = ct[ct.objeto == 'Obra'].sort_values('monto', ascending=False)
agg = ct.groupby('cui').agg(n_contratos=('proceso', 'size'), monto_contratos=('monto', 'sum'), primer_contrato=('fecha', 'min'), ultimo_contrato=('fecha', 'max'),
                            contratos_previos=('antes_de_la_norma', 'sum')).reset_index()
agg = agg.merge(ob.groupby('cui').contratista.agg(lambda x: ' / '.join(dict.fromkeys(x))).rename('contratistas_obra').reset_index(), on='cui', how='left')
otros = ct.groupby('cui').contratista.agg(lambda x: ' / '.join(dict.fromkeys(x))).rename('todos_contratistas').reset_index()
agg = agg.merge(otros, on='cui', how='left')
for c in ['primer_contrato', 'ultimo_contrato']: agg[c] = agg[c].dt.strftime('%Y-%m-%d')
out = out.merge(agg, on='cui', how='left')
ic = pd.read_csv(PRO/'informes_control.csv', dtype={'cui': str})
out = out.merge(ic, on='cui', how='left')
out['n_contratos'] = out.n_contratos.fillna(0).astype(int); out['n_informes'] = out.n_informes.fillna(0).astype(int)
out['ficha_mef'] = 'https://ofi5.mef.gob.pe/ssi/Ssi/Index?codigo=' + out.cui + '&tipo=2'
out.sort_values('marco_fen', ascending=False).to_csv(WEB/'proyectos.csv', index=False)
ctrl = pd.read_csv(PRO/'informes_control_detalle.csv', dtype={'cui': str})
ctrl = ctrl.merge(p[['cui', 'nombre', 'ejecutora', 'departamento']], on='cui', how='left')
ctrl.to_csv(WEB/'control.csv', index=False)
agc = ctrl[ctrl.n_situaciones > 0].groupby('cui').agg(informes_con_alertas=('codigo', 'nunique'), situaciones_adversas=('n_situaciones', 'sum'),
      categorias_alerta=('categorias', lambda x: ','.join(sorted(set(','.join(x).split(',')) - {''}))))
out = out.merge(agc, on='cui', how='left'); out[['informes_con_alertas', 'situaciones_adversas']] = out[['informes_con_alertas', 'situaciones_adversas']].fillna(0).astype(int)
out.sort_values('marco_fen', ascending=False).to_csv(WEB/'proyectos.csv', index=False)
q = pd.read_csv(PRO/'quebradas_cgr.csv'); q.to_csv(WEB/'quebradas_cgr.csv', index=False)
cw = ct.merge(p[['cui', 'nombre', 'ejecutora', 'departamento']], on='cui', how='left')
cw['fecha'] = cw.fecha.dt.strftime('%Y-%m-%d'); cw['fecha_norma'] = cw.fecha_norma.dt.strftime('%Y-%m-%d')
cw.to_csv(WEB/'contratos.csv', index=False)

# ---------- 3. Intervenciones de los anexos (puntos criticos) ----------
dist = json.load(open(ORI/'peru_distrital_simple.geojson'))
def centroid(geom):
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    pts = [pt for poly in polys for pt in poly[0]]
    return sum(x for x, _ in pts)/len(pts), sum(y for _, y in pts)/len(pts)
cd, cp = {}, {}
for f in [f for f in dist['features'] if f.get('geometry')]:
    pr = f['properties']; x, y = centroid(f['geometry']); d = norm(pr['NOMBDEP'])
    cd[(d, norm(pr['NOMBPROV']), norm(pr['NOMBDIST']))] = (y, x); cd.setdefault((d, '', norm(pr['NOMBDIST'])), (y, x))
    cp.setdefault((d, norm(pr['NOMBPROV'])), []).append((y, x))
cp = {k: (sum(a for a, _ in v)/len(v), sum(b for _, b in v)/len(v)) for k, v in cp.items()}
tr = {z: Transformer.from_crs(f'EPSG:327{z}', 'EPSG:4326', always_xy=True) for z in (17, 18, 19)}

def ubicar(r, este, norte):
    try:
        z = int(re.search(r'1[789]', str(r.get('Zona UTM (inferida)', ''))).group())
        e, n = float(r[este]), float(r[norte])
        if 100000 < e < 900000 and 8000000 < n < 10000000:
            lon, lat = tr[z].transform(e, n); return lat, lon, 'Coordenada del anexo'
    except Exception: pass
    d, pv = norm(r['Departamento']), norm(r['Provincia'])
    for di in re.split(r'[,/;]| Y ', str(r['Distrito']).upper()):
        for k in [(d, pv, norm(di)), (d, '', norm(di))]:
            if k in cd: return *cd[k], 'Centroide del distrito'
    if (d, pv) in cp: return *cp[(d, pv)], 'Centroide de la provincia'
    return None, None, 'Sin ubicar'

rows = []
for anio, x, este, norte in [(2023, 'DU_Fenomeno_El_Nino_2023.xlsx', 'Este (inicio)', 'Norte (inicio)'), (2026, 'DU_Fenomeno_El_Nino_2026.xlsx', 'Este', 'Norte')]:
    it = pd.read_excel(ORI/x, 'Intervenciones').dropna(subset=['Decreto'])
    for _, r in it.iterrows():
        lat, lon, prec = ubicar(r, este, norte)
        rows.append({'anio': anio, 'decreto': r['Decreto'], 'anexo': r['Anexo'], 'n_anexo': r['N.º en anexo'], 'ejecutora': r['Entidad ejecutora'],
                     'tipo': r['Tipo de intervención'], 'cuenca': r['Cuenca'], 'rio': r['Río / quebrada'], 'departamento': norm(r['Departamento']),
                     'provincia': r['Provincia'], 'distrito': r['Distrito'], 'sector': r['Sector'],
                     'presupuesto': r.get('Presupuesto referencial (S/)'), 'lat': lat, 'lon': lon, 'precision': prec})
inter = pd.DataFrame(rows); inter['repetido'] = ''
rep = pd.read_excel(ORI/'DU_Fenomeno_El_Nino_2026.xlsx', 'Repeticiones 2023-2026').dropna(subset=['Tipo'])
def marca(anio, fuente, n):
    return (inter.anio == anio) & (inter.n_anexo == n) & ((inter.decreto + ' ' + inter.anexo) == fuente.strip())
for _, r in rep.iterrows():
    inter.loc[marca(2023, str(r['Fuente 2023']), r['N.º 2023']) | marca(2026, str(r['Fuente 2026']), r['N.º 2026']), 'repetido'] = r['Coincidencia']
for c in ['lat', 'lon']: inter[c] = pd.to_numeric(inter[c]).round(5)
inter.to_csv(WEB/'intervenciones.csv', index=False)
rep.to_csv(PRO/'repeticiones_2023_2026.csv', index=False)

# ---------- 4. Departamentos (geometria simplificada) ----------
dep = json.load(open(ORI/'peru_departamental.geojson'))
def rnd(c): return [rnd(x) for x in c] if isinstance(c[0], list) else [round(c[0], 3), round(c[1], 3)]
for f in dep['features']:
    f['properties'] = {'departamento': norm(f['properties']['NOMBDEP'])}; f['geometry']['coordinates'] = rnd(f['geometry']['coordinates'])
json.dump(dep, open(WEB/'departamentos.geojson', 'w'))

# ---------- Resumen de control ----------
print(f'Duplicados eliminados: {dup}')
print(f'Gasto: {len(gasto)} filas | marco S/ {gasto.marco.sum()/1e6:,.1f} M | devengado S/ {gasto.devengado.sum()/1e6:,.1f} M')
print(f'Normas: {len(normas)} | Proyectos: {len(out)} | en Banco de Inversiones: {out.estado_bi.notna().sum()} | con avance: {out.avance.notna().sum()}')
print(out.estado_obra.value_counts().to_string())
print(f'Intervenciones: {len(inter)}'); print(inter.precision.value_counts().to_string()); print(inter.repetido.value_counts().to_string())
