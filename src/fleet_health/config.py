from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    sqlite_db_path: str = ""
    log_level: str = "INFO"

    # Dashboard login (set AUTH_ENABLED=false to disable gate)
    auth_enabled: bool = True
    auth_username: str = "admin"
    auth_password: str = "fleetops"
    session_secret: str = "change-me-in-production"
    session_ttl_hours: int = 24

    # Anomaly detection thresholds
    fuel_overconsumption_pct: float = 10.0
    schedule_slippage_hours: float = 6.0
    maintenance_overdue_days: int = 7

    @property
    def db_path(self) -> Path:
        raw = self.sqlite_db_path or str(PROJECT_ROOT / "data" / "fleet_memory.db")
        path = Path(raw)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
