const $ = (id) => document.getElementById(id);
let CURRENT_USER = null;
let CURRENT_PERMS = new Set();
let ALL_PERMS = [];
let notifyOpen = false;

function escapeHtml(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function techDetailsText(raw){
  const t=String(raw||'').trim();
  return t ? t : 'لا توجد تفاصيل فنية إضافية لهذا الحدث. تم تسجيل الرسالة الأساسية فقط.';
}
function hasPerm(p){return CURRENT_PERMS.has(p) || CURRENT_PERMS.has('all');}

function todayISO(){
  const d=new Date();
  const off=d.getTimezoneOffset();
  const local=new Date(d.getTime()-off*60000);
  return local.toISOString().slice(0,10);
}
function initDateControls(){
  // Keep filters readable in RTL UI. Empty native date placeholders can look corrupted,
  // so default them to today's date and allow clearing when needed.
  ['logDate','eventDate','errorDate'].forEach(id=>{
    const el=$(id);
    if(!el) return;
    el.lang='en';
    el.dir='ltr';
    el.classList.add('date-input');
    if(!el.value) el.value=todayISO();
    const wrap=document.createElement('div');
    wrap.className='date-filter-wrap';
    const label=document.createElement('span');
    label.className='date-label';
    label.textContent=id==='logDate'?'تاريخ السجلات':(id==='eventDate'?'تاريخ الأحداث':'تاريخ الأخطاء');
    el.parentNode.insertBefore(wrap, el);
    wrap.appendChild(label);
    wrap.appendChild(el);
  });
  [['logDate','loadLogsBtn'],['eventDate','loadEventsBtn'],['errorDate','loadErrorsBtn']].forEach(([dateId,loadBtnId])=>{
    const el=$(dateId);
    if(!el || !el.parentNode || el.parentNode.querySelector('.date-clear-btn')) return;
    const btn=document.createElement('button');
    btn.type='button';
    btn.className='date-clear-btn';
    btn.textContent='كل التواريخ';
    btn.title='إزالة فلتر التاريخ';
    btn.onclick=()=>{el.value=''; const lb=$(loadBtnId); if(lb) lb.click();};
    el.parentNode.appendChild(btn);
  });
}

async function api(url, opts={}){
  const r=await fetch(url,{headers:{'Content-Type':'application/json'},credentials:'same-origin',...opts});
  if(r.status===401){location.href='/login';throw new Error('login_required');}
  if(r.status===403)throw new Error('ليس لديك صلاحية لهذه العملية');
  if(!r.ok){
    let txt=await r.text();
    try{const j=JSON.parse(txt); txt=j.detail||j.message||txt;}catch{}
    throw new Error(txt);
  }
  const ct=r.headers.get('content-type')||'';
  if(ct.includes('application/json')) return await r.json();
  return await r.text();
}

function showView(id){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active-view'));
  const el=$(id); if(el) el.classList.add('active-view');
  document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===id));
  if(id==='events') loadEvents();
  if(id==='errors') loadErrors();
  if(id==='remote') loadRemote();
  if(id==='users') loadUsers();
  if(id==='health') loadHealth();
  if(id==='diagnostics') loadSystemTest(false);
  if(id==='conversations') loadThreads();
  if(id==='review') loadReview();
  if(id==='security') loadLoginAttempts();
}

document.querySelectorAll('.nav').forEach(btn=>btn.onclick=()=>showView(btn.dataset.view));
document.querySelectorAll('[data-view-jump]').forEach(btn=>btn.onclick=()=>showView(btn.dataset.viewJump));

function applyPermissions(){
  document.querySelectorAll('[data-perm]').forEach(el=>{
    const p=el.dataset.perm;
    el.classList.toggle('hidden-by-perm', !hasPerm(p));
  });
  const active = document.querySelector('.nav.active:not(.hidden-by-perm)') || document.querySelector('.nav:not(.hidden-by-perm)');
  if(active) showView(active.dataset.view);
}

async function loadMe(){
  const me=await api('/api/me');
  CURRENT_USER=me.user;
  CURRENT_PERMS=new Set(me.permissions||[]);
  if($('userBadge')) $('userBadge').textContent=(CURRENT_USER?.display_name||CURRENT_USER?.username||'مستخدم');
  applyPermissions();
}

function drawChart(labels, values){
  const c=$('dailyChart'); if(!c) return;
  const rect=c.getBoundingClientRect();
  const dpr=window.devicePixelRatio||1;
  const cssW=Math.max(320, Math.floor(rect.width||c.parentElement?.clientWidth||520));
  const cssH=Math.max(210, Math.floor(rect.height||220));
  c.width=cssW*dpr; c.height=cssH*dpr;
  c.style.width='100%'; c.style.height=cssH+'px';
  const ctx=c.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  const w=cssW,h=cssH,pad=38;
  ctx.clearRect(0,0,w,h);
  const max=Math.max(1,...(values||[]));
  ctx.strokeStyle='#dbe4e8';ctx.lineWidth=1;
  for(let i=0;i<5;i++){const y=pad+(h-pad*2)*i/4;ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(w-pad,y);ctx.stroke();}
  ctx.strokeStyle='#4d8899';ctx.fillStyle='#4d8899';ctx.lineWidth=2;ctx.beginPath();
  (values||[]).forEach((v,i)=>{const x=pad+(w-pad*2)*(i/((values.length-1)||1));const y=h-pad-(h-pad*2)*(v/max);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});
  ctx.stroke();
  (values||[]).forEach((v,i)=>{const x=pad+(w-pad*2)*(i/((values.length-1)||1));const y=h-pad-(h-pad*2)*(v/max);ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();});
  ctx.fillStyle='#69777f';ctx.font='12px Segoe UI';ctx.textAlign='center';ctx.textBaseline='middle';
  (labels||[]).forEach((lab,i)=>{const x=pad+(w-pad*2)*(i/((labels.length-1)||1));ctx.fillText(String(lab).slice(5),x,h-14);});
}

let LAST_CHART_SERIES=null;
async function loadStats(){
  if(!hasPerm('dashboard')) return;
  try{const s=await api('/api/stats');$('mTotal').textContent=s.total;$('mToday').textContent=s.today;$('mTelegram').textContent=s.telegram;$('mWhatsapp').textContent=s.whatsapp;$('mCalc').textContent=s.calculation;$('mClarify').textContent=s.clarification;$('mAvg').textContent=s.avg_ms+'ms';LAST_CHART_SERIES=s.series;drawChart(s.series.labels,s.series.values);}catch(e){console.error(e)}
}
let chartResizeTimer=null;
window.addEventListener('resize',()=>{clearTimeout(chartResizeTimer);chartResizeTimer=setTimeout(()=>{if(LAST_CHART_SERIES) drawChart(LAST_CHART_SERIES.labels,LAST_CHART_SERIES.values);},160);});
function humanTelegramError(err){
  if(!err) return '';
  const t=String(err);
  if(t.includes('404') || t.includes('Not Found')) return ' | مشكلة: توكن تليجرام غير صحيح أو البوت غير موجود. انسخ التوكن من BotFather مرة أخرى.';
  return ' | آخر خطأ: '+t;
}
async function loadServices(){
  try{
    const s=await api('/api/services/status');
    $('sProject').textContent=s.project.running?'شغال':'متوقف';
    $('sTelegram').textContent=s.telegram.running?'شغال':'متوقف';
    $('sWhatsapp').textContent=s.whatsapp.running?'شغال':'متوقف';
    if($('sSqlServer')){
      const sql=s.sqlserver||{};
      const enabled=!!sql.enabled;
      const ok=!!sql.ok;
      $('sSqlServer').textContent=!enabled?'غير مفعل':(ok?'متصل':'منقطع');
      const mc=sql.mirror_counts||{};
      const diffCount=mc.diffs?Object.keys(mc.diffs).length:0;
      const lr=sql.worker_last_result||{};
      let syncText=!enabled?'SQLite فقط':(ok?(diffCount?`فرق في ${diffCount} جدول`:'متزامن'):'يعمل محليًا على SQLite');
      if(lr && lr.ok===false) syncText+=' | آخر مزامنة فشلت';
      $('sSqlServerSync').textContent=syncText;
    }
    const tgName=s.telegram.bot_username?` @${s.telegram.bot_username}`:'';
    $('telegramStatusText').textContent=`الحالة: ${s.telegram.running?'شغال':'متوقف'} | Token: ${s.telegram.token_set?'موجود':'غير موجود'}${tgName}${humanTelegramError(s.telegram.last_error)}`;
    $('whatsappStatusText').textContent=`الحالة: ${s.whatsapp.running?'شغال':'متوقف'} | Token: ${s.whatsapp.token_set?'موجود':'غير موجود'} | استقبل: ${s.whatsapp.received} | أرسل: ${s.whatsapp.sent} ${s.whatsapp.last_error?'| آخر خطأ: '+s.whatsapp.last_error:''}`;
    $('healthBadge').textContent='متصل';
  }catch(e){$('healthBadge').textContent='غير متصل';}
}
function cleanPreviewText(v, maxLen=190){
  let t=(v||'').toString();
  // Keep the user-facing answer only. Technical JSON/HTTP details stay in Events/Errors pages.
  t=t.replace(/```[\s\S]*?```/g,' ');
  t=t.replace(/\{\s*\"[^\n]{0,80}/g,' ');
  t=t.replace(/HTTP\s+\d{3}[:\s][^\n]*/gi,' ');
  t=t.replace(/payload|headers|chat_id|status_code|response|elapsed_ms/gi,' ');
  t=t.replace(/\s+/g,' ').trim();
  if(!t) return 'لم يتم حفظ نص الرد بعد. افتح السجل الكامل للمراجعة.';
  return t.length>maxLen ? t.slice(0,maxLen-1)+'…' : t;
}
async function loadRecent(){
  if(!hasPerm('logs') && !hasPerm('dashboard')) return;
  try{
    const data=await api('/api/logs?limit=8');
    $('recentList').innerHTML=data.rows.map(r=>{
      const answer=cleanPreviewText(r.answer||r.response||'',220);
      const ts=(r.ts||'').replace('T',' ').slice(0,16);
      return `<div class="recent-item recent-chat-item"><b>${escapeHtml(r.question||'—')}</b><span class="recent-answer-preview">${escapeHtml(answer)}</span><small class="recent-time">${escapeHtml(ts)}</small></div>`;
    }).join('')||'<div class="recent-item">لا توجد محادثات بعد.</div>';
  }catch(e){console.warn(e)}
}
async function loadLogs(){
  if(!hasPerm('logs')) return;
  const ch=$('logChannel').value;const dt=$('logDate').value;const qs=new URLSearchParams({limit:'200'});if(ch)qs.set('channel',ch);if(dt)qs.set('date',dt);const data=await api('/api/logs?'+qs.toString());$('logsTable').innerHTML=data.rows.map(r=>`<tr><td>${escapeHtml(r.ts)}</td><td>${escapeHtml(r.channel)}</td><td>${escapeHtml(r.question)}</td><td><pre>${escapeHtml(r.answer)}</pre></td><td>${escapeHtml(r.answer_type)}</td><td>${escapeHtml(r.elapsed_ms)}ms</td></tr>`).join('')||'<tr><td colspan="6">لا توجد سجلات.</td></tr>';
}
async function refreshAll(){await Promise.allSettled([loadStats(),loadServices(),loadRecent(),loadLogs(),loadNotifications(false)]);}
if($('refreshBtn')) $('refreshBtn').onclick=refreshAll;
if($('loadLogsBtn')) $('loadLogsBtn').onclick=loadLogs;

function toast(title, msg=''){
  // No blocking alerts. Events go to notification bell and technical log.
  loadNotifications(false);
}

document.querySelectorAll('[data-service]').forEach(btn=>btn.onclick=async()=>{btn.disabled=true;try{await api(`/api/services/${btn.dataset.service}/${btn.dataset.action}`,{method:'POST'});toast('تم تنفيذ العملية');await loadServices();await loadNotifications(false);}catch(e){toast('خطأ',e.message)}finally{btn.disabled=false;}});

function addMsg(text,cls,id){const div=document.createElement('div');div.className='msg '+cls;if(id)div.id=id;div.textContent=text;$('chatBox').appendChild(div);$('chatBox').scrollTop=$('chatBox').scrollHeight;return div;}
if($('sendChatBtn')) $('sendChatBtn').onclick=async()=>{const q=$('chatInput').value.trim();if(!q)return;addMsg(q,'user');$('chatInput').value='';const thinkingId='thinking-'+Date.now();addMsg('يكتب الآن...','bot typing',thinkingId);$('sendChatBtn').disabled=true;try{const r=await api('/api/ask',{method:'POST',body:JSON.stringify({question:q,channel:'dashboard'})});const th=$(thinkingId);if(th)th.remove();addMsg(r.answer,'bot');await refreshAll();
  await loadModeIntoServices().catch(()=>{});}catch(e){const th=$(thinkingId);if(th)th.remove();addMsg('خطأ: '+e.message,'bot')}finally{$('sendChatBtn').disabled=false;}};
if($('chatInput')) $('chatInput').addEventListener('keydown',e=>{if(e.key==='Enter' && !e.shiftKey && !e.isComposing){e.preventDefault();$('sendChatBtn').click();}});

async function loadSettings(){
  if(!hasPerm('settings')) return;
  const c=await api('/api/config?mask=true');
  $('telegramMasked').value=c.telegram.bot_token_masked||'';$('waInstance').value=c.wapilot.instance_id||'';$('waWebhookPath').value=c.wapilot.webhook_path||'';$('waPublicWebhook').value=c.wapilot.public_webhook_url||'';$('waApiUrl').value=c.wapilot.api_url_template||'';$('waMasked').value=c.wapilot.api_token_masked||'';
  if($('sqlEnabled')){const s=c.sqlserver||{};$('sqlEnabled').checked=!!s.enabled;$('sqlSyncEnabled').checked=s.sync_enabled!==false;$('sqlHost').value=s.host||'';$('sqlPort').value=s.port||'1433';$('sqlDatabase').value=s.database||'MawarethAI';$('sqlAuthMode').value=s.auth_mode||'sql';$('sqlUsername').value=s.username||'';$('sqlPasswordMasked').value=s.password_masked||'';$('sqlDriver').value=s.driver||'ODBC Driver 18 for SQL Server';$('sqlEncrypt').checked=s.encrypt!==false;$('sqlTrustCert').checked=s.trust_server_certificate!==false;$('sqlTimeout').value=s.timeout_seconds||5;$('sqlSyncInterval').value=s.sync_interval_seconds||30;$('sqlBackupDir').value=s.backup_dir||'C:\\MawarethAI_Backups';}
  $('logoTitle').value=c.ui?.logo_title||'مفتي المواريث';$('logoSubtitle').value=c.ui?.logo_subtitle||'Dashboard';$('brandTitle').textContent=$('logoTitle').value;$('brandSubtitle').textContent=$('logoSubtitle').value;
  $('autoEnabled').checked=!!c.autostart?.enabled;$('autoTelegram').checked=!!c.autostart?.telegram;$('autoWhatsapp').checked=!!c.autostart?.whatsapp;$('autoNgrok').checked=!!c.autostart?.ngrok;$('ngrokPath').value=c.ngrok?.path||'';
  const ts=Date.now();$('brandLogo').src='/assets/logo?ts='+ts;$('logoPreview').src='/assets/logo?ts='+ts;
}

async function uploadLogoIfSelected(){
  const f=$('logoFile')?.files?.[0]; if(!f) return {uploaded:false};
  const data_url = await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=rej;r.readAsDataURL(f);});
  const payload=JSON.stringify({filename:f.name,data_url});
  const endpoints=['/api/logo','/api/upload-logo','/api/branding/logo'];
  let lastErr=null;
  for(const ep of endpoints){
    try{return await api(ep,{method:'POST',body:payload});}
    catch(e){lastErr=e; if(!String(e.message||'').includes('Not Found')) break;}
  }
  throw lastErr||new Error('فشل رفع الشعار');
}


if($('checkTelegramBtn')) $('checkTelegramBtn').onclick=async()=>{
  const box=$('telegramCheckResult');
  box.textContent='جاري فحص توكن تليجرام...';
  try{
    const r=await api('/api/telegram/check');
    const d=r.diagnostics||{};
    const f=d.format||{};
    box.textContent=[
      (r.ok?'✅ ':'❌ ')+r.message,
      'صيغة التوكن: '+(f.looks_like_botfather_token?'صحيحة مبدئيًا':'غير صحيحة'),
      'يحتوي على نقطتين (:): '+(f.has_colon?'نعم':'لا'),
      'البادئة رقمية: '+(f.numeric_prefix?'نعم':'لا'),
      'طول التوكن: '+(f.length||0),
      d.status_code?('HTTP: '+d.status_code):'',
      d.response_preview?('رد Telegram: '+d.response_preview.slice(0,400)):'',
    ].filter(Boolean).join('\n');
    await loadServices();
  }catch(e){box.textContent='خطأ أثناء الفحص: '+e.message;}
};

function collectSqlServerConfig(){
  if(!$('sqlEnabled')) return undefined;
  return {
    enabled:$('sqlEnabled').checked,
    sync_enabled:$('sqlSyncEnabled').checked,
    host:($('sqlHost').value||'').trim(),
    port:($('sqlPort').value||'1433').trim(),
    database:($('sqlDatabase').value||'MawarethAI').trim(),
    auth_mode:$('sqlAuthMode').value,
    username:($('sqlUsername').value||'').trim(),
    password:$('sqlPassword').value,
    driver:($('sqlDriver').value||'ODBC Driver 18 for SQL Server').trim(),
    encrypt:$('sqlEncrypt').checked,
    trust_server_certificate:$('sqlTrustCert').checked,
    timeout_seconds:Number($('sqlTimeout').value||10),
    sync_interval_seconds:Number($('sqlSyncInterval').value||30),
    backup_dir:($('sqlBackupDir').value||'C:\\MawarethAI_Backups').trim()
  };
}

function collectSettingsBody(){
  return {
    telegram:{bot_token:$('telegramToken').value},
    wapilot:{instance_id:$('waInstance').value,webhook_path:$('waWebhookPath').value,public_webhook_url:$('waPublicWebhook').value,api_url_template:$('waApiUrl').value,api_token:$('waToken').value},
    sqlserver:collectSqlServerConfig(),
    ui:{logo_title:$('logoTitle').value,logo_subtitle:$('logoSubtitle').value},
    autostart:{enabled:$('autoEnabled').checked,telegram:$('autoTelegram').checked,whatsapp:$('autoWhatsapp').checked,ngrok:$('autoNgrok').checked},
    ngrok:{path:$('ngrokPath').value}
  };
}

if($('settingsForm')) $('settingsForm').onsubmit=async(e)=>{e.preventDefault();const body=collectSettingsBody();
  try{
    await api('/api/config',{method:'POST',body:JSON.stringify(body)});
    try{await uploadLogoIfSelected();}
    catch(logoErr){$('settingsResult').textContent='تم حفظ الإعدادات، لكن رفع الشعار فشل: '+logoErr.message; return;}
    $('settingsResult').textContent='تم حفظ الإعدادات والشعار بنجاح.';
    $('telegramToken').value='';$('waToken').value='';if($('sqlPassword'))$('sqlPassword').value='';$('logoFile').value='';
    await loadSettings();await loadServices();await loadNotifications(false);
  }catch(err){$('settingsResult').textContent='خطأ: '+err.message;}
};


async function sqlAction(endpoint, label){
  const box=$('sqlResult'); if(!box) return;
  box.textContent='جاري تنفيذ: '+label+' ...';
  const sqlCfg=collectSqlServerConfig();
  if(!sqlCfg.host || !sqlCfg.port){
    box.textContent='خطأ: املأ Host و Port أولًا.';
    return;
  }
  try{
    const r=await api(endpoint,{method:'POST',body:JSON.stringify({sqlserver:sqlCfg})});
    box.textContent=JSON.stringify(r,null,2);
    await loadNotifications(false);
  }catch(e){
    box.textContent='خطأ: '+e.message;
  }
}
if($('sqlTestBtn')) $('sqlTestBtn').onclick=()=>sqlAction('/api/sqlserver/test','فحص الاتصال');
if($('sqlInitBtn')) $('sqlInitBtn').onclick=()=>sqlAction('/api/sqlserver/init','إنشاء القاعدة والجداول');
if($('sqlSyncNowBtn')) $('sqlSyncNowBtn').onclick=()=>sqlAction('/api/sqlserver/sync-now','مزامنة الآن');
if($('sqlBackupBtn')) $('sqlBackupBtn').onclick=()=>sqlAction('/api/sqlserver/backup','Backup الآن');

if($('logoFile')) $('logoFile').addEventListener('change',()=>{
  const f=$('logoFile').files?.[0]; if(!f) return;
  const r=new FileReader();
  r.onload=()=>{ if($('logoPreview')) $('logoPreview').src=r.result; if($('brandLogo')) $('brandLogo').src=r.result; };
  r.readAsDataURL(f);
});

if($('testWaBtn')) $('testWaBtn').onclick=async()=>{try{const r=await api('/api/wapilot/test-send',{method:'POST',body:JSON.stringify({to:$('testWaTo').value,message:$('testWaMsg').value})});$('testWaResult').textContent=JSON.stringify(r,null,2);}catch(e){$('testWaResult').textContent='خطأ: '+e.message;}};

async function loadEvents(){
  if(!hasPerm('events')) return;
  const qs=new URLSearchParams({limit:'500'});if($('eventLevel')?.value) qs.set('level',$('eventLevel').value);if($('eventComponent')?.value) qs.set('component',$('eventComponent').value);if($('eventDate')?.value) qs.set('date',$('eventDate').value);
  try{const data=await api('/api/events?'+qs.toString());$('eventsTable').innerHTML=data.rows.map(r=>`<tr><td>${escapeHtml(r.ts)}</td><td><span class="level ${escapeHtml(r.level)}">${escapeHtml(r.level)}</span></td><td>${escapeHtml(r.component)}</td><td>${escapeHtml(r.event)}</td><td><pre>${escapeHtml(r.message)}</pre><details><summary>التفاصيل الفنية</summary><pre>${escapeHtml(techDetailsText(r.raw_json))}</pre></details></td></tr>`).join('')||'<tr><td colspan="5">لا توجد أحداث.</td></tr>';}catch(e){$('eventsTable').innerHTML=`<tr><td colspan="5">خطأ: ${escapeHtml(e.message)}</td></tr>`;}
}
async function loadErrors(){
  if(!hasPerm('errors')) return;
  const qs=new URLSearchParams({limit:'500'});if($('errorDate')?.value) qs.set('date',$('errorDate').value);
  try{const data=await api('/api/errors?'+qs.toString());$('errorsTable').innerHTML=data.rows.map(r=>`<tr><td>${escapeHtml(r.ts)}</td><td>${escapeHtml(r.component)}</td><td>${escapeHtml(r.event)}</td><td><pre>${escapeHtml(r.message)}</pre><details><summary>التفاصيل الفنية</summary><pre>${escapeHtml(techDetailsText(r.raw_json))}</pre></details></td></tr>`).join('')||'<tr><td colspan="4">لا توجد أخطاء مسجلة.</td></tr>';}catch(e){$('errorsTable').innerHTML=`<tr><td colspan="4">خطأ: ${escapeHtml(e.message)}</td></tr>`;}
}
async function loadRemote(){if(!hasPerm('remote')) return;try{const data=await api('/api/remote/access');$('remoteInfo').textContent=JSON.stringify(data,null,2);}catch(e){$('remoteInfo').textContent='خطأ: '+e.message;}}
if($('loadEventsBtn')) $('loadEventsBtn').onclick=loadEvents;if($('loadErrorsBtn')) $('loadErrorsBtn').onclick=loadErrors;if($('loadRemoteBtn')) $('loadRemoteBtn').onclick=loadRemote;

async function loadNotifications(open=false){
  if(!hasPerm('notifications')) return;
  try{
    const data=await api('/api/notifications?limit=30');
    const b=$('notifyBadge');
    if(data.unread>0){b.textContent=data.unread;b.classList.remove('hidden');}else{b.classList.add('hidden');}
    $('notifyList').innerHTML=data.rows.map(n=>`<div class="notify-item ${n.seen?'seen':'unseen'}"><b>${escapeHtml(n.title)}</b><span>${escapeHtml(n.ts)} · ${escapeHtml(n.level)}</span><p>${escapeHtml(n.message||'')}</p></div>`).join('')||'<div class="notify-item">لا توجد إشعارات.</div>';
    if(open) $('notifyDropdown').classList.remove('hidden');
  }catch(e){console.warn(e)}
}
if($('notifyBtn')) $('notifyBtn').onclick=async()=>{
  notifyOpen=!notifyOpen;
  $('notifyDropdown').classList.toggle('hidden',!notifyOpen);
  document.body.classList.toggle('notify-open', notifyOpen);
  if(notifyOpen) await loadNotifications(true);
};
document.addEventListener('click', (ev)=>{
  const wrap = document.querySelector('.notify-wrap');
  if(notifyOpen && wrap && !wrap.contains(ev.target)){
    notifyOpen=false;
    $('notifyDropdown').classList.add('hidden');
    document.body.classList.remove('notify-open');
  }
});
if($('markNotifyRead')) $('markNotifyRead').onclick=async()=>{await api('/api/notifications/read',{method:'POST'});await loadNotifications(true);};
if($('logoutBtn')) $('logoutBtn').onclick=async()=>{await api('/api/logout',{method:'POST'});location.href='/login';};

function permLabel(p){return ({dashboard:'الرئيسية',chat:'المحادثة',services:'التشغيل',logs:'سجل المحادثات',events:'الأحداث',errors:'الأخطاء',remote:'الوصول الخارجي',settings:'الإعدادات',users:'المستخدمون',notifications:'الإشعارات',health:'حالة النظام',tests:'اختبار شامل',backup:'النسخ الاحتياطي',conversations:'إدارة المحادثات',review:'مراجعة المسائل',security:'الأمان'})[p]||p;}
async function loadUsers(){
  if(!hasPerm('users')) return;
  const data=await api('/api/users');ALL_PERMS=data.permissions||[];
  $('permissionChecks').innerHTML=ALL_PERMS.map(p=>`<label><input type="checkbox" class="permCheck" value="${escapeHtml(p)}" /> ${escapeHtml(permLabel(p))}</label>`).join('');
  $('usersTable').innerHTML=data.rows.map(u=>`<tr><td>${escapeHtml(u.username)}<br><small>${escapeHtml(u.display_name||'')}</small></td><td>${escapeHtml(u.role)}</td><td>${u.active?'نعم':'لا'}</td><td>${escapeHtml((u.permissions||[]).map(permLabel).join('، '))}</td><td><button data-edit-user="${escapeHtml(u.username)}">تعديل</button> ${u.username==='admin'?'':`<button class="danger" data-del-user="${escapeHtml(u.username)}">حذف</button>`}</td></tr>`).join('');
  document.querySelectorAll('[data-edit-user]').forEach(btn=>btn.onclick=()=>{
    const u=data.rows.find(x=>x.username===btn.dataset.editUser); if(!u) return;
    $('userUsername').value=u.username;$('userDisplay').value=u.display_name||'';$('userRole').value=u.role;$('userActive').checked=!!u.active;$('userPassword').value='';
    document.querySelectorAll('.permCheck').forEach(c=>c.checked=(u.permissions||[]).includes(c.value));
  });
  document.querySelectorAll('[data-del-user]').forEach(btn=>btn.onclick=async()=>{if(!confirm('حذف المستخدم؟'))return;await api(`/api/users/${encodeURIComponent(btn.dataset.delUser)}/delete`,{method:'POST'});await loadUsers();await loadNotifications(false);});
}
if($('userRole')) $('userRole').onchange=()=>{
  const role=$('userRole').value; const defaults={viewer:['dashboard','logs','notifications','health'],operator:['dashboard','chat','services','logs','events','errors','remote','notifications','health','tests','conversations','review'],admin:['dashboard','chat','services','logs','events','errors','remote','settings','users','notifications','health','tests','backup','conversations','review','security']}[role]||[];
  document.querySelectorAll('.permCheck').forEach(c=>c.checked=defaults.includes(c.value));
};
if($('saveUserBtn')) $('saveUserBtn').onclick=async()=>{
  const permissions=[...document.querySelectorAll('.permCheck:checked')].map(c=>c.value);
  const body={username:$('userUsername').value,display_name:$('userDisplay').value,password:$('userPassword').value,role:$('userRole').value,active:$('userActive').checked,permissions};
  try{await api('/api/users',{method:'POST',body:JSON.stringify(body)});$('userResult').textContent='تم الحفظ';$('userPassword').value='';await loadUsers();await loadNotifications(false);}catch(e){$('userResult').textContent='خطأ: '+e.message;}
};


async function loadHealth(){
  if(!hasPerm('health')) return;
  try{
    const d=await api('/api/health/full');
    const h=d.health||{};
    const items=[
      ['Dashboard', h.dashboard?.ok, `Port: ${h.dashboard?.port||''}`],
      ['Runtime', h.runtime?.ok, 'محرك المواريث'],
      ['Database', h.database?.ok, h.database?.path||''],
      ['Telegram', h.telegram?.running, h.telegram?.token_set?'Token موجود':'Token غير موجود'],
      ['WhatsApp', h.whatsapp?.enabled, `استقبل ${h.whatsapp?.received||0} / أرسل ${h.whatsapp?.sent||0}`],
      ['ngrok', h.ngrok?.running, h.ngrok?.public_url||'غير شغال'],
      ['وضع الرد', true, h.mode==='monitor'?'مراقبة فقط':'تشغيل فعلي']
    ];
    $('healthGrid').innerHTML=items.map(x=>`<div class="status-card"><span>${escapeHtml(x[0])}</span><b class="${x[1]?'ok-text':'bad-text'}">${x[1]?'يعمل':'تنبيه'}</b><p>${escapeHtml(x[2])}</p></div>`).join('');
    $('healthDetails').textContent=JSON.stringify(d,null,2);
  }catch(e){$('healthDetails').textContent='خطأ: '+e.message;}
}
if($('loadHealthBtn')) $('loadHealthBtn').onclick=loadHealth;

async function loadSystemTest(auto=false){
  if(!hasPerm('tests')) return;
  if(!auto && !$('systemTestResults')) return;
  const box=$('systemTestResults'); if(box) box.innerHTML='<div class="muted-block">جار تشغيل الاختبار...</div>';
  try{
    const d=await api('/api/system-test/run',{method:'POST'});
    if(box) box.innerHTML=(d.results||[]).map(r=>`<div class="test-item ${r.ok?'pass':'fail'}"><b>${escapeHtml(r.name)}</b><span>${r.ok?'نجح':'فشل'}</span><p>${escapeHtml(r.message)}</p></div>`).join('');
  }catch(e){if(box) box.innerHTML='<div class="test-item fail">خطأ: '+escapeHtml(e.message)+'</div>';}
}
if($('runSystemTestBtn')) $('runSystemTestBtn').onclick=()=>loadSystemTest(false);

async function loadThreads(){
  if(!hasPerm('conversations')) return;
  const qs=new URLSearchParams({limit:'200'});
  if($('threadChannel')?.value) qs.set('channel',$('threadChannel').value);
  if($('threadSearch')?.value) qs.set('search',$('threadSearch').value);
  try{
    const d=await api('/api/conversations/threads?'+qs.toString());
    $('threadsTable').innerHTML=(d.rows||[]).map(r=>`<tr data-thread="${escapeHtml(r.thread_id)}" data-channel="${escapeHtml(r.channel)}"><td><b>${escapeHtml(r.display_chat_id||r.thread_id)}</b><br><small>${escapeHtml(r.thread_id)}</small></td><td>${escapeHtml(r.display_phone||'غير متاح')}</td><td>${escapeHtml(r.country_code||'—')}</td><td>${escapeHtml(r.channel)}</td><td>${escapeHtml(r.last_ts)}</td><td>${escapeHtml(r.count)}</td></tr>`).join('')||'<tr><td colspan="6">لا توجد محادثات.</td></tr>';
    document.querySelectorAll('#threadsTable tr[data-thread]').forEach(row=>row.onclick=()=>loadThreadDetail(row.dataset.thread,row.dataset.channel));
  }catch(e){$('threadsTable').innerHTML='<tr><td colspan="6">خطأ: '+escapeHtml(e.message)+'</td></tr>';}
}
async function loadThreadDetail(id,channel){
  try{
    const qs=new URLSearchParams({limit:'200'}); if(channel) qs.set('channel',channel);
    const d=await api('/api/conversations/thread/'+encodeURIComponent(id)+'?'+qs.toString());
    const ident=d.identity||{}; const head=`<div class="muted-block"><b>بيانات المحادثة</b><br>Chat ID: ${escapeHtml(ident.display_chat_id||id)}<br>رقم الجوال: ${escapeHtml(ident.display_phone||'غير متاح')} ${ident.phone_source?`<small>(${escapeHtml(ident.phone_source)})</small>`:''}</div>`; $('threadDetail').innerHTML=head+((d.rows||[]).map(r=>`<div class="thread-msg"><small>${escapeHtml(r.ts)} · ${escapeHtml(r.channel)}</small><b>${escapeHtml(r.question||'—')}</b><pre>${escapeHtml(r.answer||'')}</pre></div>`).join('')||'لا توجد رسائل.');
  }catch(e){$('threadDetail').textContent='خطأ: '+e.message;}
}
if($('loadThreadsBtn')) $('loadThreadsBtn').onclick=loadThreads;

async function loadReview(){
  if(!hasPerm('review')) return;
  const qs=new URLSearchParams({limit:'200'}); if($('reviewStatus')?.value) qs.set('status',$('reviewStatus').value);
  try{
    const d=await api('/api/review/items?'+qs.toString());
    $('reviewList').innerHTML=(d.rows||[]).map(r=>`<div class="review-item"><div><b>${escapeHtml(r.reason)}</b><small>${escapeHtml(r.ts)} · ${escapeHtml(r.status)}</small></div><p><b>السؤال:</b> ${escapeHtml(r.question||'')}</p><pre>${escapeHtml(cleanPreviewText(r.answer||'',600))}</pre><div class="btn-row"><button data-review="${escapeHtml(r.id)}" data-status="correct">صحيح</button><button data-review="${escapeHtml(r.id)}" data-status="needs_fix">يحتاج تعديل</button><button class="danger" data-review="${escapeHtml(r.id)}" data-status="wrong">خطأ</button></div></div>`).join('')||'<div class="muted-block">لا توجد عناصر مراجعة.</div>';
    document.querySelectorAll('[data-review]').forEach(b=>b.onclick=async()=>{await api(`/api/review/${encodeURIComponent(b.dataset.review)}/mark`,{method:'POST',body:JSON.stringify({status:b.dataset.status})});await loadReview();});
  }catch(e){$('reviewList').innerHTML='<div class="muted-block">خطأ: '+escapeHtml(e.message)+'</div>';}
}
if($('loadReviewBtn')) $('loadReviewBtn').onclick=loadReview;

if($('downloadBackupBtn')) $('downloadBackupBtn').onclick=()=>{const inc=$('backupIncludeSecrets')?.checked?'true':'false'; window.location.href='/api/backup/export?include_secrets='+inc;};
if($('importBackupBtn')) $('importBackupBtn').onclick=async()=>{
  const f=$('backupFile')?.files?.[0]; if(!f){$('backupResult').textContent='اختر ملف JSON أولًا';return;}
  try{const txt=await f.text(); const payload=JSON.parse(txt); const r=await api('/api/backup/import',{method:'POST',body:JSON.stringify({payload})});$('backupResult').textContent=JSON.stringify(r,null,2);}
  catch(e){$('backupResult').textContent='خطأ: '+e.message;}
};

async function loadLoginAttempts(){
  if(!hasPerm('security')) return;
  try{const d=await api('/api/login-attempts?limit=200');$('loginAttemptsTable').innerHTML=(d.rows||[]).map(r=>`<tr><td>${escapeHtml(r.ts)}</td><td>${escapeHtml(r.username)}</td><td>${r.success?'نجح':'فشل'}</td><td>${escapeHtml(r.ip)}</td><td>${escapeHtml(r.message)}</td></tr>`).join('')||'<tr><td colspan="5">لا توجد محاولات.</td></tr>';}
  catch(e){$('loginAttemptsTable').innerHTML='<tr><td colspan="5">خطأ: '+escapeHtml(e.message)+'</td></tr>';}
}
if($('loadLoginAttemptsBtn')) $('loadLoginAttemptsBtn').onclick=loadLoginAttempts;
if($('changePasswordBtn')) $('changePasswordBtn').onclick=async()=>{
  try{const r=await api('/api/users/change-password',{method:'POST',body:JSON.stringify({current_password:$('currentPassword').value,new_password:$('newPassword').value})});$('passwordResult').textContent='تم تغيير كلمة المرور بنجاح';$('currentPassword').value='';$('newPassword').value='';}
  catch(e){$('passwordResult').textContent='خطأ: '+e.message;}
};

async function loadModeIntoServices(){
  try{const d=await api('/api/operational/mode'); const el=$('replyMode'); if(el) el.value=d.mode||'active';}catch{}
}
(async function boot(){
  initDateControls();
  await loadMe();
  await loadSettings().catch(()=>{});
  await refreshAll();
  await loadModeIntoServices().catch(()=>{});
  setInterval(()=>{loadStats();loadServices();loadRecent();loadNotifications(false);},8000);
})();

if($('replyMode')) $('replyMode').onchange=async()=>{try{await api('/api/operational/mode',{method:'POST',body:JSON.stringify({mode:$('replyMode').value})});await loadNotifications(false);}catch(e){alert('خطأ: '+e.message);}};
