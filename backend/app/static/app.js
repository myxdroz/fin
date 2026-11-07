const $ = (sel) => document.querySelector(sel);

// --- вкладки ---
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "my") loadMyPortfolio();
    if (btn.dataset.tab === "goals") loadGoals();
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
          <span class="muted">${s.shortname}</span>
          ${s.imoex_weight != null ? `<span class="badge">IMOEX ${s.imoex_weight}%</span>` : ""}</td>
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

// --- мой портфель (Т-Банк) ---
let myAccountId = null;

async function loadMyPortfolio() {
  $("#myPortfolioResult").innerHTML = "<p class='muted'>Загрузка…</p>";
  let accounts;
  try {
    accounts = (await (await fetch("/api/my/accounts")).json()).accounts;
  } catch (e) {
    $("#myPortfolioResult").innerHTML = `<p class="muted">Не удалось получить счета: ${e.message}</p>`;
    return;
  }
  if (!accounts.length) {
    $("#myPortfolioResult").innerHTML = "<p class='muted'>Счета не найдены.</p>";
    return;
  }
  myAccountId = myAccountId || accounts[0].id;
  $("#myAccounts").innerHTML = `
    <label>Счёт
      <select id="accountSelect">
        ${accounts.map(a => `<option value="${a.id}" ${a.id === myAccountId ? "selected" : ""}>${a.name || a.id} (${a.type})</option>`).join("")}
      </select>
    </label>
    <button onclick="reloadMyPortfolio()" class="btn-secondary">Обновить</button>`;
  $("#accountSelect").addEventListener("change", e => {
    myAccountId = e.target.value;
    reloadMyPortfolio();
  });
  await reloadMyPortfolio();
}

async function reloadMyPortfolio() {
  $("#myPortfolioResult").innerHTML = "<p class='muted'>Загрузка позиций…</p>";
  let pf;
  try {
    const res = await fetch(`/api/my/portfolio?account_id=${myAccountId}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    pf = await res.json();
  } catch (e) {
    $("#myPortfolioResult").innerHTML = `<p class="muted">${e.message}</p>`;
    return;
  }
  renderMyPortfolio(pf);
  // календарь выплат — фоном
  try {
    const res = await fetch(`/api/my/income?account_id=${myAccountId}`);
    if (res.ok) renderIncome(await res.json());
  } catch { /* календарь не критичен */ }
}

function renderMyPortfolio(pf) {
  const rows = pf.positions.map(p => `
    <tr>
      <td>${p.ticker ? `<b>${p.ticker}</b><br>` : ""}<span class="muted">${p.name}</span>
          <span class="badge">${p.type_label}</span></td>
      <td class="num">${p.quantity}</td>
      <td class="num">${fmt(p.avg_price, 2)}</td>
      <td class="num">${fmt(p.current_price, 2)}</td>
      <td class="num">${fmt(p.value, 0)}</td>
      <td class="num">${p.weight}%</td>
      <td class="num ${p.pnl >= 0 ? "yield" : ""}">${fmt(p.pnl, 0)} (${fmt(p.pnl_pct, 1)}%)</td>
    </tr>`).join("");
  $("#myPortfolioResult").innerHTML = `
    <div class="summary">
      <div class="stat"><div class="v">${fmt(pf.total, 0)} ₽</div><div class="k">Стоимость портфеля</div></div>
      <div class="stat"><div class="v">${fmt(pf.total_shares, 0)} ₽</div><div class="k">Акции</div></div>
      <div class="stat"><div class="v">${fmt(pf.total_bonds, 0)} ₽</div><div class="k">Облигации</div></div>
      <div class="stat"><div class="v">${fmt(pf.total_etf || 0, 0)} ₽</div><div class="k">ETF</div></div>
      <div class="stat"><div class="v">${fmt(pf.total_currencies, 0)} ₽</div><div class="k">Деньги</div></div>
      <div class="stat"><div class="v ${pf.expected_yield >= 0 ? "yield" : ""}">${fmt(pf.expected_yield, 0)} ₽</div><div class="k">Нереализованный результат</div></div>
    </div>
    <table><thead><tr>
      <th>Бумага</th><th>Кол-во</th><th>Ср. цена</th><th>Тек. цена</th><th>Стоимость, ₽</th><th>Доля</th><th>P&L</th>
    </tr></thead><tbody>${rows}</tbody></table>
    <div id="incomeCalendar"></div>`;
}

function renderIncome(cal) {
  if (!cal.events.length) {
    $("#incomeCalendar").innerHTML = "<p class='muted' style='margin-top:14px'>Объявленных выплат на ближайшие 45 дней нет.</p>";
    return;
  }
  const rows = cal.events.map(e => `
    <tr>
      <td>${e.date}</td>
      <td><span class="badge">${e.kind}</span> <b>${e.ticker}</b></td>
      <td class="num yield">${fmt(e.amount, 0)} ₽</td>
    </tr>`).join("");
  $("#incomeCalendar").innerHTML = `
    <h3>Выплаты на 45 дней: ${fmt(cal.total, 0)} ₽</h3>
    <table><thead><tr><th>Дата</th><th>Выплата</th><th>Сумма, ₽</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// --- цели ---
const SECTOR_COLORS = {
  "Нефтегаз": "#f59e0b", "Добыча": "#84cc16", "Индустрия": "#64748b",
  "Потребление вторичное": "#ec4899", "Потребление первичное": "#f472b6",
  "Здоровье": "#14b8a6", "Финансы": "#3b82f6", "Технологии": "#8b5cf6",
  "Телеком и Медиа": "#06b6d4", "Коммунальные": "#22c55e", "Недвижимость": "#a16207",
  "ОФЗ": "#e2e8f0", "Корп. облигации": "#94a3b8", "ETF": "#6366f1", "Валюта": "#eab308",
  "Прочее": "#71717a",
};

async function loadGoals() {
  $("#goalsResult").innerHTML = "<p class='muted'>Загрузка…</p>";
  let g;
  try {
    const res = await fetch("/api/goals");
    if (!res.ok) throw new Error(`Ошибка ${res.status}`);
    g = await res.json();
  } catch (e) {
    $("#goalsResult").innerHTML = `<p class="muted">Ошибка: ${e.message}</p>`;
    return;
  }
  $("#capitalGoalInput").value = g.capital_goal;
  $("#goalAssumption").textContent =
    `Цель дохода считается как: ${g.goal_income.assumption} → ${g.goal_income.annual_pct}% годовых`;

  const cur = g.current || {};
  const curValue = cur.value != null ? `${fmt(cur.value, 0)} ₽` : "—";
  const curIncome = cur.income_month != null ? `${fmt(cur.income_month, 0)} ₽` : "—";
  const bar = (pct) => {
    if (pct == null) return "<div class='muted'>нет данных</div>";
    const w = Math.min(pct, 100);
    return `<div class="progress"><div class="progress-fill" style="width:${w}%"></div></div>
            <span class="muted">${fmt(pct, 1)}%</span>`;
  };

  $("#goalsResult").innerHTML = `
    <div class="summary">
      <div class="stat"><div class="v">${fmt(g.goal_income.monthly, 0)} ₽</div><div class="k">Цель: доход в месяц</div></div>
      <div class="stat"><div class="v">${curIncome}</div><div class="k">Текущий доход в месяц</div></div>
      <div class="stat"><div class="v">${curValue}</div><div class="k">Текущая стоимость портфеля</div></div>
    </div>
    ${cur.error ? `<p class="muted">${cur.error}</p>` : ""}
    <div class="card">
      <h3>Достижение цели</h3>
      <table class="goals-table">
        <tr><td style="width:40%">Капитал: ${curValue} / ${fmt(g.capital_goal, 0)} ₽</td>
            <td>${bar(g.progress_capital_pct)}</td></tr>
        <tr><td>Доход: ${curIncome} / ${fmt(g.goal_income.monthly, 0)} ₽</td>
            <td>${bar(g.progress_income_pct)}</td></tr>
      </table>
    </div>
    <div id="sectorChart"></div>`;

  if (cur.sectors && cur.sectors.length) {
    renderDonut(cur.sectors);
  } else if (!cur.error) {
    $("#sectorChart").innerHTML = "<p class='muted'>Диаграмма по отраслям появится после пополнения портфеля.</p>";
  }
}

$("#goalsForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  await fetch("/api/goals/capital", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value: +$("#capitalGoalInput").value }),
  });
  loadGoals();
});

function renderDonut(sectors) {
  const size = 260, r = 90, cx = size / 2, cy = size / 2;
  const C = 2 * Math.PI * r;
  let offset = 0;
  const total = sectors.reduce((s, x) => s + x.value, 0) || 1;
  const circles = sectors.map(s => {
    const len = s.value / total * C;
    const c = `<circle r="${r}" cx="${cx}" cy="${cy}" fill="none"
      stroke="${SECTOR_COLORS[s.name] || "#71717a"}" stroke-width="38"
      stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-offset}"
      transform="rotate(-90 ${cx} ${cy})"><title>${s.name}: ${fmt(s.pct, 1)}%</title></circle>`;
    offset += len;
    return c;
  }).join("");
  const legend = sectors.map(s => `
    <div class="legend-row">
      <span class="legend-swatch" style="background:${SECTOR_COLORS[s.name] || "#71717a"}"></span>
      ${s.name} — ${fmt(s.pct, 1)}%
    </div>`).join("");
  $("#sectorChart").innerHTML = `
    <div class="card">
      <h3>Структура портфеля по видам деятельности</h3>
      <div class="donut-wrap">
        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${circles}
          <text x="${cx}" y="${cy - 4}" text-anchor="middle" class="donut-total">${fmt(total, 0)} ₽</text>
          <text x="${cx}" y="${cy + 16}" text-anchor="middle" class="donut-sub">всего</text>
        </svg>
        <div class="legend">${legend}</div>
      </div>
    </div>`;
}
