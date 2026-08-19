
/* ---------------- 视图 2：排行 ---------------- */
const RANK_DIMS = [
  {k:'毛利',   src:'performance'},
  {k:'销额',   src:'performance', label:'销售额'},
  {k:'手机',   src:'performance'},
  {k:'音频穿戴', src:'performance'},
  {k:'穿戴',   src:'performance'},
  {k:'增值',   src:'qcs'},
  {k:'电信积分', src:'qcs'},
];

function renderRank(){
  const dim = RANK_DIMS.find(d => d.k === RANK_BY) || RANK_DIMS[0];
  const list = DATA.meta.employees.map(n => {
    const p = DATA.people[n] || {};
    const k = ((p[dim.src] || {})[dim.k]) || null;
    return { name:n, k:k, done: (k && isNum(k.done)) ? k.done : -Infinity,
             rate:(k && isNum(k.rate)) ? k.rate : null, has: hasTask(k) };
  });
  // 排序：有任务的按达成率，没任务的按完成量垫底
  list.sort((a,b) => {
    if(a.has !== b.has) return a.has ? -1 : 1;
    if(a.has) return (b.rate||0) - (a.rate||0);
    return b.done - a.done;
  });

  let h = '<div class="wrap">';
  h += '<div class="chips">';
  RANK_DIMS.forEach(d => {
    h += '<div class="chip' + (d.k === RANK_BY ? ' on' : '') + '" data-dim="' + d.k + '">'
       + esc(d.label || d.k) + '</div>';
  });
  h += '</div>';

  h += '<div class="sec-h"><span class="bar"></span><b>' + esc(dim.label||dim.k) + ' 排行</b>'
     + '<span class="tail">共 ' + list.length + ' 人</span></div>';

  h += '<div class="cols">';
  list.forEach((it, i) => {
    const s = it.has ? stat(it.rate) : 'na';
    const colorVar = {done:'--green',over:'--purple',on:'--amber',low:'--red',na:'--gray'}[s];
    const w = it.has && isNum(it.rate) ? Math.min(it.rate,1)*100 : 0;
    h += '<div class="rk" data-person="' + esc(it.name) + '">'
      + '<div class="rk-bg" style="width:' + w.toFixed(1) + '%;background:var(' + colorVar + ')"></div>'
      + '<div class="rk-no' + (it.has && i<3 ? ' n'+(i+1) : '') + '">' + (it.has ? (i+1) : '—') + '</div>'
      + '<div class="rk-m">'
        + '<div class="rk-n">' + esc(it.name) + '</div>'
        + '<div class="rk-sub num">' + fmtU(it.k ? it.k.done : null, unitOf(dim.k, it.k))
        + (it.has ? ' / ' + fmtU(it.k.task, unitOf(dim.k, it.k)) : ' · 未分配任务') + '</div>'
      + '</div>'
      + '<div class="rk-r">'
        + '<div class="p num" style="color:var(' + colorVar + ')">' + (it.has ? pct(it.rate,0) : '—') + '</div>'
        + '<div class="g">' + (it.has && it.k && isNum(it.k.gap)
            ? (it.k.gap < 0 ? '差 ' + fmtU(Math.abs(it.k.gap), unitOf(dim.k, it.k))
                            : '超 ' + fmtU(it.k.gap, unitOf(dim.k, it.k)))
            : STAT_TXT[s]) + '</div>'
      + '</div>'
      + '</div>';
  });
  h += '</div>'; /* /cols */

  h += '<div style="font-size:11px;color:var(--tx3);text-align:center;padding:8px 0 2px;line-height:1.7">'
     + '点任意一行查看该员工完整数据</div>';
  h += foot();
  h += '</div>';
  return h;
}

/* ---------------- 视图 3：个人 ---------------- */
function renderPerson(){
  if(!PERSON) PERSON = DATA.meta.employees[0];
  const p = DATA.people[PERSON];
  let h = '<div class="wrap">';

  h += '<div class="chips">';
  DATA.meta.employees.forEach(n => {
    h += '<div class="chip' + (n === PERSON ? ' on' : '') + '" data-p="' + esc(n) + '">' + esc(n) + '</div>';
  });
  h += '</div>';

  if(!p){ return h + '<div class="empty">无此人数据</div></div>'; }

  const P = p.performance || {}, Q = p.qcs || {};
  const noTask = !hasTask(P['毛利']);

  if(noTask){
    h += '<div class="card" style="padding:12px;margin-bottom:14px;'
       + 'border-color:rgba(245,158,11,.3);background:linear-gradient(90deg,var(--amberDim),transparent)">'
       + '<div style="font-size:12px;color:#b45309;font-weight:600;display:flex;align-items:center;gap:5px">' + ic('warn',14) + ' 本月未分配任务</div>'
       + '<div style="font-size:11px;color:var(--tx3);margin-top:4px;line-height:1.6">'
       + '表格中该员工的任务列为空，因此不计算达成率，仅显示已完成的量。</div></div>';
  }

  /* 多栏容器（桌面并排） */
  h += '<div class="cols">';

  /* 核心 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>核心指标</b>'
     + '<span class="tail">' + esc(PERSON) + '</span></div><div class="kpi-grid">';
  h += kpiCard('毛利', P['毛利'], '毛利');
  h += kpiCard('销售额', P['销额'], '销额');
  h += kpiCard('增值', Q['增值'], '增值');
  h += kpiCard('手机', P['手机'], '手机');
  h += '</div></div>';

  /* 品类 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>品类达成</b><span class="tail">点品类行展开明细</span></div><div class="rows">';
  CATS.forEach(c => { h += catRow(c, P[c], c, PERSON); });
  h += catRow('增值', Q['增值'], '增值', PERSON);
  h += '</div></div>';

  h += '</div>'; /* /cols 上半 */

  /* 考核机型（独立板块，整宽） */
  h += assessHTML(Q['考核机型'], null);

  /* 全科生 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>全科生</b></div>';
  h += qcsHTML(Q);
  h += '</div>';

  /* 今日 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>今日达成</b>'
     + '<span class="tail">' + esc(DATA.meta.dayTitle || '') + '</span></div>';
  h += dayHTML(p.dailyDone, p.dailyGap);
  h += '</div>';

  /* 绩效 */
  if(isNum(P['绩效'])){
    h += '<div class="sec"><div class="card" style="padding:14px;text-align:center">'
      + '<div style="font-size:11px;color:var(--tx3)">个人绩效得分</div>'
      + '<div style="font-size:30px;font-weight:800;margin-top:4px;letter-spacing:-1px" class="num">'
      + P['绩效'].toFixed(2) + '</div></div></div>';
  }

  h += foot();
  h += '</div>';
  return h;
}

/* ---------------- 视图 4：今日 ---------------- */
const DAY_ORDER = ['毛利','销额','增值','手机','音频穿戴','智慧办公','HD','会员','回收','贴膜','电信积分','滞销','优享/会员','尊享/储值'];
const GAP_ALIAS = { '会员':'Care+' };

function dayHTML(done, gap){
  done = done || {}; gap = gap || {};
  const keys = DAY_ORDER.filter(k => k in done || (GAP_ALIAS[k] || k) in gap);
  if(!keys.length) return '<div class="empty">暂无今日数据</div>';
  let h = '<div class="day-grid">';
  keys.forEach(k => {
    const dv = done[k];
    const gk = (GAP_ALIAS[k] && (GAP_ALIAS[k] in gap)) ? GAP_ALIAS[k] : k;
    const gv = gap[gk];
    const isM = MONEY_KEYS.has(k);
    const hit = isNum(gv) && gv >= 0;
    const zero = !isNum(dv) || dv === 0;
    let cls = 'day';
    if(hit) cls += ' hit ok'; else if(isNum(gv)) cls += ' miss';
    if(zero) cls += ' zero';
    h += '<div class="' + cls + '" data-metric="' + esc(k) + '" onclick="clickDayMetric(\'' + esc(k) + '\')">'
      + '<div class="day-l">' + esc(k) + '</div>'
      + '<div class="day-v num">' + (isM ? moneyShort(dv) : cnt(dv)) + '</div>'
      + '<div class="day-g num">' + (isNum(gv)
          ? (gv >= 0 ? '达标 +' + (isM ? moneyShort(gv) : cnt(gv))
                     : (isM ? moneyShort(gv) : cnt(gv)))
          : '&nbsp;') + '</div>'
      + '</div>';
  });
  h += '</div>';
  return h;
}

/* 上账时效提示：卖了不等于已上账，但当天一定补齐 */
function postingBanner(){
  const m = DATA.meta || {};
  const t = m.fetchTime ? ('，' + esc(m.fetchTime) + ' 更新') : '';
  if(m.isToday === false && m.lagDays >= 1){
    return '<div class="lag-tip warn">'
      + '<b>今天（' + esc(m.todayLabel || '') + '）还没有上账记录</b>'
      + '<span>下面是 ' + esc(m.date || '') + ' 的数据' + t + '。已卖出但未上账的单不会显示，上完账刷新就有。</span>'
      + '</div>';
  }
  return '<div class="lag-tip">'
    + '<b>数据以「已上账」为准' + t + '</b>'
    + '<span>卖了还没上账的单暂不计入，补账后刷新即可显示。</span>'
    + '</div>';
}

function renderDay(){
  let h = '<div class="wrap">';
  h += postingBanner();

  /* 第1层：全店今日达成 + 今日品类（点品类行下钻当天产品明细） */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>全店今日达成</b>'
     + '<span class="tail">' + esc(DATA.meta.dayTitle || DATA.meta.date) + '</span></div>';
  h += dayHTML(DATA.store.dailyDone, DATA.store.dailyGap);
  h += '<div class="day-det"></div>';
  h += '<div style="font-size:10.5px;color:var(--tx3);padding:9px 2px 0;line-height:1.7">'
     + '大数字＝今天已完成；下方＝距每日任务的差额（负数表示缺口）<br>点上面的模块看当天逐单明细</div>';

  /* 今日品类：点品类行展开该品类当天产品明细（并入第1层） */
  const dd = DATA.dayDetails || [];
  if(dd.length){
    const CAT_ORDER = ['手机','PC','平板','穿戴','音频','HD','智慧办公','音频穿戴','增值','其他'];
    const groups = {};
    dd.forEach(r => { const c = r.cat || '其他'; (groups[c] = groups[c] || []).push(r); });
    h += '<div style="margin-top:12px;border-top:1px dashed var(--line2);padding-top:10px">'
       + '<div class="sec-h"><span class="bar"></span><b>今日品类</b>'
       + '<span class="tail">点品类行下钻当天明细</span></div><div class="rows">';
    CAT_ORDER.forEach(c => {
      const items = groups[c];
      if(!items || !items.length) return;
      const qty = items.reduce((s,r) => s + (r.qty || 0), 0);
      const amt = items.reduce((s,r) => s + (r.amount || 0), 0);
      const pf  = items.reduce((s,r) => s + (r.profit || 0), 0);
      const neg = pf < 0;
      h += '<div class="row pp-click' + (neg ? ' warn' : '') + '" onclick="toggleDayCat(\'' + esc(c) + '\')">'
        + '<div class="row-t">'
          + '<span class="row-n">' + esc(c) + '</span>'
          + '<span class="row-p r-' + (neg ? 'low' : 'good') + '">' + qty + ' 件</span>'
          + '<span class="row-v num"><b>' + moneyFull(amt) + '</b></span>'
          + '<span class="chev">' + ic('chev') + '</span>'
        + '</div>'
        + '<div class="row-g"><span class="' + (neg ? 'stat-low' : '') + '">毛利 ' + moneyFull(pf) + '</span>'
        + '<em style="font-style:normal">毛利率 ' + (amt ? (pf / amt * 100).toFixed(1) + '%' : '—') + '</em></div>'
        + '<div class="dcdet-det" data-cat="' + esc(c) + '"></div>'
        + '</div>';
    });
    h += '</div></div>';
  }
  h += '</div>';

  /* 第2层：每人今日（展示所有销售品类） */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>每人今日</b>'
     + '<span class="tail">全部销售品类</span></div>';
  const DAY_SHOW = ['销额','毛利','手机','PC','平板','穿戴','音频','音频穿戴','智慧办公','HD','增值','会员','回收','贴膜','电信积分','滞销','优享/会员','摄影课','尊享/储值'];
  DATA.meta.employees.forEach(n => {
    const p = DATA.people[n]; if(!p) return;
    const d = p.dailyDone || {};
    const items = DAY_SHOW.filter(k => k in d).map(k => [k, MONEY_KEYS.has(k) ? moneyShort(d[k]) : cnt(d[k])]);
    const allZero = items.every(([k]) => !isNum(d[k]) || d[k] === 0);
    h += '<div class="card" style="padding:11px 12px;margin-bottom:8px'
       + (allZero ? ';border-color:rgba(232,68,58,.22)' : '') + '">'
      + '<div style="display:flex;align-items:center;gap:7px;margin-bottom:7px">'
        + '<b style="font-size:13px">' + esc(n) + '</b>'
        + (allZero ? '<span style="font-size:10px;color:var(--tx3);background:var(--card2);padding:1px 6px;border-radius:5px;font-weight:600">暂无上账</span>' : '')
      + '</div>'
      + '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:5px">';
    items.forEach(([l,v]) => {
      h += '<div style="text-align:center">'
        + '<div style="font-size:10px;color:var(--tx3)">' + l + '</div>'
        + '<div style="font-size:13.5px;font-weight:700;margin-top:2px" class="num">' + v + '</div></div>';
    });
    h += '</div></div>';
  });
  h += '</div>';

  h += foot();
  h += '</div>';
  return h;
}

/* ---------------- 页脚 ---------------- */
function foot(){
  const m = DATA.meta;
  return '<div class="foot">'
    + '数据来源：' + esc(m.sourceFile || '任务进度表') + '<br>'
    + '生成时间 ' + esc(m.generatedAt || '—')
    + '</div>';
}

/* ---------------- 视图 5：店长洞察 ---------------- */
const LV_COLOR = { danger:'--red', warn:'--amber', good:'--green', mid:'--blue', none:'--gray' };
const LV_TAG   = { danger:'急', warn:'追', good:'稳', mid:'跟得上', none:'无任务' };

function renderInsight(){
  const I = DATA.insights;
  if(!I) return '<div class="wrap"><div class="empty">暂无洞察数据，请重新生成看板</div></div>';
  const m = DATA.meta || {};
  const tp = I.timeProgress || 0;
  let h = '<div class="wrap">';

  /* ---- 1. 今日战况 ---- */
  const T = I.today || {sold:[],idle:[]};
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>今日战况</b>'
     + '<span class="tail">' + esc(m.dayTitle || '') + '</span></div>';
  h += '<div class="bt">'
     + '<div class="bt-c"><div class="bt-v num">' + (T.totalOrders||0) + '</div><div class="bt-l">上账笔数</div></div>'
     + '<div class="bt-c"><div class="bt-v num">' + money(T.totalGross||0,0) + '</div><div class="bt-l">今日毛利</div></div>'
     + '<div class="bt-c"><div class="bt-v num" style="color:var('
       + ((T.idle||[]).length ? '--red' : '--green') + ')">'
       + (T.sold||[]).length + '<span style="font-size:12px;color:var(--tx3)">/'
       + ((T.sold||[]).length + (T.idle||[]).length) + '</span></div>'
     + '<div class="bt-l">已开单人数</div></div>'
     + '</div>';

  h += '<div class="who">';
  (T.sold||[]).forEach(s => {
    h += '<div class="who-i on"><span class="n">' + esc(s.name) + '</span>'
       + '<span class="s num">' + s.orders + '单 · ' + money(s.gross,0) + '</span></div>';
  });
  (T.idle||[]).forEach(n => {
    h += '<div class="who-i off"><span class="n">' + esc(n) + '</span>'
       + '<span class="s">暂无上账</span></div>';
  });
  if(!(T.sold||[]).length && !(T.idle||[]).length) h += '<div class="empty">今日暂无数据</div>';
  h += '</div></div>';

  /* ---- 2. 经营建议 ---- */
  const A = I.advices || [];
  if(A.length){
    h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>经营建议</b>'
       + '<span class="tail">' + A.length + ' 条 · 自动诊断</span></div>';
    A.forEach(a => {
      h += '<div class="adv ' + esc(a.level) + '">'
         + '<div class="adv-t"><i>' + esc(a.icon||'') + '</i>' + esc(a.title) + '</div>'
         + '<div class="adv-b">' + esc(a.body) + '</div></div>';
    });
    h += '</div>';
  }

  /* ---- 3. 品类体检 ---- */
  const C = I.categories || [];
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>品类体检</b>'
     + '<span class="tail">时间进度 ' + pct(tp,0) + ' · 剩 ' + (I.remainDays||0) + ' 天</span></div>';
  C.forEach(c => {
    if(!c.task) return;
    const cv = LV_COLOR[c.level] || '--gray';
    const w  = Math.min((c.rate||0)/Math.max(tp,0.01),1)*100;   // 相对时间进度的完成度
    let sub;
    if(c.done <= 0)                sub = '本月零成交';
    else if(c.coldDays === 0)      sub = '今天有成交';
    else if(c.coldDays >= 3)       sub = '已 ' + c.coldDays + ' 天没卖（最后 ' + c.lastDate.slice(5) + '）';
    else                           sub = c.coldDays + ' 天前卖过';
    h += '<div class="ct">'
       + '<div class="ct-bg" style="width:' + w.toFixed(0) + '%;background:var(' + cv + ')"></div>'
       + '<div class="ct-r">'
         + '<div class="ct-n">' + esc(c.name) + '</div>'
         + '<div class="ct-tag" style="background:var(' + cv + ');color:#fff">'
           + esc(LV_TAG[c.level]||'') + '</div>'
         + '<div class="ct-m"><div class="ct-v num" style="color:var(' + cv + ')">'
           + pct(c.rate,0) + '</div>'
         + '<div class="ct-s num">' + cnt(c.done) + '/' + cnt(c.task) + esc(c.unit)
           + ' · 日均需 ' + cnt(c.needPerDay) + '</div></div>'
       + '</div>'
       + '<div class="ct-x">' + esc(sub)
         + (c.zeroPeople && c.zeroPeople.length
             ? ' · 挂零：<b>' + c.zeroPeople.map(esc).join('、') + '</b>' : '')
       + '</div></div>';
  });
  h += '</div>';

  /* ---- 4. 员工体检 ---- */
  const P = I.people || [];
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>员工体检</b>'
     + '<span class="tail">综合进度排名</span></div>';
  P.forEach(p => {
    const cv = LV_COLOR[p.level] || '--gray';
    h += '<div class="pf">'
       + '<div class="pf-r">'
         + '<div class="pf-no' + (p.rank===1?' n1':'') + '">' + p.rank + '</div>'
         + '<div><div class="pf-n">' + esc(p.name) + '</div>'
         + '<div class="pf-kl">综合 <b class="num" style="color:var(' + cv + ')">'
           + pct(p.score,0) + '</b>' + (isNum(p.毛利率) ? ' · 毛利率 ' + pct(p.毛利率,1) : '') + '</div></div>'
         + '<div class="pf-m">'
           + '<div class="pf-k"><div class="pf-kv num">' + pct(p.毛利.rate,0) + '</div><div class="pf-kl">毛利</div></div>'
           + '<div class="pf-k"><div class="pf-kv num">' + pct(p.手机.rate,0) + '</div><div class="pf-kl">手机</div></div>'
           + '<div class="pf-k"><div class="pf-kv num">' + pct(p.增值.rate,0) + '</div><div class="pf-kl">增值</div></div>'
         + '</div>'
       + '</div>';
    if((p.strong||[]).length || (p.weak||[]).length){
      h += '<div class="pf-x">';
      (p.strong||[]).forEach(s => h += '<span class="pf-t g">强 ' + esc(s) + '</span>');
      (p.weak||[]).forEach(s   => h += '<span class="pf-t b">弱 ' + esc(s) + '</span>');
      h += '</div>';
    }
    h += '</div>';
  });
  h += '<div style="font-size:10.5px;color:var(--tx3);text-align:center;padding:6px 0 2px;line-height:1.7">'
     + '综合分 = 毛利 50% + 手机 30% + 增值 20%，与时间进度 ' + pct(tp,0) + ' 对比</div>';
  h += '</div>';

  h += foot();
  h += '</div>';
  return h;
}

/* ---------------- 主渲染 ---------------- */
function render(){
  const m = DATA.meta || {};
  $('#storeName').textContent = m.storeName || '门店看板';
  $('#dataDate').textContent  = (m.date || '')
    + (m.fetchTime ? ' · ' + m.fetchTime + ' 更新' : (m.dayTitle ? ' · ' + m.dayTitle : ''));
  const tp = m.timeProgress;
  $('#tpVal').textContent = isNum(tp) ? pct(tp,1) : '—';
  requestAnimationFrame(() => {
    $('#tpFill').style.width = (isNum(tp) ? Math.min(tp,1)*100 : 0).toFixed(1) + '%';
  });

  const fn = { store:renderStore, rank:renderRank, person:renderPerson,
               day:renderDay, insight:renderInsight, qudao:renderQudao }[VIEW];
  $('#app').innerHTML = fn();
  bindDynamic();
  window.scrollTo(0,0);
}

function bindDynamic(){
  $$('.chip[data-dim]').forEach(c => c.onclick = () => { RANK_BY = c.dataset.dim; render(); });
  $$('.chip[data-p]').forEach(c => c.onclick = () => { PERSON = c.dataset.p; render(); });
  $$('.rk[data-person]').forEach(c => c.onclick = () => {
    PERSON = c.dataset.person; VIEW = 'person';
    $$('.tab').forEach(t => t.classList.toggle('on', t.dataset.v === 'person'));
    render();
  });
  /* 品类达成：点击品类行下钻明细 */
  $$('.cat-click').forEach(c => c.onclick = () => { toggleDetail(c.dataset.cat, c.dataset.person || null); });
  /* KPI 卡片：点击跳转到该指标排行 */
  $$('.kpi[data-kpi]').forEach(c => c.onclick = () => {
    const k = c.dataset.kpi;
    if(!RANK_DIMS.some(d => d.k === k)) return;
    RANK_BY = k; VIEW = 'rank';
    $$('.tab').forEach(t => t.classList.toggle('on', t.dataset.v === 'rank'));
    render();
  });
  /* 品类速览柱：点击展开对应品类达成明细 + 高亮对应行 */
  $$('.mc-b[data-cat]').forEach(c => c.onclick = () => {
    toggleDetail(c.dataset.cat, null);
    const row = $('.cat-click[data-cat="' + c.dataset.cat + '"]:not([data-person])');
    if(row){
      row.scrollIntoView({behavior:'smooth', block:'center'});
      row.classList.add('flash');
      setTimeout(() => row.classList.remove('flash'), 1000);
    }
  });
  /* 点击总览进度环：达成即撒彩带庆祝 */
  const ring = $('.ring');
  if(ring) ring.onclick = () => {
    const P = (DATA.store && DATA.store.performance) || {};
    const sales = P['销额'] || {};
    if(hasTask(sales) && isNum(sales.rate) && sales.rate >= 1){ confetti(); toast('销售额已达成，撒花庆祝'); }
  };
}

$$('.tab').forEach(t => t.onclick = () => {
  $$('.tab').forEach(x => x.classList.remove('on'));
  t.classList.add('on');
  VIEW = t.dataset.v;
  render();
});
