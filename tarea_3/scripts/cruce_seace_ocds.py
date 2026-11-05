"""Cruza el gasto FEN (MEF) con los contratos del SEACE publicados por el OECE en formato OCDS.

Entrada: datos/originales/ocds/peru_oece_bulk_2023.csv.tar.gz y ..._2026.csv.tar.gz
         (https://data.open-contracting.org/en/publication/135, descargados el 4/11/2026)
Regla:   para las ejecutoras que concentran el gasto FEN se toman los contratos firmados desde la
         publicación de la primera norma FEN de ese año hasta el 31/12, y se clasifican:
           - "Cita FEN, la norma o peligro inminente": el texto del proceso menciona El Niño, el DU o el peligro inminente.
           - "Tema de emergencia o prevención": el texto describe descolmatación, defensas ribereñas, quebradas, etc.
         Los demás contratos de la entidad en ese periodo no se atribuyen al FEN.
Salida:  datos/procesados/seace_fen.csv y web/data/seace_fen.csv
"""
import tarfile, os
from pathlib import Path
BASE = str(Path(__file__).resolve().parents[1])
OCDS = os.path.expanduser('~/ocds')
import pandas as pd, re, unicodedata
def norm(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().upper()
    return re.sub(r'\s+',' ',re.sub(r'[^A-Z0-9 ]',' ',s)).strip()
MAP={ # ejecutora MEF -> comprador OCDS
'MODERNIZACION DE LA GESTION DE LOS RECURSOS HIDRICOS':'PROYECTO DE MODERNIZACION DE LA GESTION DE LOS RECURSOS HIDRICOS',
'EJERCITO PERUANO':'EJERCITO PERUANO','FUERZA AEREA DEL PERU':'FUERZA AEREA DEL PERU','MARINA DE GUERRA DEL PERU':'MARINA DE GUERRA DEL PERU',
'PROGRAMA DE DESARROLLO PRODUCTIVO AGRARIO RURAL - AGRORURAL':'PROGRAMA DE DESARROLLO PRODUCTIVO AGRARIO RURAL AGRO RURAL',
'M.E.-PROGRAMA NACIONAL DE INFRAESTRUCTURA  EDUCATIVA':'PROGRAMA NACIONAL DE INFRAESTRUCTURA EDUCATIVA UE 108 PRONIED',
'AUTORIDAD NACIONAL DE INFRAESTRUCTURA - ANIN':'AUTORIDAD NACIONAL DE INFRAESTRUCTURA',
'PROGRAMA SUBSECTORIAL DE IRRIGACION - PSI':'PROGRAMA SUBSECTORIAL DE IRRIGACIONES PSI',
'MTC- PRO VIAS NACIONAL':'MTC PROYECTO ESPECIAL DE INFRAESTRUCTURA DE TRANSPORTE NACIONAL PROVIAS NACIONAL',
'AUTORIDAD NACIONAL DE AGUA - SEDE CENTRAL':'AUTORIDAD NACIONAL DEL AGUA',
'AUTORIDAD PARA LA RECONSTRUCCION CON CAMBIOS - RCC':'AUTORIDAD PARA LA RECONSTRUCCION CON CAMBIOS',
'MINISTERIO DE VIVIENDA, CONSTRUCCION Y SANEAMIENTO- ADM. GEN':'MINISTERIO DE VIVIENDA CONSTRUCCION Y SANEAMIENTO ADMINISTRACION GENERAL',
'PROGRAMA NACIONAL DE SANEAMIENTO URBANO':'PROGRAMA NACIONAL DE SANEAMIENTO URBANO','PROGRAMA NACIONAL DE SANEAMIENTO RURAL':'PROGRAMA NACIONAL DE SANEAMIENTO RURAL',
'MUNICIPALIDAD PROVINCIAL DE PIURA':'MUNICIPALIDAD PROVINCIAL DE PIURA',
'REGION LIMA - AGRICULTURA LIMA PROVINCIAS':'GOBIERNO REGIONAL DE LIMA DIRECCION REGIONAL DE AGRICULTURA DE LIMA PROVINCIAS',
'REGION PIURA - PROYECTO ESP. CHIRA PIURA':'GOBIERNO REGIONAL DE PIURA PROYECTO ESPECIAL CHIRA PIURA',
'MINISTERIO DE LA PRODUCCION':'MINISTERIO DE LA PRODUCCION','MINISTERIO DE TRANSPORTES Y COMUNICACIONES-ADMINISTRACION GENERAL':'MINISTERIO DE TRANSPORTES Y COMUNICACIONES',
'MINAG - JEQUETEPEQUE- ZAÑA':'MINAG PROYECTO ESPECIAL JEQUETEPEQUE ZANA','REGION TUMBES-SEDE CENTRAL':'GOBIERNO REGIONAL DE TUMBES SEDE CENTRAL',
}
FUERTE=re.compile(r'\bFEN\b|FENOMENO (DE )?EL NINO|FENOMENO DEL NINO|\bEL NINO\b|NINO COSTERO|DECRETO DE URGENCIA|\bD ?U\b ?N? ?0?(09|15|16|19|25|28|30|31|35|36|37) 2023|\bD ?U\b ?N? ?0?(08|10|13) 2026|PELIGRO INMINENTE|31912')
TEMA=re.compile(r'DESCOLMAT|LIMPIEZA DE (CAUCE|RIO|QUEBRADA|DREN|CANAL)|QUEBRADA|DEFENSA(S)? RIBEREN|BARRERA(S)? DINAMIC|PUNTOS? CRITICO|ESTADO DE EMERGENCIA|SITUACION DE EMERGENCIA|LLUVIAS|INUNDACION|HUAICO|ENROCADO|ALQUILER DE MAQUINARIA|MOTOBOMBA|MODULOS? DE VIVIENDA|CARPAS|KIT')
g=pd.read_csv(BASE+'/web/data/gasto.csv',parse_dates=['fecha'])
ini=g[g.marco>0].groupby(['ejecutora','anio']).agg(desde=('fecha','min'),marco=('marco','sum'),dev=('devengado','sum')).reset_index()
if not os.path.exists(OCDS+'/todos.pkl'):
    os.makedirs(OCDS, exist_ok=True); out=[]
    for y in ['2023', '2026']:
        with tarfile.open(f'{BASE}/datos/originales/ocds/peru_oece_bulk_{y}.csv.tar.gz') as t:
            for n in ['main', 'contracts', 'awards_suppliers']: t.extract(f'{y}/{n}.csv', OCDS)
        m=pd.read_csv(f'{OCDS}/{y}/main.csv',dtype=str,usecols=['ocid','buyer_name','tender_title','tender_description','tender_procurementMethodDetails','tender_mainProcurementCategory'])
        c=pd.read_csv(f'{OCDS}/{y}/contracts.csv',dtype=str,usecols=['id','title','dateSigned','description','awardID','value_amount','value_currency','main_ocid'])
        su=pd.read_csv(f'{OCDS}/{y}/awards_suppliers.csv',dtype=str,usecols=['id','name','main_ocid','awards_id']).rename(columns={'id':'ruc','name':'proveedor'})
        out.append(c.merge(m.drop_duplicates('ocid'),left_on='main_ocid',right_on='ocid',how='left').merge(su.drop_duplicates(['awards_id','main_ocid']),left_on=['awardID','main_ocid'],right_on=['awards_id','main_ocid'],how='left'))
    d=pd.concat(out).drop_duplicates('id'); d['fecha']=pd.to_datetime(d.dateSigned.str[:10],errors='coerce'); d['monto']=pd.to_numeric(d.value_amount,errors='coerce')
    d.to_pickle(OCDS+'/todos.pkl')
d=pd.read_pickle(OCDS+'/todos.pkl'); d['bn']=d.buyer_name.map(norm)
d['texto']=(d.tender_title.fillna('')+' '+d.tender_description.fillna('')+' '+d.description.fillna('')+' '+d.title.fillna('')).map(norm)
rows=[]
for _,r in ini.iterrows():
    b=MAP.get(r.ejecutora.strip())
    if not b: continue
    hasta=pd.Timestamp(f'{r.anio}-12-31')
    x=d[(d.bn==b)&(d.fecha>=r.desde)&(d.fecha<=hasta)].copy()
    x['nivel_vinculo']=x.texto.map(lambda t:'Cita FEN, la norma o peligro inminente' if FUERTE.search(t) else ('Tema de emergencia o prevención' if TEMA.search(t) else None))
    x=x[x.nivel_vinculo.notna()]
    x['ejecutora_mef']=r.ejecutora.strip(); x['anio_fen']=r.anio; x['desde_norma']=r.desde.date()
    rows.append(x)
o=pd.concat(rows)
o['proceso']=o.tender_procurementMethodDetails
o=o[['anio_fen','ejecutora_mef','buyer_name','fecha','proveedor','ruc','monto','value_currency','proceso','tender_mainProcurementCategory','nivel_vinculo','tender_title','tender_description','title']]
o['ruc']=o.ruc.str.replace('PE-RUC-','',regex=False)
o['tender_description']=o.tender_description.str.slice(0,220)
print(len(o)); print(o.groupby(['anio_fen','nivel_vinculo']).agg(n=('monto','size'),m=('monto','sum')))
print(o.groupby('proceso').monto.agg(['size','sum']).sort_values('sum',ascending=False).head(8))
o=o.sort_values('monto',ascending=False); o.to_csv(BASE+'/datos/procesados/seace_fen.csv',index=False)
w=o[['anio_fen','ejecutora_mef','fecha','proveedor','ruc','monto','proceso','nivel_vinculo','tender_description']].copy()
w['fecha']=pd.to_datetime(w.fecha).dt.strftime('%Y-%m-%d'); w['tender_description']=w.tender_description.fillna('').str.slice(0,160)
w.to_csv(BASE+'/web/data/seace_fen.csv',index=False)
s=o[o.nivel_vinculo.str.startswith('Cita')]
print(s.groupby('proveedor').agg(n=('monto','size'),m=('monto','sum'),ej=('ejecutora_mef','first')).sort_values('m',ascending=False).head(15).to_string())
