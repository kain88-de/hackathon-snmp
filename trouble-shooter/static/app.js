const form = document.getElementById("check-form");
const results = document.getElementById("results");

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const host = document.getElementById("host").value.trim();
  const community = document.getElementById("community").value.trim();

  results.hidden = false;
  results.replaceChildren();

  let data;
  try {
    const resp = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, community }),
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
  addRow(table, "SNMP (UDP 161)", reachableEl(data.snmp.reachable));
  if (data.snmp.sysDescr) addRow(table, "sysDescr", textEl(data.snmp.sysDescr));
  if (data.snmp.error)    addRow(table, "Error", errorEl(data.snmp.error));
  results.appendChild(table);
});

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
