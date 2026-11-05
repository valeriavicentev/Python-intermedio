/*
 * Consulta las fichas del Sistema de Seguimiento de Inversiones (SSI) del MEF para los CUI
 * financiados con normas FEN y devuelve los contratos del SEACE e informes de control (CGR).
 *
 * Uso: abrir https://ofi5.mef.gob.pe/ssi/Ssi/Index?codigo=2446345&tipo=2 en el navegador,
 * pegar este script en la consola (F12) y ejecutar. Copiar los resultados a
 * datos/procesados/_contratos_grupos.txt e informes_control.csv.
 * Los servicios usados son los mismos que llama la propia ficha pública del MEF.
 */
const CUIS = '2475661 2446345 2524692 2425378 2501225 2609032 2608506 2609387 2608354 2608356 2608664 2608504 2436581 2608666 2608648 2608659 2427315 2608657 2468097 2608661 2608668 2436571 2441623 2234253 2608881 2607776 2608491 2608499 2608665 2436582 2609384 2436583 2609388 2436577 2440674 2443288 2608654 2441771 2436570 2441637 2443285 2443286 2441619 2441764 2441767 2441750'.split(' ');
const post = (u, d) => fetch(u, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest'}, body: new URLSearchParams(d)}).then(r => r.json()).catch(() => []);
const fecha = s => { const m = /\d+/.exec(s || ''); return m ? new Date(+m[0]).toISOString().slice(0, 10) : ''; };
(async () => {
  const contratos = [], informes = [];
  for (const cui of CUIS) {
    const s = await post('/invierteWS/Ssi/traeContratoSeaceDWH', {id: cui, codsnip: '0', vers: 'v2'});
    (Array.isArray(s) ? s : []).forEach(x => contratos.push([cui, x.OBJETO_CONTRATAC, x.NOM_CONTRATISTA, x.FEC_SUSCRIPCION, x.MTO_ITEM, x.NOMENCLATURA].join('|')));
    const k = await post('/ssi/Ssi/traeInfControlDWH', {id: cui});
    (Array.isArray(k) ? k : []).forEach(x => informes.push([cui, x.NUMERO_INFORME, x.TIPO_INFORME, fecha(x.FECHA_EMISION)].join('|')));
  }
  console.log('CONTRATOS\n' + [...new Set(contratos)].join('\n'));
  console.log('INFORMES\n' + informes.join('\n'));
})();

/*
 * Otras consultas usadas (mismo método, en la consola del navegador):
 * 1. Estado oficial por CUI (ficha SSI):  POST /invierteWS/Ssi/traeDetInvSSI  {id: CUI, tipo: '2'}
 *    -> ESTADO, CIERRE_REGISTRADO, AVAN_FISICO, DEV_ACUMULADO, COSTO_ACTUALIZADO, FEC_FIN_EJ  => datos/procesados/estado_ssi.csv
 * 2. Obras Infobras vinculadas al CUI:     GET  /ssi/Ssi/verInfObras2/CUI  -> NOBR_ID de cada obra
 *    Último avance de cada obra (en https://infobras.contraloria.gob.pe):
 *                                          POST /InfobrasWeb/Obra/Avance/ObraUAvanceMovil/NOBR_ID
 *    -> RealFis, ProgramaDofis, HayParal, FechaParal, ComentarioFis     => datos/procesados/infobras_avance.csv
 * 3. Fichas resumen de control (https://apps8.contraloria.gob.pe/SPIC/srvDownload/ViewPDF?CRES_CODIGO=...&TIPOARCHIVO=RE),
 *    leídas con pdf.js; se extrajo la sección "Situaciones adversas" y se clasificó por tipo con expresiones regulares
 *    => datos/procesados/informes_control_detalle.csv. Los informes completos (TIPOARCHIVO=ADJUNTO) de las quebradas
 *    identifican al ejecutor y las cartas fianza  => datos/procesados/quebradas_cgr.csv
 * Nota: el avance que devuelve verInfObras2 (obj_SNO_AVANCE) es igual para todas las obras, por eso no se usa.
 */
/*
 * 4. Sanciones y penalidades (en https://apps.osce.gob.pe/perfilprov-ui/):
 *    GET https://eap.oece.gob.pe/ficha-proveedor-cns/1.0/ficha/RUC/resumen  -> antecedentes.sanciones, penalidades,
 *        inhsJudicial, inhsAdministrativa, medidasCautelares             => datos/procesados/sanciones_tce.csv, penalidades_oece.csv
 *    Para obtener el RUC de los contratistas de la ficha SSI se usó
 *    GET https://eap.oece.gob.pe/perfilprov-bus/1.0/tarjetas?searchText=NOMBRE  (coincidencia exacta del nombre).
 */
