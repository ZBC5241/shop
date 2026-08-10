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
let RANK_BY = '毛利';
let PERSON = null;

/* ---------------- 工具 ---------------- */
const $  = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const isNum = v => typeof v === 'number' && isFinite(v);

function money(v, dec){
  if(!isNum(v)) return '—';
  const d = dec === undefined ? (Math.abs(v) >= 10000 ? 0 : 0) : dec;
  return '¥' + v.toLocaleString('zh-CN', {minimumFractionDigits:d, maximumFractionDigits:d});
}
function moneyShort(v){
  if(!isNum(v)) return '—';
  const a = Math.abs(v);
  if(a >= 10000) return (v/10000).toFixed(1).replace(/\.0$/,'') + '万';
  return Math.round(v).toLocaleString('zh-CN');
}
function cnt(v){ return isNum(v) ? String(Math.round(v)) : '—'; }
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
  if(u === 'wan')  return (v/10000).toFixed(1).replace(/\.0$/,'') + '万';
  return Math.round(v).toLocaleString('zh-CN');
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
  return '<div class="kpi s-' + s + '">'
    + '<div class="kpi-r r-' + s + '">' + rateTxt + '</div>'
    + '<div class="kpi-l">' + esc(label) + '</div>'
    + '<div class="kpi-v num">' + fmtU(k.done, u) + '</div>'
    + '<div class="kpi-s num">任务 ' + (hasTask(k) ? fmtU(k.task, u) : '—')
    + (isNum(k.gap) && hasTask(k) ? ' · 缺 ' + fmtU(Math.abs(k.gap), u) : '') + '</div>'
    + '<div class="kpi-bar"><i class="f-' + s + '" style="width:'
    + (isNum(k.rate) ? Math.min(k.rate,1)*100 : 0).toFixed(1) + '%"></i></div>'
    + '</div>';
}

function catRow(name, k, key){
  if(!k) return '';
  const has = hasTask(k);
  const s   = has ? stat(k.rate) : 'na';
  const crit = has && isCritical(k.rate);
  const u = unitOf(key, k);
  return '<div class="row' + (crit ? ' warn' : '') + '">'
    + '<div class="row-t">'
      + '<span class="row-n">' + esc(name) + '</span>'
      + '<span class="row-p r-' + s + '">' + (has ? pct(k.rate,0) : '无任务') + '</span>'
      + '<span class="row-v num"><b>' + fmtU(k.done, u) + '</b>'
      + (has ? ' / ' + fmtU(k.task, u) : '') + '</span>'
    + '</div>'
    + barHTML(k.rate, s)
    + (has && isNum(k.gap) && k.gap < 0
        ? '<div class="row-g"><span>' + STAT_TXT[s] + '</span><em>还差 ' + fmtU(Math.abs(k.gap), u) + '</em></div>'
        : (has && isNum(k.gap) && k.gap >= 0
            ? '<div class="row-g"><span>' + STAT_TXT[s] + '</span><span style="color:var(--green)">超出 ' + fmtU(k.gap, u) + '</span></div>'
            : ''))
    + '</div>';
}

function renderStore(){
  const P = DATA.store.performance || {};
  const Q = DATA.store.qcs || {};
  let h = '<div class="wrap">';

  /* 核心 KPI */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>核心指标</b>'
     + '<span class="tail">时间进度 ' + pct(DATA.meta.timeProgress,1) + '</span></div>';
  h += '<div class="kpi-grid">';
  h += kpiCard('毛利', P['毛利'], '毛利');
  h += kpiCard('销售额', P['销额'], '销额');
  h += kpiCard('增值', Q['增值'], '增值');
  h += kpiCard('手机', P['手机'], '手机');
  h += '</div></div>';

  /* 品类达成 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>品类达成</b>'
     + '<span class="tail">白线 = 时间进度</span></div><div class="rows">';
  CATS.forEach(c => { h += catRow(c, P[c], c); });
  h += catRow('增值', Q['增值'], '增值');
  h += '</div></div>';

  /* 考核机型（独立板块） */
  h += assessHTML(Q['考核机型'], DATA.meta.employees);

  /* 全科生 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>全科生</b></div>';
  h += qcsHTML(Q);
  h += '</div>';

  /* 绩效 */
  if(isNum(P['绩效'])){
    h += '<div class="sec"><div class="card" style="padding:14px;text-align:center">'
       + '<div style="font-size:11px;color:var(--tx3)">门店综合绩效得分</div>'
       + '<div style="font-size:30px;font-weight:800;margin-top:4px;letter-spacing:-1px" class="num">'
       + P['绩效'].toFixed(2) + '</div></div></div>';
  }

  h += foot();
  h += '</div>';
  return h;
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

  const lh = Q['乐回收'], th = Q['太力回收'];
  if(lh || th){
    h += '<div class="q wide"><div class="q-l">回收业务</div><div class="q-s" style="margin-top:2px;font-size:12px">';
    if(lh) h += '乐回收 <b class="num">' + cnt(lh.orders) + '</b> 单'
              + (isNum(lh.amount) ? ' · ' + money(lh.amount) : '') + '<br>';
    if(th) h += '太力回收 <b class="num">' + cnt(th.orders) + '</b> 单'
              + (isNum(th.amount) ? ' · ' + money(th.amount) : '')
              + (isNum(th['增值']) ? ' · 增值 ' + money(th['增值']) : '');
    h += '</div></div>';
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
