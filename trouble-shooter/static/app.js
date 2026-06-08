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
  const community = document.getElementById("community").value.trim();
  const port = parseInt(document.getElementById("port").value, 10);

  results.hidden = false;
  results.replaceChildren();

  let data;
  try {
    const resp = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, community, port }),
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
    doWalk(host, community, port);
  }
});

async function doWalk(host, community, port) {
  try {
    const resp = await fetch("/api/walk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, community, port }),
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
  ["OID", "Value"].forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  const tbody = table.createTBody();
  oids.forEach(({ oid, value }) => {
    const tr = tbody.insertRow();
    tr.insertCell().textContent = oid;
    tr.insertCell().textContent = value;
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
