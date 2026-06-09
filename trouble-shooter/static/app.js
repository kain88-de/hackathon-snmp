const form = document.getElementById("check-form");
const results = document.getElementById("results");
const walkSection = document.getElementById("walk-section");

// View toggle
document.querySelectorAll(".view-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".view-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view-pane").forEach((p) => { p.hidden = true; });
    btn.classList.add("active");
    document.getElementById(`view-${btn.dataset.view}`).hidden = false;
  });
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const host = document.getElementById("host").value.trim();
  const username = document.getElementById("username").value.trim();
  const auth_password = document.getElementById("auth_password").value;
  const port = parseInt(document.getElementById("port").value, 10);

  results.hidden = false;
  results.replaceChildren();

  let data;
  try {
    const resp = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, username, auth_password, port }),
    });
    data = await resp.json();
  } catch (err) {
    results.appendChild(errorEl(`Request failed: ${err.message}`));
    return;
  }

  const h2 = document.createElement("h2");
  h2.textContent = `Results for ${data.host}`;
  results.appendChild(h2);

  const table = document.createElement("table");
  addRow(table, "Ping", reachableEl(data.ping));
  addRow(table, `SNMP (UDP ${port})`, reachableEl(data.snmp.reachable));
  if (data.snmp.sysDescr) addRow(table, "sysDescr", textEl(data.snmp.sysDescr));
  if (data.snmp.error)    addRow(table, "Error", errorEl(data.snmp.error));
  results.appendChild(table);

  if (data.snmp.reachable) {
    walkSection.hidden = false;
    doWalk(host, username, auth_password, port);
  }
});

async function doWalk(host, username, auth_password, port) {
  try {
    const resp = await fetch("/api/walk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, username, auth_password, port }),
    });
    const data = await resp.json();
    renderWalk(data.oids);
  } catch (err) {
    renderWalkError(err.message);
  }
}

function renderWalk(oids) {
  renderWalkTable(oids);
  renderWalkRaw(oids);
  renderWalkTree(oids);
}

function renderWalkTable(oids) {
  const pane = document.getElementById("view-table");
  pane.replaceChildren();
  const table = document.createElement("table");
  const thead = table.createTHead();
  const hr = thead.insertRow();
  ["OID", "Value", "ms"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  const tbody = table.createTBody();
  oids.forEach(({ oid, value, ms }) => {
    const tr = tbody.insertRow();
    tr.insertCell().textContent = oid;
    tr.insertCell().textContent = value;
    const msCell = tr.insertCell();
    msCell.textContent = ms;
    if (ms > 500) msCell.className = "slow";
  });
  pane.appendChild(table);
}

function renderWalkRaw(oids) {
  const pane = document.getElementById("view-raw");
  pane.replaceChildren();
  const pre = document.createElement("pre");
  pre.className = "raw-output";
  const obj = Object.fromEntries(oids.map(({ oid, value }) => [oid, value]));
  pre.textContent = JSON.stringify(obj, null, 2);
  pane.appendChild(pre);
}

function renderWalkTree(oids) {
  const pane = document.getElementById("view-tree");
  pane.replaceChildren();

  // Build a prefix tree from dotted OID strings
  const root = {};
  oids.forEach(({ oid, value }) => {
    const parts = oid.split(".");
    let node = root;
    parts.forEach((part) => {
      node[part] = node[part] || { _children: {}, _value: null };
      node = node[part]._children;
    });
    // attach value to the leaf
    let leaf = root;
    parts.forEach((part, i) => {
      if (i < parts.length - 1) leaf = leaf[part]._children;
      else leaf[part]._value = value;
    });
  });

  pane.appendChild(buildTreeUl(root, ""));
}

function buildTreeUl(nodes, prefix) {
  const ul = document.createElement("ul");
  ul.className = "oid-tree";
  Object.entries(nodes).forEach(([part, node]) => {
    const oid = prefix ? `${prefix}.${part}` : part;
    const li = document.createElement("li");
    li.className = "oid-node";

    const label = document.createElement("span");
    label.className = "oid-label";
    label.textContent = oid;
    li.appendChild(label);

    if (node._value !== null) {
      const val = document.createElement("span");
      val.className = "oid-value";
      val.textContent = node._value;
      li.appendChild(val);
    }

    const childKeys = Object.keys(node._children);
    if (childKeys.length) {
      const childUl = buildTreeUl(node._children, oid);
      li.appendChild(childUl);
    }

    ul.appendChild(li);
  });
  return ul;
}

function renderWalkError(msg) {
  document.getElementById("view-tree").appendChild(errorEl(`Walk failed: ${msg}`));
}

function addRow(table, label, valueEl) {
  const tr = table.insertRow();
  const th = document.createElement("th");
  th.textContent = label;
  tr.appendChild(th);
  const td = tr.insertCell();
  td.appendChild(valueEl);
}

function reachableEl(ok) {
  const span = document.createElement("span");
  span.className = ok ? "ok" : "fail";
  span.textContent = ok ? "✓ reachable" : "✗ unreachable";
  return span;
}

function textEl(text) {
  const span = document.createElement("span");
  span.textContent = text;
  return span;
}

function errorEl(msg) {
  const span = document.createElement("span");
  span.className = "error";
  span.textContent = msg;
  return span;
}

// ---------------------------------------------------------------------------
// Diagnose: /api/diagnose — find and classify slow / dropped OIDs
// ---------------------------------------------------------------------------

const diagnoseBtn = document.getElementById("diagnose-btn");
const diagnoseSection = document.getElementById("diagnose-section");
const diagStatus = document.getElementById("diag-status");
const diagSummary = document.getElementById("diag-summary");

// Buckets returned by the engine. "TIMEOUT" is synthesised server-side for
// dropped requests; the rest come from the default bucket config.
const BUCKET_COLORS = {
  OK: "#2a7a2a",
  SLOW: "#e67e22",
  CRITICAL: "#c0392b",
  TIMEOUT: "#7d3c98",
};
const BUCKET_ORDER = ["OK", "SLOW", "CRITICAL", "TIMEOUT"];

function bucketColor(name) {
  return BUCKET_COLORS[name] || "#6b7280";
}

// Scoped view toggle for the diagnose section (independent of the walk toggle).
document.querySelectorAll(".dview-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".dview-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".dview-pane").forEach((p) => { p.hidden = true; });
    btn.classList.add("active");
    document.getElementById(`dview-${btn.dataset.dview}`).hidden = false;
  });
});

diagnoseBtn.addEventListener("click", () => {
  const body = {
    host: document.getElementById("host").value.trim(),
    username: document.getElementById("username").value.trim(),
    auth_password: document.getElementById("auth_password").value,
    port: parseInt(document.getElementById("port").value, 10),
    root_oid: document.getElementById("root_oid").value.trim(),
    timeout: parseFloat(document.getElementById("timeout").value),
    total_timeout: parseFloat(document.getElementById("total_timeout").value),
    retries: 1,
    pinpoint: document.getElementById("pinpoint").checked,
  };
  runDiagnose(body);
});

async function runDiagnose(body) {
  diagnoseSection.hidden = false;
  diagStatus.replaceChildren(textEl("Diagnosing… this can take a while when pinpoint is on."));
  diagSummary.replaceChildren();
  ["chart", "regions", "oids", "raw"].forEach((v) => {
    document.getElementById(`dview-${v}`).replaceChildren();
  });
  diagnoseBtn.disabled = true;

  let resp;
  let data;
  try {
    resp = await fetch("/api/diagnose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    data = await resp.json();
  } catch (err) {
    diagStatus.replaceChildren(errorEl(`Request failed: ${err.message}`));
    diagnoseBtn.disabled = false;
    return;
  } finally {
    diagnoseBtn.disabled = false;
  }

  if (!resp.ok) {
    diagStatus.replaceChildren(errorEl(data.detail || `HTTP ${resp.status}`));
    return;
  }

  renderDiagStatus(data);
  renderDiagSummary(data.summary);
  renderDiagChart(data.oids);
  renderDiagRegions(data.regions);
  renderDiagOids(data.oids);
  renderDiagRaw(data);
}

function renderDiagStatus(d) {
  diagStatus.replaceChildren();
  const banner = document.createElement("div");
  banner.className = `diag-banner ${d.complete ? "ok" : "fail"}`;

  const verdict = document.createElement("strong");
  verdict.textContent = d.complete
    ? "✓ Walk complete"
    : `✗ Walk incomplete — ${d.reason}`;
  banner.appendChild(verdict);

  const meta = document.createElement("span");
  meta.className = "diag-banner-meta";
  const elapsed = `${(d.elapsed_total_ms / 1000).toFixed(1)}s`;
  meta.textContent = d.complete
    ? `reason: ${d.reason} · stopped at ${d.stopped_at} · ${elapsed}`
    : `stopped at ${d.stopped_at} · ${elapsed}`;
  banner.appendChild(meta);

  diagStatus.appendChild(banner);
}

function renderDiagSummary(summary) {
  diagSummary.replaceChildren();
  const wrap = document.createElement("div");
  wrap.className = "chips";

  const names = Object.keys(summary).sort(
    (a, b) => (BUCKET_ORDER.indexOf(a) + 1 || 99) - (BUCKET_ORDER.indexOf(b) + 1 || 99),
  );
  names.forEach((name) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.style.borderColor = bucketColor(name);
    const dot = document.createElement("span");
    dot.className = "chip-dot";
    dot.style.background = bucketColor(name);
    chip.appendChild(dot);
    const label = document.createElement("span");
    label.textContent = `${name} ${summary[name]}`;
    chip.appendChild(label);
    wrap.appendChild(chip);
  });
  diagSummary.appendChild(wrap);
}

function renderDiagChart(oids) {
  const pane = document.getElementById("dview-chart");
  pane.replaceChildren();

  if (!oids.length) {
    pane.appendChild(textEl("No OIDs returned."));
    return;
  }

  // Filter control: focus on the actionable (non-OK) OIDs.
  const controls = document.createElement("label");
  controls.className = "checkbox chart-filter";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  controls.appendChild(cb);
  controls.appendChild(document.createTextNode(" Show only slow / timed-out OIDs"));
  pane.appendChild(controls);

  const chart = document.createElement("div");
  chart.className = "waterfall";
  pane.appendChild(chart);

  const maxMs = Math.max(...oids.map((o) => o.ms), 1);

  const draw = () => {
    const rows = cb.checked ? oids.filter((o) => o.bucket !== "OK") : oids;
    chart.innerHTML = rows
      .map((o) => {
        const pct = Math.max((o.ms / maxMs) * 100, 1).toFixed(1);
        const color = bucketColor(o.bucket);
        return `
          <div class="wf-row" title="${esc(o.oid)}\n${esc(o.value || "(empty)")}\n${o.bucket} · ${Math.round(o.ms)} ms · ${esc(o.phase)}">
            <span class="wf-phase ${o.phase === "pinpoint" ? "pin" : ""}">${esc(o.phase)}</span>
            <span class="wf-oid">${esc(o.oid)}</span>
            <span class="wf-bar-cell"><span class="wf-bar" style="width:${pct}%;background:${color}"></span></span>
            <span class="wf-ms" style="color:${color}">${Math.round(o.ms)}</span>
          </div>`;
      })
      .join("") || `<div class="stub">No slow or timed-out OIDs.</div>`;
  };

  cb.addEventListener("change", draw);
  draw();
}

function renderDiagRegions(regions) {
  const pane = document.getElementById("dview-regions");
  pane.replaceChildren();

  if (!regions.length) {
    pane.appendChild(textEl("No slow regions detected."));
    return;
  }

  const table = document.createElement("table");
  const hr = table.createTHead().insertRow();
  ["Prefix", "Worst bucket", "Batch ms", "OIDs"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  const tbody = table.createTBody();
  regions.forEach((r) => {
    const tr = tbody.insertRow();
    tr.insertCell().textContent = r.prefix;
    const bucketCell = tr.insertCell();
    bucketCell.textContent = r.bucket;
    bucketCell.style.color = bucketColor(r.bucket);
    bucketCell.style.fontWeight = "600";
    tr.insertCell().textContent = Math.round(r.batch_ms);
    tr.insertCell().textContent = r.oid_count;
  });
  pane.appendChild(table);
}

function renderDiagOids(oids) {
  const pane = document.getElementById("dview-oids");
  pane.replaceChildren();

  const table = document.createElement("table");
  const hr = table.createTHead().insertRow();
  ["OID", "Value", "Bucket", "ms", "Phase"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  const tbody = table.createTBody();
  oids.forEach((o) => {
    const tr = tbody.insertRow();
    tr.insertCell().textContent = o.oid;
    tr.insertCell().textContent = o.value;
    const bucketCell = tr.insertCell();
    bucketCell.textContent = o.bucket;
    bucketCell.style.color = bucketColor(o.bucket);
    bucketCell.style.fontWeight = "600";
    tr.insertCell().textContent = Math.round(o.ms);
    tr.insertCell().textContent = o.phase;
  });
  pane.appendChild(table);
}

function renderDiagRaw(data) {
  const pane = document.getElementById("dview-raw");
  pane.replaceChildren();
  const pre = document.createElement("pre");
  pre.className = "raw-output";
  pre.textContent = JSON.stringify(data, null, 2);
  pane.appendChild(pre);
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
