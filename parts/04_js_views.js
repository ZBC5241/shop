
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

  list.forEach((it, i) => {
    const s = it.has ? stat(it.rate) : 'na';
    const colorVar = {done:'--green',over:'--blue',on:'--amber',low:'--red',na:'--gray'}[s];
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
       + 'border-color:rgba(245,158,11,.3);background:linear-gradient(90deg,rgba(245,158,11,.08),var(--card))">'
       + '<div style="font-size:12px;color:var(--amber);font-weight:600">⚠ 本月未分配任务</div>'
       + '<div style="font-size:11px;color:var(--tx3);margin-top:4px;line-height:1.6">'
       + '表格中该员工的任务列为空，因此不计算达成率，仅显示已完成的量。</div></div>';
  }

  /* 核心 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>核心指标</b>'
     + '<span class="tail">' + esc(PERSON) + '</span></div><div class="kpi-grid">';
  h += kpiCard('毛利', P['毛利'], '毛利');
  h += kpiCard('销售额', P['销额'], '销额');
  h += kpiCard('增值', Q['增值'], '增值');
  h += kpiCard('手机', P['手机'], '手机');
  h += '</div></div>';

  /* 品类 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>品类达成</b></div><div class="rows">';
  CATS.forEach(c => { h += catRow(c, P[c], c); });
  h += catRow('增值', Q['增值'], '增值');
  h += '</div></div>';

  /* 考核机型（独立板块） */
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
const DAY_ORDER = ['毛利','增值','手机','音频穿戴','智慧办公','HD','会员','回收','贴膜','电信积分','滞销','优享/会员','尊享/储值'];
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
    h += '<div class="' + cls + '">'
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
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>全店今日达成</b>'
     + '<span class="tail">' + esc(DATA.meta.dayTitle || DATA.meta.date) + '</span></div>';
  h += dayHTML(DATA.store.dailyDone, DATA.store.dailyGap);
  h += '<div style="font-size:10.5px;color:var(--tx3);padding:9px 2px 0;line-height:1.7">'
     + '大数字＝今天已完成；下方＝距每日任务的差额（负数表示还差）</div>';
  h += '</div>';

  /* 每人今日 */
  h += '<div class="sec"><div class="sec-h"><span class="bar"></span><b>每人今日</b></div>';
  DATA.meta.employees.forEach(n => {
    const p = DATA.people[n]; if(!p) return;
    const d = p.dailyDone || {};
    const items = [
      ['毛利', moneyShort(d['毛利'])],
      ['增值', moneyShort(d['增值'])],
      ['手机', cnt(d['手机'])],
      ['音频穿戴', cnt(d['音频穿戴'])],
      ['贴膜', cnt(d['贴膜'])],
    ];
    const allZero = ['毛利','增值','手机','音频穿戴','贴膜'].every(k => !isNum(d[k]) || d[k] === 0);
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
               day:renderDay, insight:renderInsight }[VIEW];
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
}

$$('.tab').forEach(t => t.onclick = () => {
  $$('.tab').forEach(x => x.classList.remove('on'));
  t.classList.add('on');
  VIEW = t.dataset.v;
  render();
});
