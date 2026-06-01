// SQL Server buttons hardening layer.
// This file is intentionally isolated from app.js so SQL buttons keep working
// even if another dashboard script fails before binding its handlers.
(function(){
  'use strict';
  const $ = (id) => document.getElementById(id);
  const BTN_MAP = {
    sqlTestBtn: ['/api/sqlserver/test', 'فحص الاتصال'],
    sqlInitBtn: ['/api/sqlserver/init', 'إنشاء القاعدة والجداول'],
    sqlSyncNowBtn: ['/api/sqlserver/sync-now', 'مزامنة الآن'],
    sqlBackupBtn: ['/api/sqlserver/backup', 'Backup الآن']
  };
  function val(id, def=''){
    const el=$(id); if(!el) return def;
    if(el.type === 'checkbox') return !!el.checked;
    return (el.value || def);
  }
  function collectSqlServerConfig(){
    const passwordEl = $('sqlPassword');
    return {
      enabled: !!val('sqlEnabled', false),
      sync_enabled: !!val('sqlSyncEnabled', true),
      host: String(val('sqlHost','')).trim(),
      port: String(val('sqlPort','1433')).trim(),
      database: String(val('sqlDatabase','MawarethAI')).trim(),
      auth_mode: String(val('sqlAuthMode','sql')).trim() || 'sql',
      username: String(val('sqlUsername','')).trim(),
      password: passwordEl ? passwordEl.value : '',
      driver: String(val('sqlDriver','ODBC Driver 18 for SQL Server')).trim() || 'ODBC Driver 18 for SQL Server',
      encrypt: !!val('sqlEncrypt', true),
      trust_server_certificate: !!val('sqlTrustCert', true),
      timeout_seconds: Number(val('sqlTimeout','10')) || 10,
      sync_interval_seconds: Number(val('sqlSyncInterval','30')) || 30,
      backup_dir: String(val('sqlBackupDir','C:\\MawarethAI_Backups')).trim() || 'C:\\MawarethAI_Backups'
    };
  }
  function setResult(text, ok=null){
    const box=$('sqlResult');
    if(!box) return;
    box.textContent = text;
    box.classList.remove('sql-ok','sql-error','sql-working');
    if(ok === true) box.classList.add('sql-ok');
    if(ok === false) box.classList.add('sql-error');
    if(ok === null) box.classList.add('sql-working');
    try{ box.scrollIntoView({behavior:'smooth', block:'center'}); }catch{}
  }
  function disableSqlButtons(disabled){
    Object.keys(BTN_MAP).forEach(id=>{const b=$(id); if(b) b.disabled=disabled;});
  }
  async function postJson(url, body){
    const r = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body || {})
    });
    const txt = await r.text();
    let data = null;
    try{ data = txt ? JSON.parse(txt) : {}; }catch{ data = {raw: txt}; }
    if(r.status === 401){ window.location.href='/login'; throw new Error('login_required'); }
    if(!r.ok){
      const detail = data && (data.detail || data.message || data.error || data.raw);
      throw new Error(detail || ('HTTP '+r.status));
    }
    return data;
  }
  function prettyResponse(data){
    if(!data || typeof data !== 'object') return String(data || '');
    const lines=[];
    if(data.ok === true) lines.push('✅ نجح التنفيذ');
    if(data.ok === false) lines.push('❌ فشل التنفيذ');
    if(data.message) lines.push('الرسالة: '+data.message);
    if(data.server) lines.push('السيرفر: '+data.server);
    if(data.database) lines.push('قاعدة البيانات: '+data.database);
    if(data.driver) lines.push('ODBC Driver: '+data.driver);
    if(data.error) lines.push('الخطأ: '+data.error);
    if(data.detail) lines.push('التفاصيل: '+data.detail);
    lines.push('\n--- الرد الفني الكامل ---');
    lines.push(JSON.stringify(data,null,2));
    return lines.join('\n');
  }
  async function runSqlAction(endpoint, label){
    const cfg = collectSqlServerConfig();
    if(!cfg.host || !cfg.port){
      setResult('خطأ: املأ Host و Port أولًا.', false);
      return;
    }
    if(cfg.auth_mode === 'sql' && !cfg.username){
      setResult('خطأ: املأ Username أو اختر Windows Integrated.', false);
      return;
    }
    setResult('جاري تنفيذ: '+label+' ...\nHost: '+cfg.host+'\nPort: '+cfg.port+'\nDatabase: '+cfg.database, null);
    disableSqlButtons(true);
    try{
      const data = await postJson(endpoint, {sqlserver: cfg});
      setResult(prettyResponse(data), !!data.ok);
      // Refresh notifications if the main dashboard function exists.
      try{ if(typeof window.loadNotifications === 'function') await window.loadNotifications(false); }catch{}
    }catch(e){
      setResult('خطأ أثناء '+label+':\n'+(e && e.message ? e.message : String(e)), false);
    }finally{
      disableSqlButtons(false);
    }
  }
  function bindSqlButtons(){
    Object.entries(BTN_MAP).forEach(([id, spec])=>{
      const b=$(id); if(!b) return;
      b.disabled=false;
      b.style.pointerEvents='auto';
      b.title='تم ربط الزر بواسطة طبقة SQL الآمنة';
    });
  }
  document.addEventListener('click', function(ev){
    const btn = ev.target && ev.target.closest ? ev.target.closest('button') : null;
    if(!btn || !BTN_MAP[btn.id]) return;
    ev.preventDefault();
    ev.stopPropagation();
    if(ev.stopImmediatePropagation) ev.stopImmediatePropagation();
    const [endpoint,label] = BTN_MAP[btn.id];
    runSqlAction(endpoint,label);
  }, true);
  document.addEventListener('DOMContentLoaded', bindSqlButtons);
  window.addEventListener('load', bindSqlButtons);
  window.runSqlServerDashboardAction = runSqlAction;
})();
