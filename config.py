import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: int = _int("TELEGRAM_CHAT_ID", 0)

    hh_user_agent: str = os.getenv("HH_USER_AGENT", "hh-job-radar/1.0 (replace@example.com)")
    hh_client_id: str = os.getenv("HH_CLIENT_ID", "")
    hh_client_secret: str = os.getenv("HH_CLIENT_SECRET", "")
    hh_redirect_uri: str = os.getenv("HH_REDIRECT_URI", "")
    hh_resume_id: str = os.getenv("HH_RESUME_ID", "")

    area: str = os.getenv("AREA", "1")
    min_score: int = _int("MIN_SCORE", 65)
    scan_interval_minutes: int = _int("SCAN_INTERVAL_MINUTES", 180)
    max_pages_per_query: int = _int("MAX_PAGES_PER_QUERY", 2)
    per_page: int = _int("PER_PAGE", 20)
    publication_period_days: int = _int("PUBLICATION_PERIOD_DAYS", 3)

    oauth_host: str = os.getenv("OAUTH_HOST", "0.0.0.0")
    oauth_port: int = _int("OAUTH_PORT", 8080)
    db_path: str = os.getenv("DB_PATH", "data/job_radar.sqlite3")

    @property
    def search_queries(self) -> list[str]:
        return [
            "стажер информационная безопасность",
            "junior информационная безопасность",
            "младший специалист информационной безопасности",
            "специалист информационной безопасности без опыта",
            "стажер SOC",
            "junior SOC",
            "аналитик SOC стажер",
            "мониторинг информационной безопасности",
            "младший системный администратор Linux",
            "стажер Linux",
            "техническая поддержка Linux",
            "Python стажер",
            "DevOps стажер",
        ]


config = Config()
