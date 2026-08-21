<script>
/* ==========================================================
   李家村万达 · 业绩看板
   原则：只展示表格里的原值，不做任何二次计算
   ========================================================== */

const EMBEDDED_DATA = __DATA__;

const CFG = {
  repo   : 'ZBC5241/shop',
  branch : 'main',
  dataFile: 'data.json',
  // 达成率相对时间进度的判定门槛
  th     : { on: 0.85, low: 0.55 }
};

let DATA = EMBEDDED_DATA;
let VIEW = 'store';
let BOARD = (location.hash === '#ops') ? 'ops' : 'sales';   /* 板块：sales 销售看板 / ops 运营看板 */
let RANK_BY = '毛利';
let PERSON = null;

/* 板块配置：每个板块有自己的底部 Tab 集合（运营板块后续可加更多 tab） */
const BOARDS = {
  sales: { name: '销售看板', tabs: ['store', 'rank', 'person', 'day', 'insight'] },
  ops:   { name: '运营看板', tabs: ['qudao'] }
};
const TAB_META = {
  store:   { name: '门店', svg: '<path d="M3 9l9-6 9 6v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 21V12h6v9"/>' },
  rank:    { name: '排行', svg: '<path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0z"/><path d="M7 4H4v2a3 3 0 0 0 3 3M17 4h3v2a3 3 0 0 1-3 3"/>' },
  person:  { name: '个人', svg: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>' },
  day:     { name: '今日', svg: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/>' },
  insight: { name: '洞察', svg: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>' },
  qudao:   { name: '渠道', svg: '<path d="M3 10l9-6 9 6M4 10v9h16v-9M9 19v-5h6v5"/>' }
};

/* ---------------- 工具 ---------------- */
const $  = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const isNum = v => typeof v === 'number' && isFinite(v);

function money(v, dec){
  if(!isNum(v)) return '—';
  const d = dec === undefined ? (Math.abs(v) >= 10000 ? 0 : 0) : dec;
  return '¥' + Number(v).toFixed(d);
}
function moneyShort(v){
  if(!isNum(v)) return '—';
  return String(Math.round(v));
}
function cnt(v){ return isNum(v) ? String(Math.round(v)) : '—'; }
/* 精准金额：整数原样（带千分位），不缩写「万」。用于渠道挂账板块。 */
function moneyFull(v){
  if(!isNum(v)) return '—';
  return String(Math.round(v));
}
function pct(v, dec){
  if(!isNum(v)) return '—';
  return (v*100).toFixed(dec === undefined ? 1 : dec) + '%';
}
function esc(s){
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

/* 状态判定：done / over / on / low / na */
function stat(rate){
  const tp = DATA.meta.timeProgress;
  if(!isNum(rate)) return 'na';
  if(rate >= 1) return 'done';
  if(!isNum(tp) || tp <= 0) return 'on';
  if(rate >= tp) return 'over';
  if(rate >= tp * CFG.th.on)  return 'on';
  if(rate >= tp * CFG.th.low) return 'low';
  return 'low';
}
function isCritical(rate){
  const tp = DATA.meta.timeProgress;
  return isNum(rate) && isNum(tp) && tp > 0 && rate < tp * CFG.th.low;
}
const STAT_TXT = { done:'已达成', over:'超进度', on:'跟得上', low:'落后', na:'无任务' };

/* 进度提示行（short = 缺口量，>0=缺口多少，<0=超额完成）：
   - short>0 未完成：状态词 + 「缺口 X[单位]」
   - short<=0 已完成：只给形容词（超额完成/任务已达成），不写金额——
     月份未结束，写金额容易给人已结清/超额完成的错觉（晨哥 2026-08-19 拍板）。
   注意：品类行 gap 是 done-task（负=缺），挂账行 gap 是 task-done（正=缺），
   调用方需先把 gap 归一到「缺口」语义再传入。 */
function gapHintHTML(s, short, fmt, unit){
  if(!isNum(short)) return '';
  let inner;
  if(short > 0){
    const w = {low:'进度落后', on:'进度正常', over:'进度领先', done:'进度达标'}[s] || STAT_TXT[s] || '进度';
    inner = '<span>' + w + '</span><em>缺口 ' + fmt(short) + (unit || '') + '</em>';
  }else{
    const w = (short < 0) ? '超额完成' : '任务已达成';
    inner = '<span style="color:var(--green);font-weight:700">' + w + '</span>';
  }
  return '<div class="row-g">' + inner + '</div>';
}

/* 是否有任务 */
function hasTask(k){ return k && isNum(k.task) && k.task !== 0; }

/* 单位：哪些指标是金额 */
const MONEY_KEYS = new Set(['毛利','销额','增值']);

/* 同一行内统一单位：完成量和任务量都上万才换算成"万"，否则一律用元 */
function unitOf(key, k){
  if(!MONEY_KEYS.has(key)) return 'cnt';
  if(!k) return 'yuan';
  const d = isNum(k.done) ? Math.abs(k.done) : 0;
  const t = isNum(k.task) ? Math.abs(k.task) : d;
  return (d >= 10000 && t >= 10000) ? 'wan' : 'yuan';
}
function fmtU(v, u){
  if(!isNum(v)) return '—';
  if(u === 'cnt')  return String(Math.round(v));
  return String(Math.round(v));
}

/* ---------------- 渲染：进度条组件 ---------------- */
function barHTML(rate, s){
  const tp = DATA.meta.timeProgress;
  const w  = isNum(rate) ? Math.min(rate, 1) * 100 : 0;
  const mk = isNum(tp) ? Math.min(tp, 1) * 100 : null;
  return '<div class="row-bar"><i class="f-' + s + '" style="width:' + w.toFixed(1) + '%"></i>'
       + (mk !== null ? '<span class="mk" style="left:' + mk.toFixed(1) + '%"></span>' : '')
       + '</div>';
}

/* ---------------- 视图 1：门店 ---------------- */
const CORE = [
  {k:'毛利', label:'毛利'},
  {k:'销额', label:'销售额'},
  {k:'手机', label:'手机'},
];
const CATS = ['手机','PC','平板','穿戴','音频','HD','智慧办公','音频穿戴'];

function kpiCard(label, k, key){
  if(!k) return '';
  const s = hasTask(k) ? stat(k.rate) : 'na';
  const rateTxt = hasTask(k) ? pct(k.rate,1) : '无任务';
  const u = unitOf(key, k);
  return '<div class="kpi s-' + s + '" data-kpi="' + esc(key) + '">'
    + '<div class="kpi-r r-' + s + '">' + rateTxt + '</div>'
    + '<div class="kpi-l">' + esc(label) + '</div>'
    + '<div class="kpi-v num">' + fmtU(k.done, u) + '</div>'
    + '<div class="kpi-s num">任务 ' + (hasTask(k) ? fmtU(k.task, u) : '—')
    + (isNum(k.gap) && hasTask(k) ? ' · 缺 ' + fmtU(Math.abs(k.gap), u) : '') + '</div>'
    + '<div class="kpi-bar"><i class="f-' + s + '" style="width:'
    + (isNum(k.rate) ? Math.min(k.rate,1)*100 : 0).toFixed(1) + '%"></i></div>'
    + '</div>';
}

function catRow(name, k, key, person){
  if(!k) return '';
  const has = hasTask(k);
  const s   = has ? stat(k.rate) : 'na';
  const crit = has && isCritical(k.rate);
  const u = unitOf(key, k);
  const pc = person ? ' data-person="' + esc(person) + '"' : '';
  return '<div class="row cat-click' + (crit ? ' warn' : '') + '" data-cat="' + esc(name) + '"' + pc + '>'
    + '<div class="row-t">'
      + '<span class="row-n">' + esc(name) + '</span>'
      + '<span class="row-p r-' + s + '">' + (has ? pct(k.rate,0) : '无任务') + '</span>'
      + '<span class="row-v num"><b>' + fmtU(k.done, u) + '</b>'
      + (has ? ' / ' + fmtU(k.task, u) : '') + '</span>'
      + '<span class="chev">' + ic('chev') + '</span>'
    + '</div>'
    + barHTML(k.rate, s)
    + (has ? gapHintHTML(s, -k.gap, v => fmtU(v, u), u === 'cnt' ? '台' : '') : '')
    + '</div>'
    + '<div class="cat-det" data-cat="' + esc(name) + '"' + pc + '></div>';
}

function money(v){ v = (v == null ? 0 : v); return String(Math.round(v)); }
/* 明细用：无千分位逗号、无货币符号 */
function fmtNum(v){ v = (v == null ? 0 : v); return Number(v).toLocaleString('en-US', {maximumFractionDigits:2, useGrouping:false}); }

/* 品类销售明细（点击品类行下钻） */
function detailRowsHTML(cat, person){
  let rows = (DATA.details && DATA.details[cat]) || [];
  if(person) rows = rows.filter(r => r.emp === person);
  if(!rows.length) return '<div class="det-empty">该品类暂无销售明细</div>';
  let h = '<div class="det-list">';
  rows.forEach((r, i) => {
    const neg = (r.amount || 0) < 0;
    h += '<div class="det-item' + (neg ? ' neg' : '') + '">'
      + '<div class="det-top"><span class="det-name">' + esc(r.name || '—') + '</span>'
      + '<span class="det-date num cd-date-click" onclick="toggleDetCode(\'' + esc(cat) + '\',' + i + (person ? ',\'' + esc(person) + '\'' : '') + ')">' + esc(r.date || '—') + '</span></div>'
      + '<div class="det-row num">'
      + '<span class="dv-origin">原价: <b>' + fmtNum(r.origPrice) + '</b></span>'
      + (r.discPrice && parseFloat(r.discPrice) ? '<span class="dv-disc">折扣: <b>' + fmtNum(r.discPrice) + '</b></span>' : '')
      + '<span class="dv-profit">毛利: <b>' + fmtNum(r.profit) + '</b></span>'
      + (r.so ? '<span class="dv-so">SO: <b>' + Math.round(r.so) + '</b></span>' : '')
      + '<span class="dv-gpr">毛利率: <b>' + (r.gpr == null ? '—' : (r.gpr * 100).toFixed(1) + '%') + '</b></span>'
      + '<span class="dv-cost">成本: <b>' + fmtNum(r.cost) + '</b></span>'
      + '</div>'
      + '<div class="cdet-det" data-cat="' + esc(cat) + '" data-i="' + i + '"' + (person ? ' data-person="' + esc(person) + '"' : '') + '></div>'
      + '</div>';
  });
  h += '</div>';
  return h;
}

function toggleDetail(cat, person){
  person = person || '';
  /* 门店视图无 person（cat-det 不带 data-person 属性）；个人视图带 data-person */
  const psel = person ? '[data-person="' + esc(person) + '"]' : ':not([data-person])';
  const det = document.querySelector('.cat-det[data-cat="' + cat + '"]' + psel);
  if(!det) return;
  const rc  = document.querySelector('.cat-click[data-cat="' + cat + '"]' + psel);
  const open = det.classList.contains('open');
  // 逐层展开：关掉其它已展开项，保持界面干净
  document.querySelectorAll('.cat-det.open').forEach(d => { if(d !== det){ d.classList.remove('open'); d.innerHTML = ''; }});
  document.querySelectorAll('.cat-click.on').forEach(d => { if(d !== rc) d.classList.remove('on'); });
  if(open){ det.classList.remove('open'); det.innerHTML = ''; if(rc) rc.classList.remove('on'); return; }
  det.innerHTML = detailRowsHTML(cat, person);
  det.classList.add('open');
  if(rc) rc.classList.add('on');
}

/* 逐人下钻：列出该员工在各获客渠道的销售额（DATA.qudao.empChannel[员工]，来自桌面销售分析 sheet）
   口径：与渠道挂账完成一致（含全部业务类型，垫付/预订也算）。只展示【渠道 + 金额 + 笔数】。
   点渠道可再下钻到单品明细（DATA.qudao.channelItems[员工][渠道]）。 */
function personDetailHTML(name){
  const emp = (DATA.qudao && DATA.qudao.empChannel) || {};
  const rows = emp[name] || [];
  if(!rows.length) return '<div class="det-empty">该员工本期无获客渠道销售</div>';
  let h = '<div class="det-list">';
  rows.forEach(r => {
    if(!(r.amount > 0)) return;
    h += '<div class="det-item cd-click" data-p="' + esc(name) + '" data-c="' + esc(r.channel) + '" onclick="toggleChannel(\'' + esc(name) + '\',\'' + esc(r.channel) + '\')">'
      + '<div class="det-top"><span class="det-name">' + esc(r.channel)
      + ' <span class="chev" style="display:inline-flex;vertical-align:-1px">' + ic('chev') + '</span></span>'
      + '<span class="det-date num">' + (r.bills || 0) + ' 笔</span></div>'
      + '<div class="det-row num"><b style="font-size:15px;color:var(--tx1)">' + moneyFull(r.amount) + '</b>'
      + ' <span style="font-size:11px;color:var(--tx3)">销售净额</span></div>'
      + '</div>'
      + '<div class="cd-det" data-p="' + esc(name) + '" data-c="' + esc(r.channel) + '"></div>';
  });
  h += '</div>';
  return h;
}

/* 二级下钻：渠道 → 单品明细（DATA.qudao.channelItems[员工][渠道]，含毛利/成本/原价/毛利率）
   渲染样式与「品类达成明细」一致：商品名+日期 顶行，原价/折扣/毛利/毛利率/成本 数值行。
   点日期可展开该单的 LS 单号（不占地方）。 */
function channelDetailHTML(person, channel){
  const map = (DATA.qudao && DATA.qudao.channelItems) || {};
  const items = (map[person] || {})[channel] || [];
  if(!items.length) return '<div class="det-empty">该渠道本期无单品明细</div>';
  let h = '<div class="det-list">';
  items.forEach((r, i) => {
    const neg = (r.amount || 0) < 0;
    h += '<div class="det-item' + (neg ? ' neg' : '') + '">'
      + '<div class="det-top"><span class="det-name">' + esc(r.product || r.sku || '—') + '</span>'
      + '<span class="det-date num cd-date-click" onclick="toggleCode(\'' + esc(person) + '\',\'' + esc(channel) + '\',' + i + ')">' + esc(r.date || '—') + '</span></div>'
      + '<div class="det-row num">'
      + '<span class="dv-origin">原价: <b>' + (r.origPrice == null ? '—' : fmtNum(r.origPrice)) + '</b></span>'
      + (r.discPrice && parseFloat(r.discPrice) ? '<span class="dv-disc">折扣: <b>' + fmtNum(r.discPrice) + '</b></span>' : '')
      + '<span class="dv-profit">毛利: <b>' + (r.profit == null ? '—' : fmtNum(r.profit)) + '</b></span>'
      + '<span class="dv-gpr">毛利率: <b>' + (r.gpr == null ? '—' : (r.gpr * 100).toFixed(1) + '%') + '</b></span>'
      + '<span class="dv-cost">成本: <b>' + (r.cost == null ? '—' : fmtNum(r.cost)) + '</b></span>'
      + '</div>'
      + '<div class="code-det" data-p="' + esc(person) + '" data-c="' + esc(channel) + '" data-i="' + i + '"></div>'
      + '</div>';
  });
  h += '</div>';
  return h;
}

/* 展开内容：单号 / 会员姓名 / 电话（点日期展示，不占地方） */
function codeInfoHTML(it){
  let h = '<div class="code-line">单号 ' + esc((it && it.code) || '—') + '</div>';
  if(it && (it.member || it.phone)){
    h += '<div class="code-line">会员 ' + esc(it.member || '—')
       + (it.phone ? ' · ' + esc(it.phone) : '') + '</div>';
  }
  return h;
}

function toggleCodeBox(sel, it){
  const det = document.querySelector(sel);
  if(!det) return;
  const open = det.classList.contains('open');
  document.querySelectorAll('.code-det.open,.cdet-det.open,.ddet-det.open').forEach(x => {
    if(x !== det){ x.classList.remove('open'); x.innerHTML = ''; }
  });
  if(open){ det.classList.remove('open'); det.innerHTML = ''; return; }
  det.innerHTML = codeInfoHTML(it);
  det.classList.add('open');
}

/* 点日期展开：渠道单品明细（同渠道只展开一条） */
function toggleCode(person, channel, i){
  const map = (DATA.qudao && DATA.qudao.channelItems) || {};
  const items = (map[person] || {})[channel] || [];
  toggleCodeBox('.code-det[data-p="' + esc(person) + '"][data-c="' + esc(channel) + '"][data-i="' + i + '"]', items[i]);
}

/* 点日期展开：品类达成明细（同品类只展开一条） */
function toggleDetCode(cat, i, person){
  let rows = (DATA.details && DATA.details[cat]) || [];
  if(person) rows = rows.filter(r => r.emp === person);
  const psel = person ? '[data-person="' + esc(person) + '"]' : ':not([data-person])';
  toggleCodeBox('.cdet-det[data-cat="' + esc(cat) + '"][data-i="' + i + '"]' + psel, rows[i]);
}

/* 今日明细：点品类行展开该品类当天明细（每项点日期看单号） */
function dayCatHTML(cat, items){
  let h = '<div class="det-list" style="margin-left:10px">';
  items.forEach((it, i) => {
    const neg = (it.amount || 0) < 0;
    h += '<div class="det-item cd-click' + (neg ? ' neg' : '') + '" onclick="toggleDayCode(\'' + esc(cat) + '\',' + i + ')">'
      + '<div class="det-top"><span class="det-name">' + esc(it.product || '—') + '</span>'
      + '<span class="det-date num">' + esc(it.emp || '—') + ' · ' + (it.qty || 0) + '件</span></div>'
      + '<div class="det-row num">'
      + '<span class="dv-profit">金额: <b>' + fmtNum(it.amount) + '</b></span>'
      + '<span class="dv-profit">毛利: <b>' + fmtNum(it.profit) + '</b></span>'
      + '<span class="dv-gpr">毛利率: <b>' + (it.gpr == null ? '—' : (it.gpr * 100).toFixed(1) + '%') + '</b></span>'
      + '<span class="dv-cost">成本: <b>' + fmtNum(it.cost) + '</b></span>'
      + '</div>'
      + '<div class="ddet-det" data-cat="' + esc(cat) + '" data-i="' + i + '"></div>'
      + '</div>';
  });
  h += '</div>';
  return h;
}

function toggleDayCat(cat){
  const det = document.querySelector('.dcdet-det[data-cat="' + esc(cat) + '"]');
  if(!det) return;
  const open = det.classList.contains('open');
  document.querySelectorAll('.dcdet-det.open').forEach(x => { if(x !== det){ x.classList.remove('open'); x.innerHTML = ''; }});
  if(open){ det.classList.remove('open'); det.innerHTML = ''; return; }
  const items = dayMetricItems(cat);
  det.innerHTML = (items && items.length) ? dayCatHTML(cat, items) : '<div class="det-empty">该品类今日暂无明细</div>';
  det.classList.add('open');
}

/* 今日明细：点单项展开出库单号（cat=品类内索引） */
function toggleDayCode(cat, i){
  const items = (DATA.dayDetails || []).filter(r => (r.cat || '其他') === cat);
  toggleCodeBox('.ddet-det[data-cat="' + esc(cat) + '"][data-i="' + i + '"]', items[i]);
}

function toggleChannel(person, channel){
  const det = document.querySelector('.cd-det[data-p="' + person + '"][data-c="' + channel + '"]');
  if(!det) return;
  const open = det.classList.contains('open');
  document.querySelectorAll('.cd-det.open').forEach(d => { if(d !== det){ d.classList.remove('open'); d.innerHTML = ''; }});
  if(open){ det.classList.remove('open'); det.innerHTML = ''; return; }
  det.innerHTML = channelDetailHTML(person, channel);
  det.classList.add('open');
}

function togglePerson(name){
  const det = document.querySelector('.pp-det[data-person="' + name + '"]');
  if(!det) return;
  const rc  = document.querySelector('.pp-click[data-person="' + name + '"]');
  const open = det.classList.contains('open');
  // 逐层展开：关掉其它已展开项，保持界面干净
  document.querySelectorAll('.pp-det.open').forEach(d => { if(d !== det){ d.classList.remove('open'); d.innerHTML = ''; }});
  document.querySelectorAll('.pp-click.on').forEach(d => { if(d !== rc) d.classList.remove('on'); });
  if(open){ det.classList.remove('open'); det.innerHTML = ''; if(rc) rc.classList.remove('on'); return; }
  det.innerHTML = personDetailHTML(name);
  det.classList.add('open');
  if(rc) rc.classList.add('on');
}

/* 环形进度 */
function ringSVG(rate, s, size){
  const r = (size - 16) / 2, c = 2 * Math.PI * r;
  const w = isNum(rate) ? Math.min(rate, 1) : 0;
  const off = c * (1 - w);
  const col = {done:'#22c55e', over:'#7c3aed', on:'#f59e0b', low:'#ef4444', na:'#9aa0bd'}[s] || '#9aa0bd';
  return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">'
    + '<circle cx="' + (size/2) + '" cy="' + (size/2) + '" r="' + r + '" fill="none" stroke="rgba(30,28,60,.07)" stroke-width="10"/>'
    + '<circle cx="' + (size/2) + '" cy="' + (size/2) + '" r="' + r + '" fill="none" stroke="' + col + '" stroke-width="10" stroke-linecap="round"'
    + ' stroke-dasharray="' + c.toFixed(1) + '" stroke-dashoffset="' + off.toFixed(1) + '"'
    + ' transform="rotate(-90 ' + (size/2) + ' ' + (size/2) + ')" style="transition:stroke-dashoffset 1s cubic-bezier(.22,1,.36,1)"/>'
    + '</svg>';
}

/* ============ 今日图表：Donut(毛利占比) + Bar(增值排行) ============ */
const CHART_PALETTE = ['#6366f1','#22c55e','#06b6d4','#eab308','#f43f5e','#a855f7','#14b8a6','#fb923c'];

/* Donut 环形图：items=[{label,value,color}], size=直径。返回 SVG 字符串。
   中心数字与标签由调用方在外层 HTML 叠加（更灵活）。 */
function donutSVG(items, size){
  const total = items.reduce((s,it) => s + (isNum(it.value) ? it.value : 0), 0);
  if(!total) return '<div style="width:' + size + 'px;height:' + size + 'px;display:flex;align-items:center;justify-content:center;color:var(--tx3);font-size:12px">暂无数据</div>';
  const cx = size / 2, cy = size / 2;
  const r = (size / 2) - 14;
  const c = 2 * Math.PI * r;
  let acc = 0, parts = '';
  items.forEach((it) => {
    const v = isNum(it.value) ? it.value : 0;
    if(!v) return;
    const frac = v / total;
    const dash = (frac * c).toFixed(2);
    const gap  = (c - parseFloat(dash)).toFixed(2);
    const off  = (-acc * c).toFixed(2);
    parts += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + it.color + '" stroke-width="18"'
          + ' stroke-dasharray="' + dash + ' ' + gap + '" stroke-dashoffset="' + off + '"'
          + ' transform="rotate(-90 ' + cx + ' ' + cy + ')" style="transition:stroke-dasharray .8s cubic-bezier(.22,1,.36,1)"/>';
    acc += frac;
  });
  return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">'
    + parts + '</svg>';
}

/* 横向条形排行：items=[{label,value}] 已降序。maxV 不传时自动取 items 中最大值。返回 HTML 字符串。 */
function hbarSVG(items, maxV){
  if(!maxV) maxV = items.reduce((m,it) => Math.max(m, isNum(it.value) ? it.value : 0), 1);
  const mv = Math.max(maxV, 1);
  let h = '';
  items.forEach((it, i) => {
    const v = isNum(it.value) ? it.value : 0;
    const w = v > 0 ? Math.max(v / mv * 100, 4) : 0;
    const col = CHART_PALETTE[i % CHART_PALETTE.length];
    const valTxt = v > 0 ? moneyShort(v) : '0';
    h += '<div class="hb-row">'
       +   '<span class="hb-name">' + esc(it.label) + '</span>'
       +   '<span class="hb-track"><span class="hb-fill" style="width:' + w.toFixed(1) + '%;background:' + col + '"></span></span>'
       +   '<span class="hb-v num">' + valTxt + '</span>'
       + '</div>';
  });
  return h;
}

/* 内联 SVG 图标库（无 emoji、无外部资源） */
const ICONS = {
  store:'<path d="M3 9l9-6 9 6v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 21V12h6v9"/>',
  rank:'<path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0z"/><path d="M7 4H4v2a3 3 0 0 0 3 3M17 4h3v2a3 3 0 0 1-3 3"/>',
  person:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  day:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/>',
  insight:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>',
  qudao:'<path d="M3 10l9-6 9 6M4 10v9h16v-9M9 19v-5h6v5"/>',
  warn:'<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
  fire:'<path d="M12 3s5 4 5 9a5 5 0 0 1-10 0c0-2 1-3 1-3s.5 2 2 2c0-3 2-5 2-8z"/>',
  spark:'<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
  chev:'<path d="M9 6l6 6-6 6"/>'
};
function ic(name, size){
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    + (size ? ' style="width:'+size+'px;height:'+size+'px"' : '') + '>' + (ICONS[name] || '') + '</svg>';
}
function warnIcon(){ return ic('warn'); }

/* 彩带动效（纯 DOM，无 canvas，无外部库） */
function confetti(n){
  n = n || 110;
  const box = document.createElement('div');
  box.className = 'confetti';
  const cols = ['#7c3aed','#a855f7','#22c55e','#ef4444','#f59e0b','#6366f1'];
  for(let i = 0; i < n; i++){
    const s = document.createElement('i');
    s.style.left = (Math.random() * 100) + '%';
    s.style.background = cols[i % cols.length];
    s.style.setProperty('--x', (Math.random() * 220 - 110) + 'px');
    s.style.setProperty('--r', (Math.random() * 720 - 360) + 'deg');
    s.style.animationDelay = (Math.random() * 0.4) + 's';
    s.style.transform = 'rotate(' + (Math.random() * 360) + 'deg)';
    box.appendChild(s);
  }
  document.body.appendChild(box);
  setTimeout(() => box.remove(), 3000);
}

function heroRow(label, k){
  const s = hasTask(k) ? stat(k.rate) : 'na';
  const col = {done:'var(--green)', over:'var(--purple)', on:'var(--amber)', low:'var(--red)', na:'var(--gray)'}[s];
  return '<div class="hero-row"><span>' + esc(label) + '</span>'
       + '<b class="num" style="color:' + col + '">' + pct(k && k.rate, 1) + '</b></div>';
}

function storeHero(P, Q){
  const zeng = Q['增值'] || {};
  const s = hasTask(zeng) ? stat(zeng.rate) : 'na';
  let h = '<div class="sec"><div class="hero">';
  h += '<div class="ring">' + ringSVG(zeng.rate, s, 100)
     + '<div class="ring-c"><b class="num">' + pct(zeng.rate, 0) + '</b><span>增值达成</span></div></div>';
  h += '<div class="hero-r">'
     + '<div class="hero-t">整体进度一览</div>'
     + heroRow('销售额', P['销额'])
     + heroRow('毛利', P['毛利'])
     + heroRow('手机', P['手机'])
     + heroRow('增值', Q['增值'])
     + '<div class="hero-tp">时间进度 <b class="num">' + pct(DATA.meta.timeProgress, 1) + '</b></div>'
     + '</div>';
  h += '</div></div>';
  return h;
}

function catChartHTML(P){
  const cats = CATS.concat(['增值']);
  const tp = DATA.meta.timeProgress;
  const tpPct = isNum(tp) ? Math.min(tp, 1) * 100 : 0;
  let bars = '';
  cats.forEach(c => {
    // 增值在 DATA.store.qcs（不在 performance），同 kpiCard('增值', Q['增值'])
    const k = (c === '增值') ? (DATA.store.qcs && DATA.store.qcs['增值']) : P[c];
    const rate = (k && isNum(k.rate)) ? Math.min(k.rate, 1) : 0;
    const s = k && hasTask(k) ? stat(k.rate) : 'na';
    const col = {done:'var(--green)', over:'var(--purple)', on:'var(--amber)', low:'var(--red)', na:'var(--gray)'}[s];
    bars += '<div class="mc-b" data-cat="' + esc(c) + '"><div class="mc-track">'
          + '<div class="mc-f" style="height:' + (rate*100).toFixed(0) + '%;background:' + col + '"></div>'
          + (tpPct > 0 ? '<div class="mc-mk" style="bottom:' + tpPct.toFixed(0) + '%"></div>' : '')
          + '</div><span class="mc-l">' + esc(c) + '</span></div>';
  });
  return '<div class="mc"><div class="mc-bars">' + bars + '</div>'
       + '<div class="mc-leg"><span class="mc-dot"></span>紫线 = 时间进度 ' + pct(tp, 0) + '</div></div>';
}

/* ---------------- 板块视图：销售 / 运营 ---------------- */
/* 销售看板「门店」视图：沿用上一版主板口径（增值达成 hero + 核心指标 + 品类 + 考核机型 + 全科生 + 绩效） */
/* 运营看板「渠道」视图：仅渠道挂账（含逐人进度），见 renderQudao() */

/* 销售看板：沿用上一版主板口径 */
function renderSales(){
  const P = DATA.store.performance || {};
  const Q = DATA.store.qcs || {};
  let h = '<div class="wrap">';

  /* 总览 hero（增值达成，沿用上一版口径） */
  h += storeHero(P, Q);

  /* 核心 KPI */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>核心指标</b>'
     + '<span class="tail">时间进度 ' + pct(DATA.meta.timeProgress,1) + '</span></div>';
  h += '<div class="kpi-grid">';
  h += kpiCard('毛利', P['毛利'], '毛利');
  h += kpiCard('销售额', P['销额'], '销额');
  h += kpiCard('增值', Q['增值'], '增值');
  h += kpiCard('手机', P['手机'], '手机');
  h += '</div></div>';

  /* 品类速览（柱状图） + 品类达成 → 桌面并排 */
  h += '<div class="cols">';
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>品类速览</b>'
     + '<span class="tail">柱高 = 达成率</span></div>' + catChartHTML(P) + '</div>';
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>品类达成</b>'
     + '<span class="tail">点品类行展开明细</span></div><div class="rows">';
  CATS.forEach(c => { h += catRow(c, P[c], c); });
  h += catRow('增值', Q['增值'], '增值');
  h += '</div></div>';
  h += '</div>'; /* /cols */

  /* 考核机型 + 全科生（运营服务） → 桌面并排 */
  h += '<div class="cols">';
  h += assessHTML(Q['考核机型'], DATA.meta.employees);
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>全科生</b></div>';
  h += qcsHTML(Q);
  h += '</div>';
  h += '</div>'; /* /cols */

  /* 绩效 */
  if(isNum(P['绩效'])){
    h += '<div class="sec"><div class="card" style="padding:14px;text-align:center">'
       + '<div style="font-size:11px;color:var(--tx3)">门店综合绩效得分</div>'
       + '<div style="font-size:30px;font-weight:800;margin-top:4px;letter-spacing:-1px" class="num">'
       + P['绩效'].toFixed(2) + '</div></div></div>';
  }

  h += '</div>';
  return h;
}

/* 运营看板「渠道」视图：仅渠道挂账（含逐人进度） */
/* 由 renderQudao() 提供（见下），运营板块后续可追加其他运营 tab */

/* 销售看板「门店」视图（含页脚） */
function renderStore(){
  return renderSales() + foot();
}

/* 考核机型 —— 独立板块
   names 传入姓名数组则逐人列出；不传只显示单条 */
function assessHTML(kh, names){
  if(!kh) return '';
  const gc = v => (isNum(v) && v < 0) ? 'var(--red)' : 'var(--green)';
  let h = '<div class="sec"><div class="sec-h"><span class="bar"></span><b>考核机型</b>'
        + '<span class="tail">未完成 −100/台</span></div>';
  h += '<div class="card" style="padding:13px 14px">';

  h += '<div style="display:flex;align-items:baseline;gap:7px;flex-wrap:wrap">'
     + '<span style="font-size:11.5px;color:var(--tx3)">' + (names ? '门店任务' : '任务') + '</span>'
     + '<b class="num" style="font-size:24px;letter-spacing:-.5px">' + cnt(kh.task) + '</b>'
     + '<span style="font-size:11.5px;color:var(--tx3)">台</span>'
     + '<span style="flex:1"></span>'
     + '<span style="font-size:11.5px;color:var(--tx3)">缺口</span>'
     + '<b class="num" style="font-size:20px;color:' + gc(kh.gap) + '">' + cnt(kh.gap) + '</b>'
     + '</div>';

  if(names && names.length){
    h += '<div style="margin-top:11px;border-top:1px solid var(--line);padding-top:4px">';
    names.forEach(n => {
      const p = DATA.people[n];
      const k = p && p.qcs && p.qcs['考核机型'];
      if(!k) return;
      const noTask = !isNum(k.task) || k.task === 0;
      h += '<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--line)">'
         + '<span style="flex:1;font-size:13px;font-weight:600">' + esc(n) + '</span>'
         + '<span class="num" style="font-size:12.5px;color:var(--tx2)">任务 '
         + (noTask ? '<em style="color:var(--tx3);font-style:normal">—</em>' : cnt(k.task)) + '</span>'
         + '<span class="num" style="font-size:13px;font-weight:700;min-width:42px;text-align:right;color:'
         + (noTask ? 'var(--tx3)' : gc(k.gap)) + '">' + (noTask ? '—' : cnt(k.gap)) + '</span>'
         + '</div>';
    });
    h += '</div>';
  }

  h += '</div></div>';
  return h;
}

/* QCS 卡片组 */
function qcsHTML(Q){
  if(!Q) return '<div class="empty">暂无数据</div>';
  let h = '<div class="q-grid">';

  const dx = Q['电信积分'];
  if(dx){
    const s = hasTask(dx) ? stat(dx.rate) : 'na';
    h += '<div class="q"><div class="q-l">电信积分（5分）</div>'
      + '<div class="q-v num">' + cnt(dx.done) + '<small>/ ' + cnt(dx.task) + '</small></div>'
      + '<div class="q-s">达成 <em class="r-' + s + '" style="padding:1px 4px;border-radius:4px">' + pct(dx.rate,0) + '</em></div></div>';
  }

  const hy = Q['会员搭售率'];
  if(hy){
    h += '<div class="q"><div class="q-l">会员搭售率（30%）</div>'
      + '<div class="q-v num">' + pct(hy.rate,1) + '</div>'
      + '<div class="q-s">Care+ ' + cnt(hy.care) + ' / 终端 ' + cnt(hy.terminal)
      + (isNum(hy.gap) ? ' · 缺 <em style="color:' + (hy.gap<0?'var(--red)':'var(--green)') + '">' + cnt(hy.gap) + '</em>' : '')
      + '</div></div>';
  }

  const hs = Q['回收搭售率'];
  if(hs){
    h += '<div class="q"><div class="q-l">回收搭售率（20%）</div>'
      + '<div class="q-v num">' + pct(hs.rate,1) + '</div>'
      + '<div class="q-s">单数 ' + cnt(hs.orders)
      + (isNum(hs.gap) ? ' · 缺 <em style="color:' + (hs.gap<0?'var(--red)':'var(--green)') + '">' + cnt(hs.gap) + '</em>' : '')
      + '</div></div>';
  }

  const tm = Q['贴膜率'];
  if(tm){
    h += '<div class="q"><div class="q-l">贴膜率（50%）</div>'
      + '<div class="q-v num">' + pct(tm.rate,1) + '</div>'
      + '<div class="q-s">单数 ' + cnt(tm.orders)
      + (isNum(tm.gap) ? ' · 缺 <em style="color:' + (tm.gap<0?'var(--red)':'var(--green)') + '">' + cnt(tm.gap) + '</em>' : '')
      + '</div></div>';
  }

  /* 回收业务：乐回收(《李家村销售》T14:U18 直读) + 太力回收 合并为单卡两行 */
  const lh = Q['乐回收'];
  const th = Q['太力回收'];
  if(lh || th){
    let _rows = '';
    if(lh){
      _rows += '<div class="q-s">乐回收 <b class="num">' + cnt(lh.orders)
            + '</b> 单 · 公司净利 ' + money(lh.amount) + '</div>';
    }
    if(th){
      _rows += '<div class="q-s">太力回收 <b class="num">' + cnt(th.orders)
            + '</b> 单 · ' + money(th.amount)
            + (isNum(th['增值']) ? ' · 增值 ' + money(th['增值']) : '') + '</div>';
    }
    h += '<div class="q wide">'
      + '<div class="q-l">回收业务</div>'
      + '<div class="rec-list">' + _rows + '</div></div>';
  }

  const xl = Q['星联会员'];
  if(xl){
    h += '<div class="q"><div class="q-l">星联会员</div>'
      + '<div class="q-v num">' + cnt(xl['合计']) + '</div>'
      + '<div class="q-s">优享 ' + cnt(xl['优享']) + ' · 尊享 ' + cnt(xl['尊享']) + '</div></div>';
  }

  const jk = Q['健康度'];
  if(jk){
    h += '<div class="q"><div class="q-l">健康度</div>'
      + '<div class="q-v num">' + pct(jk.grossMargin,1) + '<small>毛利率</small></div>'
      + '<div class="q-s">券 ' + moneyShort(jk.coupon) + ' · 占比 ' + pct(jk.ratio,0)
      + '<br>增值率 ' + pct(jk['增值率'],1) + '</div></div>';
  }

  h += '</div>';
  return h;
}

/* ---------------- 渠道挂账（运营板内复用） ---------------- */
function qudaoSections(){
  const Q = DATA.qudao;
  if(!Q) return '<div class="sec"><div class="card" style="padding:20px;text-align:center;color:var(--tx3)">暂无渠道挂账数据</div></div>';
  const t = Q.total || {};
  const tp = Q.timeRate;
  const s = isNum(t.rate) ? stat(t.rate) : 'na';
  let h = '';

  /* 汇总卡 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>渠道挂账</b>'
     + '<span class="tail">时间进度 ' + pct(tp,1) + '</span></div>';
  h += '<div class="card" style="padding:15px">';
  h += '<div style="display:flex;align-items:baseline;gap:8px">'
     + '<b class="num" style="font-size:28px;font-weight:800;letter-spacing:-.5px">' + moneyFull(t.done) + '</b>'
     + '<span style="font-size:12px;color:var(--tx3)">/ ' + moneyFull(t.task) + ' 目标</span>'
     + '<span style="flex:1"></span>'
     + '<span class="r-' + s + '" style="font-size:13px;font-weight:800;padding:3px 9px;border-radius:8px">' + pct(t.rate,1) + '</span>'
     + '</div>';
  h += '<div class="kpi-bar" style="margin-top:12px"><i class="f-' + s + '" style="width:'
     + (isNum(t.rate) ? Math.min(t.rate,1)*100 : 0).toFixed(1) + '%"></i></div>';
  const lag = isNum(t.rate) && isNum(tp) && t.rate < tp;
  h += '<div style="margin-top:10px;font-size:11.5px;color:var(--tx3);line-height:1.6">'
     + '数据日期 ' + esc(Q.timeDate || '—') + ' · 已过 ' + pct(tp,1)
     + (lag ? ' <span style="color:#b45309;font-weight:700;display:inline-flex;align-items:center;gap:3px">'
              + ic('warn',13) + ' 进度落后</span>'
            : ' <span style="color:#15803d;font-weight:700">跟上节奏</span>')
     + '</div>';
  h += '</div></div>';

  /* 逐人（渠道挂账口径：含全部业务类型；点击行下钻渠道明细） */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>逐人进度</b>'
     + '<span class="tail">点击行下钻渠道明细</span></div><div class="rows">';
  (Q.people || []).forEach(p => {
    const has = isNum(p.task) && p.task !== 0;
    const ps = has ? stat(p.rate) : 'na';
    const crit = has && isCritical(p.rate);
    h += '<div class="row pp-click' + (crit ? ' warn' : '') + '" data-person="' + esc(p.name) + '" onclick="togglePerson(\'' + esc(p.name) + '\')">'
      + '<div class="row-t">'
        + '<span class="row-n">' + esc(p.name) + '</span>'
        + '<span class="row-p r-' + ps + '">' + (has ? pct(p.rate,0) : '无任务') + '</span>'
        + '<span class="row-v num"><b>' + moneyFull(p.done) + '</b>' + (has ? ' / ' + moneyFull(p.task) : '') + '</span>'
        + '<span class="chev">' + ic('chev') + '</span>'
      + '</div>'
      + barHTML(p.rate, ps)
      + (has ? gapHintHTML(ps, p.gap, moneyFull) : '')
      + '</div>'
      + '<div class="pp-det" data-person="' + esc(p.name) + '"></div>';
  });
  h += '</div></div>';
  return h;
}
function renderQudao(){
  if(!DATA.qudao) return '<div class="wrap"><div class="empty">暂无渠道挂账数据</div></div>';
  return '<div class="wrap">' + qudaoSections() + foot() + '</div>';
}

/* ---------------- 动效：点击水波纹（一次性委托，避免每次 render 重绑） ---------------- */
(function(){
  var RP_SEL = '.kpi,.rk,.day,.tab,.chip,.row.cat-click,.pp-click,.cd-click,.mc-b[data-cat]';
  document.addEventListener('click', function(e){
    var t = e.target && e.target.closest ? e.target.closest(RP_SEL) : null;
    if(!t) return;
    var rect = t.getBoundingClientRect();
    var size = Math.max(rect.width, rect.height, 40);
    var r = document.createElement('span');
    r.className = 'rp-ring';
    r.style.width = r.style.height = size + 'px';
    r.style.left = (e.clientX - rect.left - size / 2) + 'px';
    r.style.top  = (e.clientY - rect.top  - size / 2) + 'px';
    t.appendChild(r);
    setTimeout(function(){ if(r.parentNode) r.parentNode.removeChild(r); }, 600);
  });
})();

/* 今日明细：点击展开某指标/品类的当天逐单明细（供今日品类行下钻调用） */
function dayMetricItems(k){
  const dd = DATA.dayDetails || [];
  const CATS = { '手机':['手机'],'PC':['PC'],'平板':['平板'],'穿戴':['穿戴'],'音频':['音频'],
                 'HD':['HD'],'智慧办公':['PC','平板'],'音频穿戴':['穿戴','音频'],'增值':['增值'] };
  if(CATS[k]) return dd.filter(r => CATS[k].indexOf(r.cat) !== -1);
  if(k === '毛利' || k === '销额') return dd.slice();
  if(k === '滞销'){
    const khj = ["01.001.010.00","01.001.011.002","01.001.012.00","01.001.013.0","01.001.031.002",
                 "01.001.032.002","01.001.043.002","01.001.044.002","01.001.001.0","01.001.002.0","01.001.003"];
    return dd.filter(r => khj.some(p => r.sku.indexOf(p) === 0));
  }
  const rx = { '贴膜':/膜|套包/, '回收':/回收/, '会员':/Care|会员|星联优享/,
               '电信积分':/入网/, '摄影课':/大师课/ }[k];
  if(rx) return dd.filter(r => ((k === '贴膜' || k === '摄影课') ? (r.amount > 0 && rx.test(r.product)) : rx.test(r.product)));
  return null;
}

function dayMetricHTML(k, items){
  let h = '<div class="det-list">';
  items.forEach((it, i) => {
    const neg = (it.amount || 0) < 0;
    h += '<div class="det-item' + (neg ? ' neg' : '') + '">'
      + '<div class="det-top"><span class="det-name">' + esc(it.product || '—') + '</span>'
      + '<span class="det-date num">' + esc(it.emp || '—') + ' · ' + (it.qty || 0) + '件</span></div>'
      + '<div class="det-row num">'
      + '<span class="dv-profit">金额: <b>' + fmtNum(it.amount) + '</b></span>'
      + '<span class="dv-profit">毛利: <b>' + fmtNum(it.profit) + '</b></span>'
      + '<span class="dv-gpr">毛利率: <b>' + (it.gpr == null ? '—' : (it.gpr * 100).toFixed(1) + '%') + '</b></span>'
      + '<span class="dv-cost">成本: <b>' + fmtNum(it.cost) + '</b></span>'
      + '</div></div>';
  });
  h += '</div>';
  return '<div class="sec-h" style="margin-top:10px"><span class="bar"></span><b>' + esc(k) + ' · 当天明细</b>'
       + '<span class="tail">' + items.length + ' 行</span></div>' + h;
}

function clickDayMetric(k){
  const det = document.querySelector('.day-det');
  if(!det) return;
  const items = dayMetricItems(k);
  if(!items || !items.length){
    toast('今日「' + k + '」暂无逐单明细');
    return;
  }
  det.innerHTML = dayMetricHTML(k, items);
  det.scrollIntoView({behavior:'smooth', block:'nearest'});
  det.classList.add('open');
}
