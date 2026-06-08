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
  // TODO: populate tree / table / raw views with real data
  console.log("walk result", oids);
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
