(function () {
  const KEY = 'snmp_prefs';
  const TEXT_IDS = ['host', 'username', 'auth_password', 'port', 'root_oid', 'timeout', 'total_timeout', 'bulk_size'];
  const CHECK_IDS = ['pinpoint'];

  function save() {
    const prefs = {};
    TEXT_IDS.forEach(id => { const el = document.getElementById(id); if (el) prefs[id] = el.value; });
    CHECK_IDS.forEach(id => { const el = document.getElementById(id); if (el) prefs[id] = el.checked; });
    try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch {}
  }

  function load() {
    let prefs;
    try { prefs = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { return; }
    TEXT_IDS.forEach(id => { const el = document.getElementById(id); if (el && prefs[id] !== undefined) el.value = prefs[id]; });
    CHECK_IDS.forEach(id => { const el = document.getElementById(id); if (el && prefs[id] !== undefined) el.checked = prefs[id]; });
  }

  document.addEventListener('DOMContentLoaded', () => {
    load();
    [...TEXT_IDS, ...CHECK_IDS].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', save);
    });
  });
})();
