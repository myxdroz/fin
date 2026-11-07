from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Bond(Base):
    __tablename__ = "bonds"

    secid: Mapped[str] = mapped_column(String(20), primary_key=True)
    shortname: Mapped[str] = mapped_column(String(120), default="")
    isin: Mapped[str] = mapped_column(String(20), default="", index=True)
    regnumber: Mapped[str] = mapped_column(String(30), default="")
    face_value: Mapped[float] = mapped_column(Float, default=0)
    face_unit: Mapped[str] = mapped_column(String(10), default="SUR")
    prev_price: Mapped[float] = mapped_column(Float, default=0)  # % от номинала
    last_price: Mapped[float] = mapped_column(Float, default=0)  # % от номинала
    yield_at_pricing: Mapped[float] = mapped_column(Float, default=0)  # YIELD, % годовых
    duration: Mapped[float] = mapped_column(Float, default=0)  # дюрация, дней
    coupon_value: Mapped[float] = mapped_column(Float, default=0)
    coupon_percent: Mapped[float] = mapped_column(Float, default=0)
    coupon_period: Mapped[int] = mapped_column(Integer, default=0)
    accr_int: Mapped[float] = mapped_column(Float, default=0)  # НКД
    mat_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_flag: Mapped[int] = mapped_column(Integer, default=0)
    amort_flag: Mapped[int] = mapped_column(Integer, default=0)
    floating_flag: Mapped[int] = mapped_column(Integer, default=0)
    perpetual_flag: Mapped[int] = mapped_column(Integer, default=0)
    issue_size: Mapped[float] = mapped_column(Float, default=0)
    list_level: Mapped[int] = mapped_column(Integer, default=0)  # уровень листинга 1-3
    is_ofz: Mapped[int] = mapped_column(Integer, default=0)  # ОФЗ
    val_today: Mapped[float] = mapped_column(Float, default=0)  # оборот за день, руб
    num_trades: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Share(Base):
    __tablename__ = "shares"

    secid: Mapped[str] = mapped_column(String(20), primary_key=True)
    shortname: Mapped[str] = mapped_column(String(120), default="")
    isin: Mapped[str] = mapped_column(String(20), default="", index=True)
    regnumber: Mapped[str] = mapped_column(String(30), default="")
    prev_price: Mapped[float] = mapped_column(Float, default=0)
    last_price: Mapped[float] = mapped_column(Float, default=0)
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    issue_size: Mapped[float] = mapped_column(Float, default=0)
    list_level: Mapped[int] = mapped_column(Integer, default=0)
    val_today: Mapped[float] = mapped_column(Float, default=0)
    num_trades: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Dividend(Base):
    __tablename__ = "dividends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    secid: Mapped[str] = mapped_column(String(20), index=True)
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="SUR")

    __table_args__ = ({"sqlite_autoincrement": True},)


class IndexWeight(Base):
    """Состав индекса IMOEX: веса компонентов (MOEX index analytics)."""

    __tablename__ = "index_weights"

    secid: Mapped[str] = mapped_column(String(20), primary_key=True)
    shortname: Mapped[str] = mapped_column(String(120), default="")
    weight: Mapped[float] = mapped_column(Float, default=0)  # % от индекса
    tradedate: Mapped[date | None] = mapped_column(Date, nullable=True)
