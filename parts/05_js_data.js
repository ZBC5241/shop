
/* ==========================================================
   数据加载：优先读线上 data.json，失败则用内嵌快照
   ========================================================== */
function loadRemote(silent){
  const url = CFG.dataFile + '?t=' + Date.now();
  return fetch(url, {cache:'no-store'})
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(j => {
      if(j && j.meta && j.store && j.people){
        DATA = j;
        render();
        $('#liveTag').textContent = '数据已更新';
        if(!silent) toast('已拉取最新数据');
        return true;
      }
      throw new Error('格式不对');
    })
    .catch(() => {
      $('#liveTag').textContent = '本地快照';
      if(!silent) toast('拉取失败，显示本地快照');
      return false;
    });
}

/* ==========================================================
   浏览器端 Excel 解析 —— 与 build_data.py 保持完全一致
   ========================================================== */
const SHEET_NAME = '李家村销售';
const PEOPLE_ORDER = ['邵乐乐','杨丽华','李泽','陈超磊','张博晨'];
const P1_ROWS = {'邵乐乐':4,'杨丽华':5,'李泽':6,'陈超磊':7,'张博晨':8}, P1_TOTAL = 9;
const P2_ROWS = {'邵乐乐':14,'杨丽华':15,'李泽':16,'陈超磊':17,'张博晨':18}, P2_TOTAL = 19;
const P3_ROWS = {'邵乐乐':28,'杨丽华':29,'李泽':30,'陈超磊':31,'张博晨':32}, P3_TOTAL = 33, P3_LABEL = 26;
const P4_ROWS = {'邵乐乐':38,'杨丽华':39,'李泽':40,'陈超磊':41}, P4_TOTAL = 42, P4_LABEL = 36;
const P1_BLOCKS = [['毛利',1],['手机',5],['PC',9],['平板',13],['穿戴',17],
                   ['音频',21],['HD',25],['智慧办公',29],['音频穿戴',33],['销额',37]];
const P1_SCORE = 41;

function xnum(v){
  if(v === null || v === undefined) return null;
  if(typeof v === 'number') return isFinite(v) ? v : null;
  if(typeof v === 'boolean') return null;
  if(v instanceof Date) return null;
  let s = String(v).trim();
  if(s === '' || s[0] === '#') return null;
  s = s.replace(/,/g,'').replace(/[¥￥]/g,'');
  const isPct = s.endsWith('%');
  if(isPct) s = s.slice(0,-1);
  const f = parseFloat(s);
  if(!isFinite(f)) return null;
  return isPct ? f/100 : f;
}
/* g(grid, 1-based行, 0-based列) */
function g(grid, row, col){
  const r = grid[row-1];
  if(!r) return null;
  return xnum(r[col]);
}
function g4(grid, row, col){
  return { task:g(grid,row,col), done:g(grid,row,col+1),
           gap:g(grid,row,col+2), rate:g(grid,row,col+3) };
}
function readPerf(grid, row){
  const d = {};
  P1_BLOCKS.forEach(([n,c]) => d[n] = g4(grid,row,c));
  d['绩效'] = g(grid,row,P1_SCORE);
  return d;
}
function readQcs(grid, row){
  const G = c => g(grid,row,c);
  return {
    '电信积分':  {task:G(1),done:G(2),gap:G(3),rate:G(4)},
    '会员搭售率':{terminal:G(5),care:G(6),gap:G(7),rate:G(8)},
    '回收搭售率':{orders:G(9),gap:G(10),rate:G(11)},
    '贴膜率':    {orders:G(12),gap:G(13),rate:G(14)},
    '考核机型':  {task:G(17),gap:G(18)},
    '乐回收':    {orders:G(19),amount:G(20),'增值':G(21)},
    '太力回收':  {orders:G(22),amount:G(23),'增值':G(24)},
    '增值':      {task:G(25),done:G(26),gap:G(27),rate:G(28)},
    '健康度':    {coupon:G(29),ratio:G(30),grossMargin:G(31),'增值率':G(32)},
    '星联会员':  {'优享':G(33),'尊享':G(34),'合计':G(35)}
  };
}
function readLabels(grid, labelRow, start, end){
  const r = grid[labelRow-1] || [];
  const out = [];
  for(let c = start; c < end; c++){
    const v = r[c];
    out.push(v === null || v === undefined || String(v).trim() === '' ? null : String(v).trim());
  }
  return out;
}
const DROP_KEYS = new Set(['摄影课']);
function readFlat(grid, row, labels, start){
  const d = {};
  labels.forEach((lab,i) => { if(lab && !DROP_KEYS.has(lab)) d[lab] = g(grid,row,start+i); });
  return d;
}

function parseWorkbook(ab, fileName){
  const wb = XLSX.read(ab, {type:'array', cellDates:true});
  if(wb.SheetNames.indexOf(SHEET_NAME) < 0)
    throw new Error('找不到工作表「' + SHEET_NAME + '」，该文件包含：' + wb.SheetNames.slice(0,8).join('、'));
  const ws = wb.Sheets[SHEET_NAME];
  const grid = XLSX.utils.sheet_to_json(ws, {header:1, defval:null, raw:true, blankrows:true});

  /* 结构校验：防止模板被改动导致静默错位 */
  const nameCol = r => { const x = grid[r-1]; return x && x[0] ? String(x[0]).trim() : ''; };
  const bad = [];
  PEOPLE_ORDER.forEach(n => {
    if(nameCol(P1_ROWS[n]) !== n) bad.push('业绩考核区第' + P1_ROWS[n] + '行应为「' + n + '」，实为「' + nameCol(P1_ROWS[n]) + '」');
    if(nameCol(P2_ROWS[n]) !== n) bad.push('全科生区第' + P2_ROWS[n] + '行应为「' + n + '」，实为「' + nameCol(P2_ROWS[n]) + '」');
  });
  if(nameCol(P1_TOTAL) !== '合计') bad.push('第' + P1_TOTAL + '行应为「合计」');
  if(bad.length) throw new Error('表格结构和预期不一致，为避免读出错数已中止：\n· ' + bad.slice(0,4).join('\n· '));

  /* 元信息 */
  let dateStr = '';
  const rawDate = (grid[0] || [])[1];
  if(rawDate instanceof Date){
    const p = n => String(n).padStart(2,'0');
    dateStr = rawDate.getFullYear() + '-' + p(rawDate.getMonth()+1) + '-' + p(rawDate.getDate());
  }else if(rawDate){
    dateStr = String(rawDate).trim().slice(0,10);
  }
  const tp = g(grid,1,8);
  const dayTitle = ((grid[24] || [])[1]) ? String(grid[24][1]).trim() : '';
  const d3 = readLabels(grid, P3_LABEL, 1, 15);
  const d4 = readLabels(grid, P4_LABEL, 1, 15);

  const now = new Date();
  const pad = n => String(n).padStart(2,'0');
  const out = {
    meta:{
      storeName:'华为李家村万达授权体验店',
      date:dateStr, dayTitle:dayTitle, timeProgress:tp,
      employees:PEOPLE_ORDER.slice(),
      sourceFile:fileName,
      generatedAt: now.getFullYear() + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate())
                 + ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds())
    },
    store:{
      performance: readPerf(grid, P1_TOTAL),
      qcs:         readQcs(grid, P2_TOTAL),
      dailyDone:   readFlat(grid, P3_TOTAL, d3, 1),
      dailyGap:    readFlat(grid, P4_TOTAL, d4, 1)
    },
    people:{}
  };
  PEOPLE_ORDER.forEach(n => {
    out.people[n] = {
      performance: readPerf(grid, P1_ROWS[n]),
      qcs:         readQcs(grid, P2_ROWS[n]),
      dailyDone:   readFlat(grid, P3_ROWS[n], d3, 1),
      dailyGap:    P4_ROWS[n] ? readFlat(grid, P4_ROWS[n], d4, 1) : {}
    };
  });
  return out;
}

/* ==========================================================
   GitHub 同步
   ========================================================== */
function b64(str){
  const bytes = new TextEncoder().encode(str);
  let bin = '';
  const CH = 0x8000;
  for(let i = 0; i < bytes.length; i += CH){
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i+CH));
  }
  return btoa(bin);
}

async function pushToGitHub(token, json, log){
  const api = 'https://api.github.com/repos/' + CFG.repo + '/contents/' + CFG.dataFile;
  const hd  = { 'Authorization':'Bearer ' + token, 'Accept':'application/vnd.github+json' };

  log('连接 GitHub…', 'in');
  let sha = null;
  const gr = await fetch(api + '?ref=' + CFG.branch, {headers:hd, cache:'no-store'});
  if(gr.status === 200){
    sha = (await gr.json()).sha;
    log('找到现有 data.json', 'in');
  }else if(gr.status === 404){
    log('线上还没有 data.json，将新建', 'wa');
  }else if(gr.status === 401){
    throw new Error('密钥无效或已过期（401）');
  }else if(gr.status === 403){
    throw new Error('没有权限访问该仓库（403）');
  }else{
    throw new Error('读取失败：HTTP ' + gr.status);
  }

  const body = {
    message: '更新看板数据 ' + (json.meta.date || '') + ' via 看板上传',
    content: b64(JSON.stringify(json, null, 1)),
    branch : CFG.branch
  };
  if(sha) body.sha = sha;

  log('上传中…', 'in');
  const pr = await fetch(api, {method:'PUT', headers:hd, body:JSON.stringify(body)});
  if(!pr.ok){
    let msg = 'HTTP ' + pr.status;
    try{ const e = await pr.json(); if(e.message) msg += ' · ' + e.message; }catch(_){}
    throw new Error('上传失败：' + msg);
  }
  log('✓ 已同步到线上', 'ok');
  return true;
}

/* 动态加载 SheetJS（多源兜底，国内优先） */
const XLSX_CDNS = [
  'https://registry.npmmirror.com/xlsx/0.18.5/files/dist/xlsx.full.min.js',
  'https://cdn.staticfile.org/xlsx/0.18.5/xlsx.full.min.js',
  'https://cdn.bootcdn.net/ajax/libs/xlsx/0.18.5/xlsx.full.min.js',
  'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js'
];
function loadXLSX(log){
  if(window.XLSX) return Promise.resolve();
  let i = 0;
  return new Promise((res, rej) => {
    const tryNext = () => {
      if(i >= XLSX_CDNS.length) return rej(new Error('解析组件加载失败，请检查网络后重试'));
      const url = XLSX_CDNS[i++];
      log('加载解析组件…（源 ' + i + '）', 'in');
      const s = document.createElement('script');
      s.src = url;
      s.onload  = () => window.XLSX ? res() : tryNext();
      s.onerror = tryNext;
      document.head.appendChild(s);
    };
    tryNext();
  });
}
