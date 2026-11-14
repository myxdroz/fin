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
    $("#appVersion").textContent = "v." + (h.version || "dev");
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
let lastPortfolio = null;
$("#portfolioForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  $("#portfolioResult").innerHTML = "<p class='muted'>Подбираем…</p>";
  try {
    const r = await api("/api/portfolio", {
      profile: f.get("profile"),
      amount: +f.get("amount"),
    });
    lastPortfolio = r;
    renderPortfolio(r);
  } catch (err) {
    $("#portfolioResult").innerHTML = `<p class="muted">Ошибка: ${err.message}</p>`;
  }
});

function renderPortfolio(r) {
  $("#portfolioDesc").textContent = r.description;
  const bondsTotal = r.bonds.reduce((s, b) => s + b.amount, 0);
  const sharesTotal = r.shares.reduce((s, x) => x.amount + s, 0);
  const bondRows = r.bonds.map(b => `
    <tr>
      <td><a href="${moexLink(b.secid)}" target="_blank">${b.secid}</a><br>
          <span class="muted">${b.shortname}</span>
          ${b.is_ofz ? ' <span class="badge">ОФЗ</span>' : ""}
          ${b.flags && b.flags.offer ? ` <span class="badge" title="Доходность посчитана до даты оферты">оферта ${b.offer_date || ""}</span>` : ""}
          ${b.flags && b.flags.floating ? ' <span class="badge" title="Купон привязан к ключевой ставке, пересматривается">флоатер</span>' : ""}
          ${b.flags && b.flags.amort ? ' <span class="badge">амортизация</span>' : ""}</td>
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
    <table><thead><tr><th>Бумага</th><th class="num" title="Доля внутри облигационной части портфеля">Доля*</th><th class="num">Сумма, ₽</th><th class="num">Кол-во</th><th class="num">Доходн., %</th><th class="num">Дюрация, лет</th><th>Погашение</th></tr></thead>
    <tbody>${bondRows}</tbody></table>` : ""}
    ${r.shares.length ? `<h3>Акции (${r.shares.length})</h3>
    <table><thead><tr><th>Бумага</th><th class="num" title="Доля внутри акционной части портфеля">Доля*</th><th class="num">Сумма, ₽</th><th class="num">Кол-во</th><th class="num">Цена, ₽</th><th class="num">Див. доходн., %</th></tr></thead>
    <tbody>${shareRows}</tbody></table>
    <p class="muted">* «Доля» — распределение внутри класса активов. Общая структура: облигации ${fmt(bondsTotal / r.amount * 100, 0)}% / акции ${fmt(sharesTotal / r.amount * 100, 0)}% от ${fmt(r.amount, 0)} ₽.${
      r.bonds.some(b => b.flags && b.flags.offer) ? " Доходность по бумагам с офертой посчитана до даты оферты." : ""
    }${
      r.bonds.some(b => b.flags && b.flags.floating) ? " Флоатеры: доходность условна (купон пересматривается со ставкой)." : ""
    }</p>` : ""}
    <p class="muted" style="margin-top:14px">${r.disclaimer}</p>
    <button class="btn-secondary" onclick="exportPortfolioCSV()">Экспорт CSV</button>`;
}

// --- мой портфель (Т-Банк) ---
let myAccountId = null;

async function loadMyPortfolio() {
  $("#myPortfolioResult").innerHTML = "<p class='muted'>Загрузка…</p>";
  let accounts;
  try {
    const res = await fetch("/api/my/accounts");
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      $("#myAccounts").innerHTML = "";
      $("#myPortfolioResult").innerHTML = `
        <div class="card">
          <h2>Токен T-Invest не настроен</h2>
          <p class="muted">${d.detail || "Данные брокера недоступны."}</p>
          <p>Чтобы включить этот раздел:</p>
          <ol class="muted">
            <li>Создайте токен на <a href="https://www.tbank.ru/invest/settings/api" target="_blank">tbank.ru/invest/settings/api</a> (доступ: «только чтение»);</li>
            <li>На сервере добавьте строку <code>FIN_TINVEST_TOKEN=ваш_токен</code> в файл /opt/fin/.env;</li>
            <li>Перезапустите: <code>cd /opt/fin && docker compose up -d</code>.</li>
          </ol>
          <p class="muted">Без токена работают скринеры, подбор портфеля и вкладка «Цели».</p>
        </div>`;
      return;
    }
    accounts = (await res.json()).accounts;
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
  await loadStrategyBanner();
  await loadTaxes();
  await loadHistory();
  await loadLots();
  await loadOffers();
}

async function loadStrategyBanner() {
  try {
    const r = await (await fetch("/api/strategy")).json();
    const banner = $("#myStrategyBanner");
    if (r.strategy) {
      banner.innerHTML = `Применена стратегия: <b>${r.strategy.profile_label}</b>, ` +
        `${fmt(r.strategy.amount, 0)} ₽ <span class="muted">(сохранена ${r.strategy.updated_at.slice(0, 10)})</span>`;
    } else {
      banner.innerHTML = `<span class="muted">Стратегия не сохранена. Задайте её на вкладке «Портфель» — тогда здесь появится ребалансировка.</span>`;
    }
  } catch { /* не критично */ }
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
  loadRebalance();
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
    <div id="myStrategyBanner" style="margin-bottom:12px"></div>
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
    <div id="rebalanceBox" style="margin-top:22px"></div>
    <div id="incomeCalendar"></div>
    <div id="offersBox" style="margin-top:22px"></div>
    <div id="taxesBox" style="margin-top:22px"></div>
    <div id="historyBox" style="margin-top:22px"></div>
    <div id="lotsBox" style="margin-top:22px"></div>`;
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

// --- моя стратегия + ребалансировка ---
async function loadStrategyStatus() {
  try {
    const r = await (await fetch("/api/strategy")).json();
    $("#strategyStatus").textContent = r.strategy
      ? `Активная стратегия: ${r.strategy.profile_label}, ${fmt(r.strategy.amount, 0)} ₽`
      : "Стратегия не сохранена — подберите портфель и нажмите «Сохранить как мою стратегию»";
  } catch { /* не критично */ }
}
loadStrategyStatus();

async function saveStrategy() {
  const f = new FormData($("#portfolioForm"));
  const res = await fetch("/api/strategy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: f.get("profile"), amount: +f.get("amount") }),
  });
  if (res.ok) {
    showToast("Стратегия сохранена ✓");
    setTimeout(loadStrategyStatus, 500);
  } else {
    showToast("Ошибка сохранения стратегии", true);
  }
}

async function loadRebalance() {
  let r;
  try {
    const budget = document.getElementById("budgetMode")?.checked ? "true" : "false";
    const res = await fetch(`/api/my/rebalance?budget_mode=${budget}`);
    const text = await res.text();
    let d;
    try { d = JSON.parse(text); }
    catch { throw new Error(`сервер вернул ошибку ${res.status} — попробуйте обновить страницу`); }
    if (!res.ok) throw new Error(d.detail || `ошибка ${res.status}`);
    r = d;
  } catch (e) {
    $("#rebalanceBox").innerHTML = `<p class="muted">Ребалансировка: ${e.message}</p>`;
    return;
  }
  const ACTION = { BUY: ["КУПИТЬ", "buy"], SELL: ["ПРОДАТЬ", "sell"],
                   HOLD: ["ДЕРЖАТЬ", "hold"], SKIP: ["ПОЗЖЕ", "hold"] };
  const rows = r.actions.map(a => `
    <tr>
      <td><span class="badge ${ACTION[a.action][1]}">${ACTION[a.action][0]}</span></td>
      <td><b>${a.name || a.ticker}</b>${a.name && a.name != a.ticker ? `<br><span class="muted">${a.ticker}</span>` : ""}</td>
      <td class="num">${a.held_qty ? fmt(a.held_qty, a.held_qty % 1 ? 2 : 0) : "—"}</td>
      <td class="num ${a.action === "SELL" ? "sell-qty" : a.action === "BUY" ? "yield" : ""}">${a.qty ? (a.action === "BUY" ? "+" : "−") + fmt(a.qty, a.qty % 1 ? 2 : 0) : "—"}</td>
      <td class="num">${(a.action === "HOLD" || a.action === "SKIP") ? "—" : fmt(a.amount, 0) + " ₽"}</td>
      <td class="muted">${a.note}</td>
    </tr>`).join("");
  const repl = r.replacement_candidates.length ? `
    <p class="muted">Кандидаты на замену (вошли в индекс): ${
      r.replacement_candidates.map(c => `<b>${c.ticker}</b> (${c.weight}%)`).join(", ")}</p>` : "";
  const fxStr = (r.cash_fx || []).map(f => `${f.qty} ${f.ccy} (≈${fmt(f.value_rub, 0)} ₽)`).join(" + ");
  $("#rebalanceBox").innerHTML = `
    <h3>Ребалансировка по стратегии «${r.strategy.profile_label}» (${fmt(r.strategy.amount, 0)} ₽)</h3>
    <p class="muted">Реальный портфель: ${fmt(r.real_total, 0)} ₽. Свободные деньги: <b>${fmt(r.cash, 0)} ₽</b>${
      fxStr ? ` + ${fxStr} — под покупки не идут, нужна конвертация` : ""}.
       Целевая доходность стратегии: ${fmt(r.target_expected_yield)}%</p>
    <label class="check" style="margin:8px 0">
      <input type="checkbox" id="budgetMode" ${r.budget_mode ? "checked" : ""} onchange="loadRebalance()">
      Только на доступные деньги — ${fmt(r.cash, 0)} ₽ (покупки по приоритету доходности)
    </label>
    <table><thead><tr><th>Действие</th><th>Бумага</th><th class="num">Есть, шт</th><th class="num">Δ, шт</th><th class="num">Сумма</th><th>Причина</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="muted" style="margin-top:10px">Итого: купить на ${fmt(r.buy_total, 0)} ₽, продать на ${fmt(r.sell_total, 0)} ₽</p>
    ${repl}`;
}

// --- всплывающие сообщения ---
function showToast(msg, isError = false) {
  let el = $(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), 3000);
}

async function loadTaxes() {
  const box = $("#taxesBox");
  if (!myAccountId || !box) return;
  try {
    const res = await fetch(`/api/my/taxes?account_id=${myAccountId}`);
    if (!res.ok) return;
    const t = await res.json();
    if (!t.annual_income) {
      box.innerHTML = "<p class='muted'>Налоги: купонов и дивидендов за год пока нет.</p>";
      return;
    }
    box.innerHTML = `
      <h3>Налоги</h3>
      <p>Ожидаемый доход за 12 мес: <b>${fmt(t.annual_income, 0)} ₽</b>,
         НДФЛ (~13%${t.ndfl_15_base ? " + 15% свыше 2.4 млн" : ""}): <b>${fmt(t.tax_est, 0)} ₽</b></p>
      <p class="muted">${t.iis_a_hint}. ${t.iis_b_hint}.</p>`;
  } catch { /* не критично */ }
}

async function loadHistory() {
  const box = $("#historyBox");
  if (!box) return;
  try {
    const r = await (await fetch("/api/my/history")).json();
    if (r.points.length < 2) {
      box.innerHTML = "<p class='muted'>График стоимости появится после нескольких дней синхронизации.</p>";
      return;
    }
    renderHistoryChart(r.points);
  } catch { /* не критично */ }
}

function renderHistoryChart(points) {
  const W = 640, H = 180, pad = 34;
  const vals = points.map(p => p.total);
  const min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  const x = i => pad + i * (W - 2 * pad) / Math.max(points.length - 1, 1);
  const y = v => H - pad - (v - min) / span * (H - 2 * pad);
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.total).toFixed(1)}`).join(" ");
  const area = `${pad},${H - pad} ${line} ${x(points.length - 1).toFixed(1)},${H - pad}`;
  $("#historyBox").innerHTML = `
    <h3>Стоимость портфеля</h3>
    <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="max-width:100%">
      <polygon points="${area}" fill="rgba(59,130,246,.12)"></polygon>
      <polyline points="${line}" fill="none" stroke="#3b82f6" stroke-width="2"></polyline>
      <text x="${pad}" y="${y(max) - 8}" fill="#8b95a9" font-size="11">${fmt(max, 0)} ₽</text>
      <text x="${pad}" y="${H - pad + 14}" fill="#8b95a9" font-size="11">${fmt(min, 0)} ₽</text>
      <text x="${W - pad}" y="${H - 6}" text-anchor="end" fill="#8b95a9" font-size="11">${points[points.length - 1].date}</text>
      <text x="${pad}" y="${H - 6}" fill="#8b95a9" font-size="11">${points[0].date}</text>
    </svg>`;
}

// --- экспорт подборки в CSV ---
function exportPortfolioCSV() {
  if (!lastPortfolio) { showToast("Сначала подберите портфель", true); return; }
  const r = lastPortfolio;
  const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
  const lines = [["Класс", "Тикер", "Название", "Доля %", "Сумма руб", "Количество", "Доходность %"]];
  for (const b of r.bonds) lines.push(["Облигация", b.secid, b.shortname, b.weight, b.amount, b.approx_qty, b.yield]);
  for (const s of r.shares) lines.push(["Акция", s.secid, s.shortname, s.weight, s.amount, s.approx_qty, s.div_yield_12m]);
  const csv = "﻿" + lines.map(l => l.map(esc).join(";")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `portfolio_${r.profile}_${r.amount}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast("CSV выгружен");
}

// --- лоты: история покупок по ценам ---
async function loadLots() {
  const box = $("#lotsBox");
  if (!myAccountId || !box) return;
  try {
    const res = await fetch(`/api/my/lots?account_id=${myAccountId}`);
    if (!res.ok) return;
    const d = await res.json();
    if (!d.positions.length) {
      box.innerHTML = "";
      return;
    }
    const rows = d.positions.flatMap(p =>
      p.lots.map(l => `
      <tr>
        <td><b>${p.ticker}</b><br><span class="muted">${p.name}</span></td>
        <td>${l.date}</td>
        <td class="num">${fmt(l.price, 2)}</td>
        <td class="num">${l.qty}</td>
        <td class="num">${fmt(l.invested, 0)}</td>
        <td class="num ${l.pnl_pct >= 0 ? "yield" : ""}">${l.pnl_pct == null ? "—" : fmt(l.pnl_pct, 1) + "%"}</td>
      </tr>`)).join("");
    box.innerHTML = `
      <h3>История покупок (лоты)</h3>
      <p class="muted">Каждая покупка отдельно: цена лота и результат, если продать сейчас.
         Продажи учтены по FIFO (вычитаются из самых старых лотов).</p>
      <table><thead><tr>
        <th>Бумага</th><th>Дата покупки</th><th class="num">Цена лота</th>
        <th class="num">Кол-во</th><th class="num">Вложено, ₽</th><th class="num">P&L лота</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  } catch { /* не критично */ }
}

// --- оферты по облигациям портфеля ---
async function loadOffers() {
  const box = $("#offersBox");
  if (!myAccountId || !box) return;
  try {
    const res = await fetch(`/api/my/offers?account_id=${myAccountId}`);
    if (!res.ok) return;
    const d = await res.json();
    if (!d.events.length) {
      box.innerHTML = "<p class='muted'>У облигаций в портфеле нет предстоящих оферт.</p>";
      return;
    }
    const rows = d.events.map(e => `
      <tr>
        <td>${e.offer_date}</td>
        <td><b>${e.name}</b><br><span class="muted">${e.ticker}</span></td>
        <td class="num">${e.qty}</td>
        <td class="num">${e.days_left}</td>
        <td class="num">${fmt(e.price, 2)}%</td>
      </tr>`).join("");
    box.innerHTML = `
      <h3>Оферты по облигациям</h3>
      <p class="muted">В эти даты эмитент обязан выкупить бумагу. Если цена на рынке ниже номинала —
         выгодно подать заявку на оферту (условия смотрите в приложении брокера).</p>
      <table><thead><tr>
        <th>Дата оферты</th><th>Бумага</th><th class="num">Кол-во</th>
        <th class="num">Дней осталось</th><th class="num">Цена сейчас, %</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  } catch { /* не критично */ }
}
