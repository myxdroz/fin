"""Подбор портфеля под профиль риска.

Модель намеренно простая и прозрачная (а не «чёрный ящик»):
- консервативный: лестница облигаций (ОФЗ + высокий листинг) с ограничением дюрации;
- умеренный: облигации + дивидендные акции;
- агрессивный: акции + длинные/корпоративные облигации.
Внутри классов активов — равные доли, перекос в сторону доходности ограничен лимитом на бумагу.
"""

import re

from pydantic import BaseModel, Field

from ..config import settings
from .filters import BondFilter, ShareFilter, screen_bonds, screen_shares

PROFILES = {
    "conservative": {
        "label": "Консервативный",
        "bond_share": 1.0, "share_share": 0.0,
        "max_duration": 1095, "bond_limit": 10, "share_limit": 0,
        "max_price": 102.0, "only_quality": True,
        "description": "Только облигации: ОФЗ и корпоративные бумаги 1-2 уровня листинга, "
                       "дюрация до 3 лет. Цель — доходность выше ключевой ставки с минимальным риском.",
    },
    "moderate": {
        "label": "Умеренный",
        "bond_share": 0.6, "share_share": 0.4,
        "max_duration": 1825, "bond_limit": 7, "share_limit": 5,
        "max_price": 104.0, "only_quality": True,
        "description": "60% облигаций + 40% ликвидных дивидендных акций. "
                       "Баланс между доходностью облигаций и ростом акций.",
    },
    "aggressive": {
        "label": "Агрессивный",
        "bond_share": 0.35, "share_share": 0.65,
        "max_duration": 3650, "bond_limit": 5, "share_limit": 8,
        "max_price": 110.0, "only_quality": False,
        "description": "Преимущественно акции + длинные корпоративные облигации с максимальной доходностью. "
                       "Высокая волатильность, горизонт — от 3 лет.",
    },
}


class PortfolioRequest(BaseModel):
    profile: str = Field(pattern="^(conservative|moderate|aggressive)$")
    amount: float = Field(gt=0, description="Сумма портфеля, руб")


def _issuer_key(shortname: str) -> str:
    """Нормализованный ключ эмитента из первого слова названия ('Систем1P24' -> 'систе')."""
    token = shortname.split()[0] if shortname.split() else ""
    m = re.match(r"^[A-Za-zА-Яа-я]+", token)
    return (m.group(0) if m else token)[:5].lower()


def _pick_bonds(db, cfg: dict, amount: float, target: float) -> list[dict]:
    quality = cfg["only_quality"]
    # Консервативный: только 1 уровень листинга, доходность около ставки + умеренная премия.
    # Агрессивный: 1-3 уровень, премия за риск выше.
    yield_cap = settings.key_rate + (8 if quality else 45)
    f = BondFilter(
        min_yield=settings.key_rate - (2 if quality else 0),
        max_yield=yield_cap,
        max_duration=cfg["max_duration"],
        min_liquidity=min(1_000_000, amount * 0.05),
        list_level=1 if quality else 3,
        exclude_floating=True,
        exclude_amort=True,
        max_price=cfg["max_price"],
        limit=300,
    )
    candidates = screen_bonds(db, f)
    if not candidates:
        return []

    # Лестница: делим горизонт дюрации на столько же сегментов, сколько бумаг берём,
    # из каждого сегмента — самая доходная. Не сидим в одной точке кривой доходности.
    picked: list[dict] = []
    n = cfg["bond_limit"]
    seg = max(cfg["max_duration"] / 365 / n, 0.05)
    buckets: list[list[dict]] = [[] for _ in range(n)]
    for b in candidates:
        idx = min(int(b["duration_years"] / seg), n - 1)
        buckets[idx].append(b)

    ofz_min = max(1, n // 3)
    ofz_taken = 0
    for bucket in buckets:
        bucket.sort(key=lambda x: -x["yield"])
        for b in bucket:
            if len(picked) >= n:
                break
            same_issuer = sum(1 for p in picked if _issuer_key(p["shortname"]) == _issuer_key(b["shortname"]))
            if same_issuer >= 2:
                continue
            if b["is_ofz"]:
                ofz_taken += 1
            picked.append(b)
    # Гарантируем долю ОФЗ: добираем из оставшихся, если лестница их не взяла
    if ofz_taken < ofz_min:
        for b in sorted(candidates, key=lambda x: -x["yield"]):
            if len(picked) >= n:
                break
            if b["is_ofz"] and b not in picked:
                picked.append(b)
                ofz_taken += 1

    # Равные доли внутри класса
    weight = target / len(picked)
    for b in picked:
        b["weight"] = round(100 / len(picked), 1)
        nominal_qty = weight / (b["price"] / 100 * b["face_value"])
        b["amount"] = round(weight, 0)
        b["approx_qty"] = int(nominal_qty // 1)
    return picked


def _pick_shares(db, cfg: dict, amount: float, target: float) -> list[dict]:
    if not cfg["share_limit"]:
        return []
    f = ShareFilter(
        min_div_yield=0,
        min_liquidity=min(50_000_000, amount * 0.1),
        list_level=1 if cfg["only_quality"] else 2,
        limit=cfg["share_limit"] * 3,
    )
    candidates = screen_shares(db, f)
    picked = candidates[: cfg["share_limit"]]
    if picked:
        for s in picked:
            s["weight"] = round(100 / len(picked), 1)
            s["amount"] = round(target / len(picked), 0)
            s["approx_qty"] = int(s["amount"] // s["lot_cost"]) * s["lot_size"]
    return picked


def build_portfolio(db, req: PortfolioRequest) -> dict:
    cfg = PROFILES[req.profile]
    bond_target = req.amount * cfg["bond_share"]
    share_target = req.amount * cfg["share_share"]

    bonds = _pick_bonds(db, cfg, req.amount, bond_target)
    shares = _pick_shares(db, cfg, req.amount, share_target)

    bond_yield = sum(b["yield"] for b in bonds) / len(bonds) if bonds else 0.0
    share_yield = sum(s["div_yield_12m"] for s in shares) / len(shares) if shares else 0.0
    expected = bond_yield * cfg["bond_share"] + share_yield * cfg["share_share"]

    return {
        "profile": req.profile,
        "profile_label": cfg["label"],
        "amount": req.amount,
        "description": cfg["description"],
        "key_rate": settings.key_rate,
        "expected_yield": round(expected, 2),
        "expected_income_year": round(req.amount * expected / 100, 0),
        "bonds": bonds,
        "shares": shares,
        "disclaimer": "Расчёт на основе текущих данных MOEX. Это не индивидуальная инвестиционная "
                      "рекомендация (ИИР). Доходность в прошлом не гарантирует доходность в будущем.",
    }
