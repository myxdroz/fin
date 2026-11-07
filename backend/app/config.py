from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIN_")

    database_url: str = "sqlite:////data/fin.db"
    moex_base_url: str = "https://iss.moex.com/iss"
    http_timeout: float = 20.0
    sync_on_startup: bool = True
    scheduler_enabled: bool = True
    # Время ежедневной синхронизации (UTC): 21:00 UTC = 00:00 МСК
    sync_hour_utc: int = 21
    sync_minute_utc: int = 0
    key_rate: float = 15.0  # запасное значение; обновляется автоматически из MOEX
    tinvest_token: str = ""  # T-Invest API read-only токен; пусто = дивиденды со Smart-Lab


settings = Settings()
