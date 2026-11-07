const $ = (sel) => document.querySelector(sel);

// --- вкладки ---
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
  });
});

const fmt = (n, d = 2) =>
  n == null ? "—" : Number(n).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Ошибка ${res.status}: ${await res.text()}`);
  return res.json();
}

function moexLink(secid, board) {
  return `https://www.moex.com/ru/issue.aspx?code=${secid}`;
}

// --- статус ---
async function loadStatus() {
  try {
    const h = await (await fetch("/api/health")).json();
    $("#keyRate").textContent = fmt(h.key_rate, 1);
  } catch { $("#dataStatus").textContent = "API недоступен"; }
}
loadStatus();

async function doSync() {
  const btn = event.target;
  btn.disabled = true; btn.textContent = "Синхронизация…";
  try {
    const r = await api("/api/sync", {});
    $("#dataStatus").textContent = `Обновлено: ${r.bonds} облигаций, ${r.shares} акций`;
    loadStatus();
  } catch (e) {
    $("#dataStatus").textContent = "Ошибка синхронизации";
  } finally {
    btn.disabled = false; btn.textContent = "Обновить данные";
  }
}

// --- облигации ---
$("#bondsForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const body = {
    min_yield: +f.get("min_yield"),
    max_duration: Math.round(+f.get("max_duration_years") * 365),
    min_liquidity: +f.get("min_liq_mln") * 1e6,
    max_price: +f.get("max_price"),
    list_level: +f.get("list_level"),
    exclude_floating: !!f.get("exclude_floating"),
    exclude_offers: !!f.get("exclude_offers"),
    only_ofz: !!f.get("only_ofz"),
    limit: 200,
  };
  $("#bondsResult").innerHTML = "<p class='muted'>Загрузка…</p>";
  try {
    const r = await api("/api/bonds", body);
    renderBonds(r.items, r.key_rate);
  } catch (err) {
    $("#bondsResult").innerHTML = `<p class="muted">Ошибка: ${err.message}</p>`;
  }
});

function renderBonds(items, keyRate) {
  if (!items.length) {
    $("#bondsResult").innerHTML = "<p class='muted'>Ничего не найдено по заданным фильтрам.</p>";
    return;
  }
  const rows = items.map(b => `
    <tr>
      <td><a href="${moexLink(b.secid)}" target="_blank">${b.secid}</a><br>
          <span class="muted">${b.shortname}</span>
          ${b.is_ofz ? '<span class="badge">ОФЗ</span>' : ""}
          ${b.flags.floating ? '<span class="badge">флоатер</span>' : ""}
          ${b.flags.offer ? '<span class="badge">оферта</span>' : ""}</td>
      <td class="num">${fmt(b.price)}</td>
      <td class="num yield">${fmt(b.yield)}</td>
      <td class="num">${fmt(b.yield - (keyRate || 0))}</td>
      <td class="num">${fmt(b.duration_years, 1)}</td>
      <td class="num">${fmt(b.coupon_percent, 1)}</td>
      <td class="num">${fmt(b.accr_int)}</td>
      <td>${b.mat_date || "—"}</td>
      <td class="num">${(b.val_today / 1e6).toFixed(1)} млн</td>
    </tr>`).join("");
  $("#bondsResult").innerHTML = `
    <p class="muted">Найдено: ${items.length}</p>
    <table><thead><tr>
      <th>Бумага</th><th>Цена, %</th><th>Доходность, %</th><th>к ставке, п.п.</th>
      <th>Дюрация, лет</th><th>Купон, %</th><th>НКД</th><th>Погашение</th><th>Оборот</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

// --- акции ---
$("#sharesForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const body = {
    min_div_yield: +f.get("min_div_yield"),
    min_liquidity: +f.get("min_liq_mln") * 1e6,
    list_level: +f.get("list_level"),
    limit: 100,
  };
  $("#sharesResult").innerHTML = "<p class='muted'>Загрузка…</p>";
  try {
    const r = await api("/api/shares", body);
    renderShares(r.items);
  } catch (err) {
    $("#sharesResult").innerHTML = `<p class="muted">Ошибка: ${err.message}</p>`;
  }
});

function renderShares(items) {
  if (!items.length) {
    $("#sharesResult").innerHTML = "<p class='muted'>Ничего не найдено.</p>";
    return;
  }
  const rows = items.map(s => `
    <tr>
      <td><a href="${moexLink(s.secid)}" target="_blank">${s.secid}</a><br>
          <span class="muted">${s.shortname}</span></td>
      <td class="num">${fmt(s.price)}</td>
      <td class="num yield">${fmt(s.div_yield_12m)}</td>
      <td class="num">${fmt(s.dividends_12m)}</td>
      <td class="num">${fmt(s.lot_cost, 0)}</td>
      <td class="num">${(s.val_today / 1e6).toFixed(0)} млн</td>
    </tr>`).join("");
  $("#sharesResult").innerHTML = `
    <p class="muted">Найдено: ${items.length}. Див. доходность — по выплатам за последние 12 месяцев к текущей цене.</p>
    <table><thead><tr>
      <th>Бумага</th><th>Цена, ₽</th><th>Див. доходность, %</th><th>Дивиденды 12м, ₽</th>
      <th>Стоимость лота, ₽</th><th>Оборот</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

// --- портфель ---
$("#portfolioForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  $("#portfolioResult").innerHTML = "<p class='muted'>Подбираем…</p>";
  try {
    const r = await api("/api/portfolio", {
      profile: f.get("profile"),
      amount: +f.get("amount"),
    });
    renderPortfolio(r);
  } catch (err) {
    $("#portfolioResult").innerHTML = `<p class="muted">Ошибка: ${err.message}</p>`;
  }
});

function renderPortfolio(r) {
  $("#portfolioDesc").textContent = r.description;
  const bondRows = r.bonds.map(b => `
    <tr>
      <td><a href="${moexLink(b.secid)}" target="_blank">${b.secid}</a><br>
          <span class="muted">${b.shortname}</span>${b.is_ofz ? ' <span class="badge">ОФЗ</span>' : ""}</td>
      <td class="num">${b.weight}%</td>
      <td class="num">${fmt(b.amount, 0)}</td>
      <td class="num">${b.approx_qty}</td>
      <td class="num yield">${fmt(b.yield)}</td>
      <td class="num">${fmt(b.duration_years, 1)}</td>
      <td>${b.mat_date || "—"}</td>
    </tr>`).join("");
  const shareRows = r.shares.map(s => `
    <tr>
      <td><a href="${moexLink(s.secid)}" target="_blank">${s.secid}</a><br>
          <span class="muted">${s.shortname}</span></td>
      <td class="num">${s.weight}%</td>
      <td class="num">${fmt(s.amount, 0)}</td>
      <td class="num">${s.approx_qty}</td>
      <td class="num">${fmt(s.price, 2)}</td>
      <td class="num yield">${fmt(s.div_yield_12m)}</td>
    </tr>`).join("");

  $("#portfolioResult").innerHTML = `
    <div class="summary">
      <div class="stat"><div class="v yield">${fmt(r.expected_yield)}%</div><div class="k">Ожидаемая доходность портфеля</div></div>
      <div class="stat"><div class="v">${fmt(r.expected_income_year, 0)} ₽</div><div class="k">Ожидаемый доход за год</div></div>
      <div class="stat"><div class="v">${fmt(r.key_rate, 1)}%</div><div class="k">Ключевая ставка ЦБ (бенчмарк)</div></div>
    </div>
    ${r.bonds.length ? `<h3>Облигации (${r.bonds.length})</h3>
    <table><thead><tr><th>Бумага</th><th>Доля</th><th>Сумма, ₽</th><th>Кол-во</th><th>Доходн., %</th><th>Дюрация, лет</th><th>Погашение</th></tr></thead>
    <tbody>${bondRows}</tbody></table>` : ""}
    ${r.shares.length ? `<h3>Акции (${r.shares.length})</h3>
    <table><thead><tr><th>Бумага</th><th>Доля</th><th>Сумма, ₽</th><th>Кол-во</th><th>Цена, ₽</th><th>Див. доходн., %</th></tr></thead>
    <tbody>${shareRows}</tbody></table>` : ""}
    <p class="muted" style="margin-top:14px">${r.disclaimer}</p>`;
}
