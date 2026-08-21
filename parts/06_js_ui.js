
/* ==========================================================
   交互：管理弹层 / 上传 / Toast
   ========================================================== */
let pickedFile = null;

function toast(msg, ms){
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('on');
  clearTimeout(t._tm);
  t._tm = setTimeout(() => t.classList.remove('on'), ms || 1800);
}

function log(msg, type){
  const box = $('#logBox');
  box.style.display = 'block';
  const cls = type || 'in';
  box.innerHTML += '<span class="' + cls + '">' + esc(msg) + '</span>\n';
  box.scrollTop = box.scrollHeight;
}

/* 选文件 */
const dz = $('#dropZone'), fi = $('#fileInput');
dz.onclick = () => fi.click();
dz.ondragover = e => { e.preventDefault(); dz.classList.add('hover'); };
dz.ondragleave = () => dz.classList.remove('hover');
dz.ondrop = e => {
  e.preventDefault(); dz.classList.remove('hover');
  if(e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
};
fi.onchange = () => { if(fi.files.length) setFile(fi.files[0]); };

function setFile(f){
  if(!/\.xlsx?$/i.test(f.name)){ toast('请选择 .xlsx 文件'); return; }
  pickedFile = f;
  $('#dropTitle').textContent = f.name;
  $('#dropSub').textContent = (f.size/1024).toFixed(0) + ' KB · 点击可重选';
  $('#btnParse').disabled = false;
}

/* 解析 + 同步 */
$('#btnParse').onclick = async () => {
  if(!pickedFile) return;
  const btn = $('#btnParse');
  btn.disabled = true; btn.textContent = '处理中…';
  $('#logBox').innerHTML = '';

  try{
    await loadXLSX(log);
    log('读取文件…', 'in');
    const ab = await pickedFile.arrayBuffer();

    log('解析表格…', 'in');
    const json = parseWorkbook(ab, pickedFile.name);

    const gm = json.store.performance['毛利'];
    log('✓ 解析成功', 'ok');
    log('  数据日期 ' + (json.meta.date || '未知'), 'in');
    log('  时间进度 ' + (isNum(json.meta.timeProgress) ? pct(json.meta.timeProgress,1) : '—'), 'in');
    log('  门店毛利 ' + money(gm.done) + ' / ' + money(gm.task) + '（' + pct(gm.rate,1) + '）', 'in');
    PEOPLE_ORDER.forEach(n => {
      const p = json.people[n].performance['毛利'];
      log('  ' + n + '：' + money(p.done) + (hasTaskRaw(p) ? '' : '（未分配任务）'), 'in');
    });

    /* 先本地生效 */
    DATA = json;
    render();
    $('#liveTag').textContent = '本机预览';
    log('✓ 页面已刷新', 'ok');

    /* 同步线上 */
    const token = $('#tokenInput').value.trim();
    if(token){
      localStorage.setItem('gh_token', token);
      await pushToGitHub(token, json, log);
      $('#liveTag').textContent = '数据已更新';
      log('店员刷新页面即可看到新数据', 'ok');
      toast('已更新，店员刷新可见');
    }else{
      log('未填密钥，仅本机生效，店员看到的还是旧数据', 'wa');
      toast('仅本机预览');
    }
  }catch(err){
    log('✗ ' + (err.message || err), 'er');
    toast('处理失败，看下方提示');
  }finally{
    btn.disabled = false; btn.textContent = '解析并更新';
  }
};

function hasTaskRaw(k){ return k && typeof k.task === 'number' && isFinite(k.task) && k.task !== 0; }

/* ==========================================================
   启动
   ========================================================== */
render();

/* 首次加载：若有目标已 100% 达成，撒一次彩带 */
(function celebrateIfAchieved(){
  const P = (DATA.store && DATA.store.performance) || {};
  const Q = (DATA.store && DATA.store.qcs) || {};
  const check = [P['销额'], P['毛利'], P['手机'], Q['增值']];
  const done = check.some(k => k && hasTask(k) && isNum(k.rate) && k.rate >= 1);
  if(done) setTimeout(() => confetti(90), 400);
})();

if(location.protocol === 'http:' || location.protocol === 'https:'){
  loadRemote(true);
}else{
  $('#liveTag').textContent = '本地文件';
}
</script>
</body>
</html>
