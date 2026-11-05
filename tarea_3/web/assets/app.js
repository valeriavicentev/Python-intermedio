/* Dashboard: El dinero de El Niño (2023-2026). Datos en ./data, generados por scripts/procesar_datos.py */
const $ = s => document.querySelector(s);
const tip = $('#tip');
const nf1 = new Intl.NumberFormat('es-PE', {maximumFractionDigits: 1, minimumFractionDigits: 1});
const nf0 = new Intl.NumberFormat('es-PE', {maximumFractionDigits: 0});
const M = v => 'S/ ' + (Math.abs(v) >= 1e9 ? nf0.format(v / 1e6) : nf1.format(v / 1e6)) + ' M';
const P = v => isFinite(v) ? nf1.format(v) + '%' : '—';
const title = s => (s || '').toLowerCase().replace(/(^|[\s(/-])([a-záéíóúñü])/g, (m, a, b) => a + b.toUpperCase())
  .replace(/(?!^)\b(De|Del|La|Las|Los|Y|En|El|Para|Por|A|Con)\b/g, w => w.toLowerCase()).replace(/\b(Ana|Anin|Psi|Mtc|Fap|Indeci|Arcc|Pronied|Cui|Ii|Iii)\b/gi, w => w.toUpperCase());
const sum = (a, k) => d3.sum(a, d => d[k]);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function showTip(ev, html) { tip.innerHTML = html; tip.style.opacity = 1; moveTip(ev); }
function moveTip(ev) {
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
  if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
const hideTip = () => tip.style.opacity = 0;

const ESTADO_COLOR = {
  'En ejecución': 'var(--dev)', 'En ejecución, plazo vencido': 'var(--warn)', 'Paralizada': 'var(--p-plum)', 'Cerrado sin culminar': 'var(--crit)',
  'Culminada, sin cierre': 'var(--good)', 'Sin avance registrado': 'var(--neutral)', 'Código genérico (no es obra)': '#b8b0a4'
};
const SIN_AVANCE = ['Cerrado sin culminar', 'Paralizada', 'Sin avance registrado'];
const CAT = {EXP: 'Expediente técnico deficiente', CONTRATO: 'Contrato inexistente, resuelto o nulo', GARANTIA: 'Garantías y pólizas', DOC: 'Documentación inexacta o personal no habilitado',
  CALIDAD: 'Calidad de la obra', PAGO: 'Pagos, valorizaciones y penalidades', PLAZO: 'Retrasos y paralizaciones', SEGURIDAD: 'Seguridad en obra',
  TRANSP: 'Registro y transparencia (SEACE, Infobras)', SUBCON: 'Subcontratación no autorizada', PERSONAL: 'Personal o equipo mínimo ausente', PREDIOS: 'Liberación de predios'};
const F = {anio: '', nivel: '', dep: '', norma: ''};
let D = {};

Promise.all([
  d3.csv('data/gasto.csv', d3.autoType), d3.csv('data/normas.csv', d3.autoType), d3.csv('data/proyectos.csv', d => { const r = {...d}; return {...d3.autoType(d), cui: r.cui, fin_ejecucion: r.fin_ejecucion, inicio_ejecucion: r.inicio_ejecucion, ultima_act_seguimiento: r.ultima_act_seguimiento, primer_contrato: r.primer_contrato, ultimo_contrato: r.ultimo_contrato, ultimo_informe: r.ultimo_informe}; }),
  d3.csv('data/contratos.csv', d => { const r = {...d}; return {...d3.autoType(d), cui: r.cui, fecha: r.fecha, fecha_norma: r.fecha_norma}; }), d3.csv('data/intervenciones.csv', d3.autoType), d3.json('data/departamentos.geojson'), d3.csv('data/seace_fen.csv', d => { const r = {...d}; return {...d3.autoType(d), ruc: r.ruc, fecha: r.fecha}; }),
  d3.csv('data/control.csv', d => { const r = {...d}; return {...d3.autoType(d), cui: r.cui, fecha: r.fecha, categorias: r.categorias || ''}; }), d3.json('data/casos.json'), d3.csv('data/quebradas_cgr.csv', d3.autoType),
  d3.csv('data/sanciones.csv', d => { const r = {...d}; return {...d3.autoType(d), ruc: r.ruc, inicio: r.inicio, fin: r.fin, fecha_contratos: r.fecha_contratos}; }), d3.csv('data/penalidades.csv', d => { const r = {...d}; return {...d3.autoType(d), ruc: r.ruc, fecha: r.fecha}; })
]).then(([gasto, normas, proyectos, contratos, inter, geo, seace, control, casos, qcgr, sanciones, penalidades]) => {
  D = {gasto, normas, proyectos, contratos, inter, geo, seace, control, casos, qcgr, sanciones, penalidades};
  proyectos.forEach(p => { p.anio = String(p.anio); });
  fillSelect('#f-nivel', [...new Set(gasto.map(d => d.nivel))].sort());
  fillSelect('#f-dep', [...new Set(gasto.map(d => d.departamento))].sort(), title);
  fillSelect('#f-norma', [...new Set(gasto.map(d => d.tipo_norma))].sort());
  fillSelect('#t-estado', Object.keys(ESTADO_COLOR).filter(e => proyectos.some(p => p.estado_obra === e)));
  [['#f-anio', 'anio'], ['#f-nivel', 'nivel'], ['#f-dep', 'dep'], ['#f-norma', 'norma']].forEach(([s, k]) =>
    $(s).addEventListener('change', e => { F[k] = e.target.value; render(); }));
  $('#f-reset').addEventListener('click', () => { Object.keys(F).forEach(k => F[k] = ''); document.querySelectorAll('#filters select').forEach(s => s.value = ''); render(); });
  ['#t-q', '#t-estado'].forEach(s => $(s).addEventListener('input', renderTable));
  ['#s-q', '#s-v'].forEach(s => $(s).addEventListener('input', renderSeaceTable));
  ['#m-coro', '#m-lima', '#m-int', '#m-proy'].forEach(s => $(s).addEventListener('change', renderMap));
  document.querySelectorAll('#t-proy th').forEach(th => th.addEventListener('click', () => { sortKey = th.dataset.k; sortDir = sortKey === lastKey ? -sortDir : -1; lastKey = sortKey; renderTable(); }));
  ['#al-cat', '#al-q'].forEach(s => $(s).addEventListener('input', renderAlertTable));
  initMap(); renderStatic(); renderAlertas(); render();
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 150); });
}).catch(err => { document.querySelector('main').insertAdjacentHTML('afterbegin', `<div class="empty">No se pudieron cargar los datos (${err}).</div>`); });

function fillSelect(sel, vals, fmt = v => v) { const s = $(sel); vals.forEach(v => s.insertAdjacentHTML('beforeend', `<option value="${v}">${fmt(v)}</option>`)); }
const gFil = () => D.gasto.filter(d => (!F.anio || d.anio == F.anio) && (!F.nivel || d.nivel === F.nivel) && (!F.dep || d.departamento === F.dep) && (!F.norma || d.tipo_norma === F.norma));
const pFil = () => D.proyectos.filter(p => (!F.anio || p.anio.includes(F.anio)) && (!F.nivel || p.nivel === F.nivel) && (!F.dep || p.departamento === F.dep));

function render() {
  const g = gFil();
  const act = Object.entries(F).filter(([, v]) => v).map(([k, v]) => ({anio: 'Año ', nivel: '', dep: '', norma: ''}[k] + (k === 'dep' ? title(v) : v)));
  $('#filter-note').textContent = act.length ? `Filtros activos: ${act.join(' · ')}. Afectan los indicadores, gráficos, mapa y tabla.` : 'Los filtros afectan los indicadores, los gráficos, el mapa y la tabla de proyectos.';
  renderKPIs(g); renderTimeline(g); renderAnios(g); renderMap(); renderDep(g); renderEjec(g); renderSeace(); renderContratos(); renderEstado(); renderAvance(); renderTable();
}

function renderKPIs(g) {
  const m = sum(g, 'marco'), d = sum(g, 'devengado');
  $('#k-marco').textContent = M(m); $('#k-marco-sub').textContent = `${new Set(g.map(x => x.norma)).size} normas · ${new Set(g.map(x => x.sec_ejec)).size} unidades ejecutoras`;
  $('#k-dev').textContent = M(d); $('#k-dev-sub').textContent = `${P(100 * d / m)} de lo autorizado`;
  $('#k-saldo').textContent = M(m - d); $('#k-saldo-sub').textContent = 'Autorizado que no llegó a devengarse';
  const e = d3.rollups(g, v => sum(v, 'marco'), x => x.ejecutora).sort((a, b) => b[1] - a[1])[0];
  $('#k-ejec').textContent = e ? title(e[0]) : '—'; $('#k-ejec-sub').textContent = e ? `${M(e[1])} autorizados (${P(100 * e[1] / m)} del total)` : '';
  const p = pFil().filter(x => x.estado_obra !== 'Código genérico (no es obra)'), s = p.filter(x => SIN_AVANCE.includes(x.estado_obra));
  $('#k-obras').textContent = `${s.length} de ${p.length}`; $('#k-obras-sub').textContent = `${p.filter(x => x.estado_obra === 'Cerrado sin culminar').length} cerradas sin culminar y ${p.filter(x => x.estado_obra === 'Paralizada').length} paralizadas · ${M(sum(s, 'marco_fen'))} FEN`;
}

/* ---- Cronología: una barra por norma, agrupadas por año ---- */
function renderTimeline(g) {
  const el = $('#c-timeline'); el.innerHTML = '';
  const rows = d3.rollups(g, v => ({marco: sum(v, 'marco'), dev: sum(v, 'devengado'), fecha: v[0].fecha, anio: v[0].anio, n: new Set(v.map(x => x.sec_ejec)).size}), d => d.norma)
    .map(([norma, o]) => ({norma, ...o})).filter(d => Math.abs(d.marco) > 0 || d.dev > 0).sort((a, b) => d3.ascending(a.fecha, b.fecha) || d3.descending(a.marco, b.marco));
  if (!rows.length) { el.innerHTML = '<div class="empty">Sin normas para esta selección.</div>'; return; }
  const W = el.clientWidth, H = 300, mg = {t: 26, r: 8, b: 30, l: 52};
  const years = [...new Set(rows.map(d => d.anio))];
  const x = d3.scaleBand().domain(rows.map(d => d.norma)).range([mg.l, W - mg.r]).paddingInner(0.18);
  const y = d3.scaleLinear().domain([Math.min(0, d3.min(rows, d => d.marco)), d3.max(rows, d => Math.max(d.marco, d.dev))]).nice().range([H - mg.b, mg.t]);
  const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('width', '100%');
  svg.append('g').attr('class', 'grid').attr('transform', `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(W - mg.l - mg.r)).tickFormat('')).call(s => s.select('.domain').remove());
  svg.append('g').attr('class', 'axis').attr('transform', `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(v => nf0.format(v / 1e6))).call(s => s.select('.domain').remove());
  svg.append('text').attr('x', mg.l - 44).attr('y', 12).attr('fill', 'var(--ink-3)').attr('font-size', 11).text('S/ millones');
  years.forEach(yr => {
    const r = rows.filter(d => d.anio === yr), x0 = x(r[0].norma), x1 = x(r[r.length - 1].norma) + x.bandwidth();
    svg.append('line').attr('x1', x0).attr('x2', x1).attr('y1', H - mg.b + 8).attr('y2', H - mg.b + 8).attr('stroke', 'var(--ink-3)');
    svg.append('text').attr('x', (x0 + x1) / 2).attr('y', H - 6).attr('text-anchor', 'middle').attr('font-size', 12).attr('font-weight', 600).attr('fill', 'var(--ink-2)').text(yr);
  });
  const bw = x.bandwidth(), r = Math.min(4, bw / 2);
  const bar = svg.append('g').selectAll('g').data(rows).join('g');
  bar.append('rect').attr('x', d => x(d.norma)).attr('width', bw).attr('y', d => y(Math.max(0, d.marco))).attr('height', d => Math.abs(y(d.marco) - y(0))).attr('rx', r).attr('fill', 'var(--auth)');
  bar.append('rect').attr('x', d => x(d.norma) + bw * 0.2).attr('width', bw * 0.6).attr('y', d => y(Math.max(0, d.dev))).attr('height', d => Math.abs(y(d.dev) - y(0))).attr('rx', Math.min(3, bw * 0.3)).attr('fill', 'var(--dev)');
  svg.append('line').attr('x1', mg.l).attr('x2', W - mg.r).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', 'var(--ink-3)');
  rows.slice().sort((a, b) => b.marco - a.marco).slice(0, W < 640 ? 1 : 3).forEach(d => svg.append('text').attr('x', x(d.norma) + bw / 2).attr('y', y(d.marco) - 6).attr('text-anchor', 'middle').attr('font-size', 11).attr('fill', 'var(--ink-2)').text(d.norma.replace(/^(D\.U\.|D\.S\.|LEY) N° /, m => m.startsWith('LEY') ? 'Ley ' : m.slice(0, 4) + ' ')));
  bar.append('rect').attr('x', d => x(d.norma) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', mg.t).attr('height', H - mg.t - mg.b).attr('fill', 'transparent')
    .on('mouseenter mousemove', (ev, d) => showTip(ev, `<b>${d.norma}</b><br>Publicada: ${d.fecha ? d3.timeFormat('%d/%m/%Y')(d.fecha) : '—'}<br>Autorizado: ${M(d.marco)}<br>Devengado: ${M(d.dev)} (${P(100 * d.dev / d.marco)})<br>${d.n} unidades ejecutoras`)).on('mouseleave', hideTip);
}

/* ---- Barras horizontales de autorizado vs devengado (reutilizable) ---- */
function hbars(el, rows, {label = d => d.k, onClick, extra = d => P(100 * d.dev / d.marco) + ' gastado', lw = 220, tipf, solid} = {}) {
  el.innerHTML = '';
  if (!rows.length) { el.innerHTML = '<div class="empty">Sin datos para esta selección.</div>'; return; }
  const W = el.clientWidth, narrow = W < 560, row = narrow ? 46 : 28, H = rows.length * row + 24;
  const L = narrow ? 0 : Math.min(lw, W * 0.35), R = solid ? 150 : 96, top = narrow ? 16 : 0;
  const x = d3.scaleLinear().domain([0, d3.max(rows, d => Math.max(d.marco, d.dev))]).nice().range([L, W - R]);
  const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('width', '100%');
  const g = svg.selectAll('g').data(rows).join('g').attr('transform', (d, i) => `translate(0,${i * row + 4})`).style('cursor', onClick ? 'pointer' : 'default');
  g.append('text').attr('x', narrow ? 0 : L - 8).attr('y', narrow ? 10 : 15).attr('text-anchor', narrow ? 'start' : 'end').attr('font-size', 12).attr('fill', 'var(--ink-2)')
    .text(d => { const t = label(d); const max = narrow ? Math.floor(W / 6.8) : Math.floor(L / 6.4); return t.length > max ? t.slice(0, max - 1) + '…' : t; });
  g.append('rect').attr('x', L).attr('y', top + 4).attr('height', 16).attr('rx', 4).attr('width', d => Math.max(0, x(Math.max(0, d.marco)) - L)).attr('fill', d => solid ? (typeof solid === 'function' ? solid(d) : solid) : 'var(--auth)');
  g.append('rect').attr('x', L).attr('y', top + 8).attr('height', 8).attr('rx', 3).attr('width', d => Math.max(0, x(Math.max(0, d.dev)) - L)).attr('fill', 'var(--dev)');
  g.append('text').attr('x', d => x(Math.max(0, d.marco, d.dev)) + 6).attr('y', top + 16).attr('font-size', 11).attr('fill', 'var(--ink-2)').text(d => M(d.marco));
  g.append('rect').attr('x', 0).attr('y', 0).attr('width', W).attr('height', row).attr('fill', 'transparent')
    .on('mouseenter mousemove', (ev, d) => showTip(ev, tipf ? tipf(d) : `<b>${label(d)}</b><br>Autorizado: ${M(d.marco)}<br>Devengado: ${M(d.dev)}<br>${extra(d)}`)).on('mouseleave', hideTip)
    .on('click', (ev, d) => onClick && onClick(d));
}

function renderAnios(g) {
  const rows = d3.rollups(g, v => ({marco: sum(v, 'marco'), dev: sum(v, 'devengado')}), d => d.anio).map(([k, o]) => ({k: String(k), ...o})).sort((a, b) => d3.ascending(a.k, b.k));
  hbars($('#c-anios'), rows, {lw: 60});
}

/* ---- Mapa ---- */
let map, lyrCoro, lyrInt, lyrProy, lyrLegend;
const SEQ = ['#e7e3fc', '#c3b9f6', '#9483ef', '#5f45e7', '#3415E0', '#2F1F3E'];
function initMap() {
  map = L.map('map', {scrollWheelZoom: false, zoomSnap: 0.25}); map.fitBounds([[-18.4, -81.4], [-0.1, -68.6]]);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {attribution: '© OpenStreetMap · © CARTO', subdomains: 'abcd', maxZoom: 12}).addTo(map);
  lyrLegend = L.control({position: 'bottomleft'});
  lyrLegend.onAdd = () => L.DomUtil.create('div', 'map-legend');
  lyrLegend.addTo(map);
}
const sinSede = d => !(d.nivel === 'Gobierno Nacional' && d.departamento === 'LIMA');
function renderMap() {
  if (!map) return;
  [lyrCoro, lyrInt, lyrProy].forEach(l => l && map.removeLayer(l));
  const incl = $('#m-lima').checked, g = gFil().filter(d => incl || sinSede(d));
  const byDep = new Map(d3.rollups(g, v => ({dev: sum(v, 'devengado'), marco: sum(v, 'marco')}), d => d.departamento));
  const vals = [...byDep.values()].map(v => v.dev).filter(v => v > 0);
  const q = d3.scaleQuantile().domain(vals.length ? vals : [0, 1]).range(SEQ);
  const box = document.querySelector('.map-legend');
  if ($('#m-coro').checked) {
    lyrCoro = L.geoJSON(D.geo, {
      style: f => { const v = byDep.get(f.properties.departamento); return {fillColor: v && v.dev > 0 ? q(v.dev) : css('--line'), fillOpacity: 0.85, color: css('--surface'), weight: 1}; },
      onEachFeature: (f, l) => { const v = byDep.get(f.properties.departamento) || {dev: 0, marco: 0};
        l.bindTooltip(`<b>${title(f.properties.departamento)}</b><br>Autorizado: ${M(v.marco)}<br>Devengado: ${M(v.dev)}`, {sticky: true}); }
    }).addTo(map);
    const th = [Math.min(...vals), ...q.quantiles()];
    box.innerHTML = '<b>Devengado por región</b>' + SEQ.map((c, i) => `<div><i style="background:${c}"></i>${th[i] !== undefined && isFinite(th[i]) ? 'desde ' + M(th[i]) : ''}</div>`).join('') + '<div style="margin-top:6px"><i class="dot" style="background:' + css('--p-magenta') + '"></i>Punto repetido 2023–2026</div><div><i class="dot" style="background:' + css('--anexo') + '"></i>Intervención de anexo</div><div><i class="dot ring"></i>Proyecto con CUI (color = estado)</div>';
    box.style.display = vals.length ? '' : 'none';
  } else box.style.display = 'none';
  if ($('#m-int').checked) {
    const it = D.inter.filter(d => d.lat && (!F.anio || d.anio == F.anio) && (!F.dep || d.departamento === F.dep));
    lyrInt = L.layerGroup(it.sort((a, b) => (a.repetido ? 1 : 0) - (b.repetido ? 1 : 0)).map(d => L.circleMarker([d.lat, d.lon], {
      radius: d.repetido ? 6 : 4, weight: 1.5, color: css('--surface'), fillOpacity: 0.9, fillColor: d.repetido ? css('--p-magenta') : css('--anexo')
    }).bindTooltip(`<b>${d.rio || d.tipo}</b> · ${d.distrito || ''}<br>${d.tipo}<br>${d.decreto} ${d.anexo} · ${d.ejecutora}${d.repetido ? '<br><b>Se repite 2023–2026:</b> ' + d.repetido : ''}<br><i>Ubicación: ${d.precision.toLowerCase()}</i>`))).addTo(map);
  }
  if ($('#m-proy').checked) {
    const pr = pFil().filter(p => p.lat && p.lon);
    lyrProy = L.layerGroup(pr.map(p => L.circleMarker([p.lat, p.lon], {radius: 8, weight: 3, color: css('--ink'), fillOpacity: 0.95, fillColor: ESTADO_COLOR[p.estado_obra]?.startsWith('var') ? css(ESTADO_COLOR[p.estado_obra].slice(4, -1)) : '#999'})
      .bindTooltip(`<b>${title(p.nombre).slice(0, 110)}</b><br>CUI ${p.cui} · ${p.estado_obra}<br>FEN: ${M(p.marco_fen)} · avance ${p.avance != null ? P(p.avance) : 'sin dato'}`))).addTo(map);
  }
  const lima = gFil().filter(d => !sinSede(d));
  $('#map-note').innerHTML = `<b>${M(sum(lima, 'marco'))}</b> autorizados al Gobierno Nacional se registran con meta en Lima (sedes centrales) y no se pueden asignar a una región; ${incl ? 'están incluidos en el mapa.' : 'no se muestran. Actívalos con la casilla de arriba.'} Puntos: ${D.inter.filter(d => d.lat).length} de ${D.inter.length} intervenciones ubicadas (coordenadas del anexo o centroide del distrito).`;
}

function renderDep(g) {
  const rows = d3.rollups(g.filter(sinSede), v => ({marco: sum(v, 'marco'), dev: sum(v, 'devengado')}), d => d.departamento).map(([k, o]) => ({k, ...o}))
    .sort((a, b) => b.dev - a.dev).slice(0, 15);
  hbars($('#c-dep'), rows, {label: d => title(d.k), lw: 150, onClick: d => { F.dep = d.k; $('#f-dep').value = d.k; render(); }});
}

function renderEjec(g) {
  const rows = d3.rollups(g, v => ({marco: sum(v, 'marco'), dev: sum(v, 'devengado'), normas: d3.rollups(v, w => sum(w, 'marco'), w => w.norma)}), d => d.ejecutora)
    .map(([k, o]) => ({k, ...o})).sort((a, b) => b.marco - a.marco).slice(0, 12);
  hbars($('#c-ejec'), rows, {label: d => title(d.k), lw: 300, onClick: d => {
    $('#ejec-detail').innerHTML = `<b>${title(d.k)}</b> · ${P(100 * d.dev / d.marco)} gastado. Normas: ` + d.normas.sort((a, b) => b[1] - a[1]).map(([n, m]) => `${n} (${M(m)})`).join(' · ');
  }});
  $('#ejec-detail').textContent = '';
}

function renderContratos() {
  const ps = new Set(pFil().map(p => p.cui));
  const seen = new Set(), c = D.contratos.filter(d => ps.has(d.cui)).filter(d => { const k = d.proceso + d.contratista + d.monto; if (seen.has(k)) return false; seen.add(k); return true; });
  const rows = [[true, 'Firmados antes de la norma FEN'], [false, 'Firmados después de la norma FEN']].map(([b, k]) => {
    const v = c.filter(d => !!d.antes_de_la_norma === b); return {k, marco: sum(v, 'monto'), dev: 0, n: v.length};
  });
  hbars($('#c-contratos'), rows, {lw: 220, solid: d => d.k.includes('antes') ? 'var(--accent)' : 'var(--dev)', tipf: d => `<b>${d.k}</b><br>${d.n} contratos únicos<br>Monto contratado: ${M(d.marco)}`});
  d3.select('#c-contratos svg').selectAll('g').each(function (d) { d3.select(this).select('text:nth-of-type(2)').text(`${M(d.marco)} · ${d.n} contratos`); });
}

/* ---- Estado y avance de las obras ---- */
function renderEstado() {
  const el = $('#c-estado'); el.innerHTML = '';
  const p = pFil(), rows = Object.keys(ESTADO_COLOR).filter(k => !k.startsWith('Código')).map(k => { const v = p.filter(x => x.estado_obra === k); return {k, n: v.length, m: sum(v, 'marco_fen')}; }).filter(d => d.n);
  if (!rows.length) { el.innerHTML = '<div class="empty">Sin proyectos para esta selección.</div>'; return; }
  const W = el.clientWidth, row = 34, H = rows.length * row, L = Math.min(270, W * 0.55);
  const x = d3.scaleLinear().domain([0, d3.max(rows, d => d.n)]).range([L, W - 110]);
  const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('width', '100%');
  const g = svg.selectAll('g').data(rows).join('g').attr('transform', (d, i) => `translate(0,${i * row})`);
  g.append('circle').attr('cx', 6).attr('cy', 14).attr('r', 5).attr('fill', d => ESTADO_COLOR[d.k]);
  g.append('text').attr('x', 16).attr('y', 18).attr('font-size', 12).attr('fill', 'var(--ink-2)').text(d => d.k);
  g.append('rect').attr('x', L).attr('y', 6).attr('height', 16).attr('rx', 4).attr('width', d => x(d.n) - L).attr('fill', d => ESTADO_COLOR[d.k]);
  g.append('text').attr('x', d => x(d.n) + 6).attr('y', 18).attr('font-size', 11).attr('fill', 'var(--ink-2)').text(d => `${d.n} · ${M(d.m)}`);
  g.append('rect').attr('width', W).attr('height', row).attr('fill', 'transparent').style('cursor', 'pointer')
    .on('mouseenter mousemove', (ev, d) => showTip(ev, `<b>${d.k}</b><br>${d.n} proyectos<br>FEN autorizado: ${M(d.m)}<br>Clic para filtrar la tabla`)).on('mouseleave', hideTip)
    .on('click', (ev, d) => { $('#t-estado').value = d.k; renderTable(); $('#t-proy').scrollIntoView({behavior: 'smooth', block: 'center'}); });
}

function renderAvance() {
  const el = $('#c-avance'); el.innerHTML = '';
  const all = pFil().filter(p => p.estado_obra !== 'Código genérico (no es obra)' && p.avance_financiero != null);
  const est = Object.keys(ESTADO_COLOR).filter(k => all.some(p => p.estado_obra === k));
  if (!all.length) { el.innerHTML = '<div class="empty">Sin proyectos para esta selección.</div>'; return; }
  const W = el.clientWidth, narrow = W < 520, L = narrow ? 0 : 170, row = narrow ? 64 : 52, H = est.length * row + 26;
  const x = d3.scaleLinear().domain([0, 100]).range([L + 8, W - 12]);
  const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('width', '100%');
  svg.append('g').attr('class', 'grid').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(5).tickSize(-(H - 20)).tickFormat('')).call(s => s.select('.domain').remove());
  svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(5).tickFormat(v => v + '%')).call(s => s.select('.domain').remove());
  est.forEach((k, i) => {
    const y0 = i * row, v = all.filter(p => p.estado_obra === k).sort((a, b) => a.avance_financiero - b.avance_financiero);
    const med = d3.median(v, p => p.avance_financiero);
    svg.append('text').attr('x', 0).attr('y', y0 + (narrow ? 12 : row / 2)).attr('font-size', 12).attr('fill', 'var(--ink-2)').text(narrow ? `${k} · mediana ${P(med)}` : k.replace(', sin avance registrado', ''));
    if (!narrow) svg.append('text').attr('x', 0).attr('y', y0 + row / 2 + 15).attr('font-size', 11).attr('fill', 'var(--ink-3)').text(`${v.length} proy. · mediana ${P(med)}`);
    const cy = y0 + (narrow ? 38 : row / 2 + 2), placed = [];
    v.forEach(p => { let cx = x(Math.min(100, p.avance_financiero)), dy = 0; const free = (X, Y) => !placed.some(q => Math.abs(q[0] - X) < 10 && Math.abs(q[1] - Y) < 10); search: for (;;) { for (const o of [0, -10, 10]) if (free(cx, o)) { dy = o; break search; } cx += 10; } placed.push([cx, dy]);
      svg.append('circle').attr('cx', cx).attr('cy', cy + dy).attr('r', 5).attr('fill', ESTADO_COLOR[k]).attr('stroke', 'var(--panel)').attr('stroke-width', 1.5)
        .on('mouseenter mousemove', ev => showTip(ev, `<b>${title(p.nombre).slice(0, 130)}</b><br>CUI ${p.cui} · ${k}<br>Avance financiero: ${P(p.avance_financiero)} (${M(p.devengado_acumulado)} de ${M(p.costo_actualizado_ssi)})<br>Avance físico: ${p.avance_consolidado != null ? P(p.avance_consolidado) + (p.avance == null ? ' (Infobras)' : '') : 'no registrado'}${p.fin_ejecucion ? '<br>Fin previsto: ' + p.fin_ejecucion : ''}`)).on('mouseleave', hideTip); });
  });
}

function avCell(p) {
  const bi = p.avance, ib = p.ib_avance, v = p.avance_consolidado;
  let h = v != null ? `Físico ${P(v)}<div class="bar-mini"><span style="width:${Math.min(100, v)}%"></span></div>` : '<span style="color:var(--ink-3)">Físico: sin registro</span>';
  if (bi != null && ib != null) h += p.avance_fuentes === 'coincide' ? `<div class="fuentes-ok">✓ Coinciden MEF e Infobras</div>` : `<div class="note" style="margin:2px 0 0">MEF ${P(bi)} · Infobras ${P(ib)}</div>`;
  else if (ib != null) h += `<div class="note" style="margin:2px 0 0">Infobras, ${p.ib_periodo}</div>`;
  else if (bi != null) h += `<div class="note" style="margin:2px 0 0">MEF (Formato 12-B)</div>`;
  if (p.avance_financiero != null) h += `<div class="note" style="margin:2px 0 0">Financiero ${P(p.avance_financiero)}</div>`;
  if (p.fin_ejecucion) h += `<div class="note" style="margin:0">Fin previsto ${p.fin_ejecucion}</div>`;
  return h;
}
let sortKey = 'marco_fen', sortDir = -1, lastKey = 'marco_fen';
function renderTable() {
  const q = $('#t-q').value.trim().toLowerCase(), est = $('#t-estado').value;
  const rows = pFil().filter(p => (!est || p.estado_obra === est) && (!q || [p.nombre, p.ejecutora, p.todos_contratistas, p.cui].join(' ').toLowerCase().includes(q)))
    .sort((a, b) => sortDir * d3.ascending(a[sortKey] ?? -Infinity, b[sortKey] ?? -Infinity));
  const tb = $('#t-proy tbody'); tb.innerHTML = '';
  rows.forEach(p => {
    const tr = document.createElement('tr');
    const cells = [
      `<a href="${p.ficha_mef}" target="_blank" rel="noopener">${title(p.nombre).slice(0, 120)}${p.nombre.length > 120 ? '…' : ''}</a><div class="note" style="margin:2px 0 0">CUI ${p.cui} · ${title(p.departamento)} · ${p.norma}</div>`,
      title(p.ejecutora), M(p.marco_fen), M(p.dev_fen),
      avCell(p),
      `<span class="badge" style="--c:${ESTADO_COLOR[p.estado_obra]}">${p.estado_obra}</span>` + (p.estado_obra === 'Paralizada' && p.ib_comentario ? `<div class="note" style="margin:4px 0 0">${p.ib_comentario}</div>` : '') + (p.contratos_resueltos ? `<div class="note" style="margin:4px 0 0">Contrato resuelto (Infobras)</div>` : ''),
      p.contratistas_obra ? title(p.contratistas_obra) + (p.contratos_previos ? `<div class="note" style="margin:2px 0 0">${p.contratos_previos} de ${p.n_contratos} contratos firmados antes de la norma</div>` : '') : (p.n_contratos ? `<span style="color:var(--ink-3)">${p.n_contratos} contratos de bienes o servicios</span>` : '<span style="color:var(--ink-3)">Sin contrato en el SEACE</span>'),
      p.situaciones_adversas ? `${p.n_informes}<div class="note" style="margin:2px 0 0">${p.situaciones_adversas} situaciones adversas</div>` : (p.n_informes || '0')];
    cells.forEach((c, i) => { const td = document.createElement('td'); if ([2, 3, 4, 7].includes(i)) td.className = 'num'; td.innerHTML = c; tr.appendChild(td); });
    tb.appendChild(tr);
  });
  if (!rows.length) tb.innerHTML = '<tr><td colspan="8" class="empty">Ningún proyecto coincide con la búsqueda.</td></tr>';
  $('#t-note').textContent = `${rows.length} proyectos · ordenado por ${document.querySelector(`#t-proy th[data-k="${sortKey}"]`).textContent.toLowerCase()} · haz clic en un encabezado para ordenar y en el nombre para abrir la ficha oficial del MEF.`;
}

/* ---- Secciones que no dependen de los filtros ---- */
function renderStatic() {
  // Intervenciones de 2026 que repiten un punto de 2023 (se usan en los hallazgos)
  const rep = D.inter.filter(d => d.anio === 2026 && d.repetido);

  // Hallazgos calculados con los mismos datos del tablero
  const g = D.gasto, seen = new Set();
  const c = D.contratos.filter(d => { const k = d.proceso + d.contratista + d.monto; if (seen.has(k)) return false; seen.add(k); return true; });
  const cPrev = c.filter(d => d.antes_de_la_norma);
  const qb = D.proyectos.filter(p => p.estado_obra === 'Cerrado sin culminar');
  const qbRepRows = rep.filter(d => d.repetido === 'Misma quebrada' && /^Qda/.test(d.rio)), qbRep = new Set(qbRepRows.map(d => d.rio.toLowerCase())).size;
  const y = a => g.filter(d => d.anio === a), m26 = sum(y(2026), 'marco'), d26 = sum(y(2026), 'devengado');
  const m23 = sum(y(2023), 'marco'), d23 = sum(y(2023), 'devengado');
  const lima = g.filter(d => !sinSede(d)), mt = sum(g, 'marco');
  const psi = g.filter(d => d.anio === 2026 && /IRRIGACION - PSI/.test(d.ejecutora));
  $('#findings').innerHTML = [
    [`${cPrev.length} de ${c.length}`, `contratos vinculados a los proyectos FEN se firmaron <b>antes</b> de la norma que les dio el dinero (${M(sum(cPrev, 'monto'))} de ${M(sum(c, 'monto'))}). Puentes contratados en 2019 y obras de la Reconstrucción con Cambios de 2020–2021 recibieron fondos "por El Niño": el dinero pagó obras en curso, no intervenciones nuevas.`],
    [`${qb.length} quebradas`, `de Lima Este (ANA, Ley 31912 de 2023) recibieron ${M(sum(qb, 'marco_fen'))} del FEN y figuran como <b>cerradas sin culminar</b> en el Banco de Inversiones. La Contraloría identifica como ejecutor al Consorcio SQA - LGQ, contratado por contratación directa sin registro en el SEACE: sus cartas fianza por adelanto directo suman ${M(d3.sum(uniq(D.qcgr.filter(d => d.carta_fianza_adelanto_directo), 'carta_fianza_adelanto_directo'), d => d.carta_fianza_adelanto_directo))}, casi lo mismo que el devengado FEN (${M(sum(qb, 'dev_fen'))}). Ninguna tiene avance en Infobras. En 2026 se vuelven a asignar ${qbRepRows.length} barreras dinámicas en ${qbRep} de esas quebradas.`],
    [`${P(100 * d26 / m26)}`, `de los ${M(m26)} autorizados entre agosto y octubre de 2026 para el nuevo Niño se había gastado al 28 de octubre. En 2023 se llegó a ${P(100 * d23 / m23)}. El Programa Subsectorial de Irrigación (PSI) recibió ${M(sum(psi, "marco"))} en 2026 y apenas devengó ${P(100 * sum(psi, 'devengado') / sum(psi, 'marco'))}.`],
    [`${P(100 * sum(lima, 'marco') / mt)}`, `del dinero (${M(sum(lima, 'marco'))}) lo ejecutan entidades nacionales que lo registran con meta en Lima. Sin pedir información a cada entidad no se puede saber en qué región se gastó: la trazabilidad territorial del gasto FEN es limitada.`],
    [`${P(100 * sum(D.seace.filter(d => d.proceso === 'Contratación Directa'), 'monto') / sum(D.seace, 'monto'))}`, `del monto de los ${D.seace.length} contratos del SEACE identificados para las actividades FEN (${M(sum(D.seace, 'monto'))}) se adjudicó por <b>contratación directa</b>, sin competencia. El mayor es de 2026: ${M(d3.max(D.seace, d => d.monto))} a ${title(D.seace.slice().sort((a, b) => b.monto - a.monto)[0].proveedor)} para barreras dinámicas en las quebradas de Lima Este.`],
    [`${uniq(D.control.filter(d => d.n_situaciones > 0), 'codigo').length} informes`, `de la Contraloría advierten situaciones adversas en ${new Set(D.control.filter(d => d.n_situaciones > 0).map(d => d.cui)).size} de los ${D.proyectos.filter(p => p.estado_obra !== 'Código genérico (no es obra)').length} proyectos FEN: expedientes técnicos pagados sin cumplir el contenido mínimo, documentación inexacta, pagos y liquidaciones observadas. Además, Infobras registra ${D.proyectos.filter(p => p.estado_obra === 'Paralizada').length} obras paralizadas y ${D.proyectos.filter(p => p.contratos_resueltos > 0).length} proyectos con contratos resueltos, y ${uniq(D.sanciones, 'ruc').length} proveedores con contratos FEN tienen antecedentes de sanción del Tribunal de Contrataciones (${uniq(D.sanciones.filter(d => d.vigente_hoy === 'Sí'), 'ruc').length} vigentes hoy).`],
  ].map(([n, t]) => `<div class="finding"><div class="n">${n}</div><p>${t}</p></div>`).join('');

  $('#method').innerHTML = `
  <h4>Pregunta</h4><p>¿A dónde se destinó el dinero autorizado por las normas para el Fenómeno El Niño, quiénes lo ejecutaron y en qué estado están las obras, de cara al nuevo Niño de 2026?</p>
  <h4>Fuentes</h4><ul>
   <li><a href="https://www.datosabiertos.gob.pe/" target="_blank" rel="noopener">MEF – Ejecución del gasto de emergencias FEN</a> (Datos Abiertos), años 2023, 2024, 2025 y 2026, descargados el 28/10/2026.</li>
   <li>MEF – Banco de Inversiones (detalle de inversiones) y avance mensual por componente, descargados el 3/11/2026.</li>
   <li><a href="https://ofi5.mef.gob.pe/ssi/" target="_blank" rel="noopener">MEF – Seguimiento de Inversiones (SSI)</a>: contratos del SEACE (OECE) e informes de control de la Contraloría por CUI, consultados el 4/11/2026.</li>
   <li><a href="https://data.open-contracting.org/en/publication/135" target="_blank" rel="noopener">OECE – Contrataciones abiertas (OCDS)</a>, años 2023 y 2026, descargados el 4/11/2026: contratos de las 20 ejecutoras con más gasto FEN.</li>
   <li><a href="https://infobras.contraloria.gob.pe/InfobrasWeb/" target="_blank" rel="noopener">Contraloría – Infobras</a>: último reporte mensual de avance físico, paralizaciones y comentarios de cada obra vinculada a los CUI (consultado el 4/11/2026).</li>
   <li>Contraloría – fichas resumen e informes de control simultáneo (hito de control, orientación de oficio, visita de control, control concurrente) vinculados a cada CUI en la ficha SSI; se leyeron las 134 fichas resumen y se clasificaron sus situaciones adversas por tipo.</li>
   <li><a href="https://apps.osce.gob.pe/perfilprov-ui/" target="_blank" rel="noopener">OECE – Ficha Única del Proveedor</a>: sanciones del Tribunal de Contrataciones y penalidades de los proveedores con RUC (consultado el 4/11/2026).</li>
   <li>Textos y anexos de los decretos de urgencia publicados en <a href="https://diariooficial.elperuano.pe/" target="_blank" rel="noopener">El Peruano</a> (DU 009, 015, 016, 019, 025, 030, 031, 035, 036 y 037-2023; DU 008, 010 y 013-2026), sistematizados a mano.</li>
   <li>Límites departamentales y distritales (INEI), versión simplificada de juaneladio/peru-geojson.</li></ul>
  <h4>Procesamiento</h4><p>Se unieron los cuatro archivos del MEF (4 833 líneas, sin duplicados), se normalizó el nombre de la norma, el departamento y el nivel de gobierno, y se agregó por norma, ejecutora, departamento y genérica. "Autorizado" es el marco presupuestal asignado por la norma; "devengado" es el gasto reconocido. Los 49 CUI del archivo FEN se cruzaron con el Banco de Inversiones, el avance mensual y los contratos del SEACE de la ficha SSI. Un contrato es "previo" si su fecha de suscripción es anterior a la publicación de la norma FEN que financió el proyecto. Para las actividades sin CUI, se tomaron los contratos del SEACE de las 20 ejecutoras con más gasto FEN firmados entre la publicación de la norma y el fin del año fiscal, y se clasificaron como "cita FEN" (el texto menciona El Niño, el decreto o el peligro inminente) o "tema" (descolmatación, defensas ribereñas, quebradas, maquinaria, módulos de emergencia); los demás no se atribuyen al FEN. Las 880 intervenciones de los anexos se ubicaron con sus coordenadas UTM cuando existían (119) o con el centroide del distrito o la provincia; 40 no pudieron ubicarse.</p>
  <h4>Estado de las obras</h4><p>El estado, el avance físico, el devengado acumulado y las fechas de ejecución provienen de la ficha SSI de cada CUI (consultada el 4/11/2026). "En ejecución": activo con avance físico registrado. "Plazo vencido, sin avance registrado": activo, sin avance físico en el formato de seguimiento y con fecha de fin ya pasada. "Cerrado sin culminar": la entidad registró el cierre de la inversión indicando que no se culminó. El avance financiero es el devengado acumulado entre el costo actualizado. Tres códigos (2000270, 2000351 y 2001621) son categorías presupuestales genéricas y no obras.</p>
  <h4>Limitaciones</h4><ul>
   <li>Más del 90% del dinero son actividades sin CUI (limpieza de cauces, alquiler de maquinaria, combustible), cuyo contratista no puede identificarse sin solicitudes de acceso a la información ni cruces con el SEACE por entidad y fecha.</li>
   <li>El gasto del Gobierno Nacional se registra mayormente con meta en Lima; el mapa por región lo excluye por defecto.</li>
   <li>2026 está en ejecución: el devengado corresponde al 28/10/2026. El archivo 2025 del MEF no tiene registros.</li>
   <li>Las fichas SSI advierten que los vínculos con el SEACE e Infobras son referenciales; algunos contratos cubren varios CUI (se cuentan una sola vez en los totales).</li>
   <li>Los informes de control simultáneo advierten riesgos y situaciones adversas; no determinan responsabilidades ni sanciones. Las sanciones del Tribunal se revisaron en la Ficha Única del Proveedor (OECE) para los 132 proveedores con RUC; los consorcios sin RUC propio no pudieron revisarse porque el registro no identifica a sus integrantes.</li>
   <li>Para proyectos con varios paquetes, Infobras reporta el avance por paquete; en esos casos se usa el avance del Banco de Inversiones.</li>
   <li>La coincidencia de puntos 2023–2026 se basó en nombre del cauce, distrito y distancia entre coordenadas; "probable" y "posible" requieren verificación en campo.</li></ul>
  <h4>Uso de IA</h4><p>El procesamiento, el código y el diseño se hicieron con asistencia de Claude (Anthropic). Las cifras se verificaron contra los archivos originales, que están en el repositorio.</p>`;
}

/* ---- Contratos SEACE de las actividades FEN ---- */
const VCOL = v => v.startsWith('Cita') ? 'var(--accent)' : 'var(--neutral)';
let NIV; const sFil = () => { NIV = NIV || new Map(D.gasto.map(d => [d.ejecutora.trim(), d.nivel])); return D.seace.filter(d => (!F.anio || d.anio_fen == F.anio) && (!F.nivel || NIV.get(d.ejecutora_mef.trim()) === F.nivel)); };
function renderSeace() {
  const s = sFil(), tot = sum(s, 'monto'), dir = s.filter(d => d.proceso === 'Contratación Directa');
  const cita = s.filter(d => d.nivel_vinculo.startsWith('Cita'));
  const act = gFil().filter(d => d.tipo === 'Actividad'), devAct = sum(act, 'devengado');
  $('#seace-sum').innerHTML = s.length ? `<div><b>${s.length}</b>contratos · ${M(tot)}</div><div><b>${P(100 * sum(dir, 'monto') / tot)}</b>del monto por contratación directa (${dir.length} contratos)</div><div><b>${cita.length}</b>citan expresamente El Niño o la norma (${M(sum(cita, 'monto'))})</div><div><b>${P(100 * tot / devAct)}</b>del devengado en actividades (${M(devAct)}) queda identificado con un proveedor</div>` : '<div>Sin contratos para esta selección.</div>';
  const top = d3.rollups(s, v => ({marco: sum(v, 'monto'), dev: 0, n: v.length, cita: v.some(x => x.nivel_vinculo.startsWith('Cita')), ej: [...new Set(v.map(x => title(x.ejecutora_mef)))].join(', '), ruc: v[0].ruc}), d => d.proveedor)
    .map(([k, o]) => ({k, ...o})).sort((a, b) => b.marco - a.marco).slice(0, 12);
  hbars($('#c-prov'), top, {label: d => title(d.k), lw: 280, solid: d => d.cita ? 'var(--accent)' : 'var(--neutral)',
    tipf: d => `<b>${title(d.k)}</b><br>${/^(10|20)\d{9}$/.test(d.ruc || '') ? 'RUC ' + d.ruc : 'ID OECE ' + (d.ruc || '—')}<br>${d.n} contrato(s) · ${M(d.marco)}<br>Ejecutora: ${d.ej}`});
  renderSeaceTable();
}
function renderSeaceTable() {
  const q = $('#s-q').value.trim().toLowerCase(), v = $('#s-v').value;
  const rows = sFil().filter(d => (!v || d.nivel_vinculo === v) && (!q || [d.proveedor, d.ruc, d.tender_description, d.ejecutora_mef].join(' ').toLowerCase().includes(q)));
  $('#t-seace tbody').innerHTML = rows.slice(0, 300).map(d => `<tr><td>${d.fecha}</td><td>${title(d.ejecutora_mef)}</td><td>${title(d.proveedor || '—')}<div class="note" style="margin:2px 0 0">${/^(10|20)\d{9}$/.test(d.ruc || '') ? 'RUC ' + d.ruc : 'ID OECE ' + (d.ruc || '—')}</div></td><td class="num">${M(d.monto)}</td><td>${d.proceso}</td><td><span class="badge" style="--c:${VCOL(d.nivel_vinculo)}">${d.nivel_vinculo.startsWith('Cita') ? 'Cita FEN' : 'Tema'}</span> ${(d.tender_description || '').toLowerCase().replace(/^./, c => c.toUpperCase())}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">Sin contratos para esta búsqueda.</td></tr>';
}

/* ---- Alertas de control (Contraloría) ---- */
const uniq = (a, k) => { const s = new Set(); return a.filter(d => { if (s.has(d[k])) return false; s.add(d[k]); return true; }); };
function renderAlertas() {
  const c = D.control, inf = uniq(c, 'codigo'), adv = inf.filter(d => d.n_situaciones > 0), P0 = D.proyectos;
  const par = P0.filter(p => p.estado_obra === 'Paralizada'), res = P0.filter(p => p.contratos_resueltos > 0);
  $('#al-sum').innerHTML = `<div><b>${inf.length}</b>informes de control sobre ${new Set(c.map(d => d.cui)).size} proyectos FEN</div><div><b>${adv.length}</b>advierten situaciones adversas (${d3.sum(adv, d => d.n_situaciones)} en total)</div><div><b>${par.length}</b>obras paralizadas según Infobras</div><div><b>${res.length}</b>proyectos con al menos un contrato resuelto (Infobras)</div>`;
  const cats = Object.keys(CAT).map(k => ({k, marco: adv.filter(d => d.categorias.split(',').includes(k)).length, dev: 0})).filter(d => d.marco).sort((a, b) => b.marco - a.marco);
  hbars($('#c-alertas'), cats, {label: d => CAT[d.k], lw: 260, solid: 'var(--crit)', tipf: d => `<b>${CAT[d.k]}</b><br>${d.marco} informes`, onClick: d => { $('#al-cat').value = d.k; renderAlertTable(); }});
  d3.selectAll('#c-alertas svg > g').each(function (d) { d3.select(this).select('text:nth-of-type(2)').text(`${d.marco} informes`); });
  const pr = d3.rollups(c.filter(d => d.n_situaciones > 0), v => d3.sum(v, d => d.n_situaciones), d => d.cui).map(([cui, n]) => { const p = P0.find(x => x.cui === cui) || {}; return {k: cui, marco: n, dev: 0, nom: p.nombre || cui, est: p.estado_obra}; })
    .sort((a, b) => b.marco - a.marco).slice(0, 10);
  hbars($('#c-alproy'), pr, {label: d => title(d.nom).replace(/^(Rehabilitacion|Creacion|Mejoramiento|Instalacion) de(l)? (los )?(Servicio(s)? de )?/i, '').slice(0, 60), lw: 300, solid: d => ESTADO_COLOR[d.est] || 'var(--neutral)', tipf: d => `<b>${title(d.nom).slice(0, 120)}</b><br>CUI ${d.k} · ${d.est}<br>${d.marco} situaciones adversas`});
  d3.selectAll('#c-alproy svg > g').each(function (d) { d3.select(this).select('text:nth-of-type(2)').text(`${d.marco}`); });
  const base = 'https://apps8.contraloria.gob.pe/SPIC/srvDownload/ViewPDF?CRES_CODIGO=';
  $('#casos').innerHTML = D.casos.map(k => `<div class="caso"><h4>${k.titulo}</h4><div class="sub">${k.proyectos}</div><p>${k.texto}</p><div class="refs src"><b>Fuente:</b> Contraloría, informes ${k.informes.map(([n, c]) => `<a href="${base}${c}&TIPOARCHIVO=RE" target="_blank" rel="noopener">${n}</a>`).join('')}${k.fuentes_extra ? '<br>' + k.fuentes_extra : ''}</div></div>`).join('');
  Object.keys(CAT).forEach(k => $('#al-cat').insertAdjacentHTML('beforeend', `<option value="${k}">${CAT[k]}</option>`));
  renderAlertTable(); renderSanciones();
}
function renderAlertTable() {
  const k = $('#al-cat').value, q = $('#al-q').value.trim().toLowerCase();
  const rows = D.control.filter(d => d.n_situaciones > 0 && (!k || d.categorias.split(',').includes(k)) && (!q || [d.nombre, d.numero, d.cui, d.fecha].join(' ').toLowerCase().includes(q)))
    .sort((a, b) => d3.descending(a.fecha, b.fecha));
  $('#t-alertas tbody').innerHTML = rows.map(d => `<tr><td>${d.fecha}</td><td>${d.numero}<div class="note" style="margin:2px 0 0">${d.tipo}</div></td><td>${title(d.nombre || '').slice(0, 90)}<div class="note" style="margin:2px 0 0">CUI ${d.cui}</div></td><td class="num">${d.n_situaciones}</td><td>${d.categorias.split(',').filter(Boolean).map(c => `<span class="badge" style="--c:var(--crit);margin:0 4px 4px 0">${CAT[c]}</span>`).join('')}</td><td><a href="${d.url_resumen}" target="_blank" rel="noopener">Ficha resumen</a></td></tr>`).join('') || '<tr><td colspan="6" class="empty">Sin informes para esta selección.</td></tr>';
  $('#al-note').textContent = `${rows.length} filas · un informe puede referirse a varios proyectos del mismo paquete.`;
}

/* ---- Sanciones del Tribunal (OECE) ---- */
function renderSanciones() {
  const S = D.sanciones, prov = uniq(S, 'ruc'), vig = uniq(S.filter(d => d.vigente_hoy === 'Sí'), 'ruc'), dur = S.filter(d => d.vigente_al_contratar === 'Sí');
  const falsos = uniq(S.filter(d => /falsos|inexacta/i.test(d.motivo)), 'ruc');
  $('#sa-sum').innerHTML = `<div><b>${prov.length} de 132</b>proveedores tienen al menos una sanción del Tribunal (${S.length} sanciones)</div><div><b>${vig.length}</b>tienen una sanción vigente hoy</div><div><b>${falsos.length}</b>fueron sancionados por información inexacta o documentos falsos</div><div><b>${dur.length}</b>sanciones temporales estaban vigentes cuando firmaron su contrato FEN</div>`;
  const rows = S.slice().sort((a, b) => (b.vigente_hoy === 'Sí') - (a.vigente_hoy === 'Sí') || b.monto_contratos_fen - a.monto_contratos_fen);
  $('#t-sanciones tbody').innerHTML = rows.map(d => `<tr><td>${title(d.proveedor)}<div class="note" style="margin:2px 0 0">RUC ${d.ruc}</div></td><td>${d.tipo === 'TEMPORAL' ? 'Inhabilitación temporal' : 'Multa'}${d.periodo && d.periodo !== 'NO APLICA' ? ' · ' + d.periodo.toLowerCase() : ''}${d.vigente_hoy === 'Sí' ? '<div><span class="badge" style="--c:var(--crit)">Vigente</span></div>' : ''}</td><td>${d.inicio ? d.inicio + ' – ' + d.fin : '—'}</td><td style="font-size:12px;color:var(--ink-2);min-width:240px">${d.motivo.replace(/^[a-z]\)\s*/, '')}</td><td class="num">${M(d.monto_contratos_fen)}<div class="note" style="margin:2px 0 0">${d.fecha_contratos}</div></td><td style="font-size:12px">${title(d.ejecutoras)}</td></tr>`).join('');
  const pe = D.penalidades;
  $('#sa-note').innerHTML = `Además, la ficha del OECE registra <b>penalidades</b> aplicadas por entidades a ${uniq(pe, 'ruc').length} proveedores, entre ellas ${pe.filter(d => d.monto > 1e6).map(d => `${M(d.monto)} a ${title(d.proveedor)} (${d.fecha})`).join(', ')}. No se pudo revisar a los consorcios sin RUC propio (como el Consorcio SQA - LGQ o el Consorcio Barreras Dinámicas), porque el registro no identifica a sus integrantes.`;
}
