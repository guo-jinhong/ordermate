from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env file if it exists (without requiring python-dotenv)."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / ".env",  # project root
        Path(__file__).resolve().parent.parent / ".env",  # agent-service dir
        Path.cwd() / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = value
            break


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str | None
    ecommerce_api_base_url: str
    request_timeout_seconds: float
    max_tool_rounds: int
    agent_mode: str = "auto"
    conversation_max_messages: int = 30
    conversation_ttl_seconds: int = 900
    redis_url: str | None = None
    # 数据库类型: sqlite / mysql
    db_type: str = "sqlite"
    # SQLite 配置
    sqlite_path: str = "agent_service_dev.db"
    # MySQL 配置
    mysql_host: str = "127.0.0.1"
    mysql_port: str = "3306"
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "ecommerce_db"
    # 电商后端模式: database / api
    ecommerce_backend: str = "api"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            ecommerce_api_base_url=os.getenv(
                "ECOMMERCE_API_BASE_URL", "http://localhost:8080/api"
            ).rstrip("/"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")),
            max_tool_rounds=int(os.getenv("MAX_TOOL_ROUNDS", "5")),
            agent_mode=os.getenv("AGENT_MODE", "auto").lower(),
            conversation_max_messages=int(os.getenv("CONVERSATION_MAX_MESSAGES", "12")),
            conversation_ttl_seconds=int(os.getenv("CONVERSATION_TTL_SECONDS", "1800")),
            redis_url=os.getenv("REDIS_URL") or None,
            db_type=os.getenv("DB_TYPE", "sqlite").lower(),
            sqlite_path=os.getenv("SQLITE_PATH", "agent_service_dev.db"),
            mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            mysql_port=os.getenv("MYSQL_PORT", "3306"),
            mysql_user=os.getenv("MYSQL_USER", "root"),
            mysql_password=os.getenv("MYSQL_PASSWORD", "123456"),
            mysql_database=os.getenv("MYSQL_DATABASE", "ecommerce_db"),
            ecommerce_backend=os.getenv("ECOMMERCE_BACKEND", "api").lower(),
        )

    def resolved_agent_mode(self) -> str:
        if self.agent_mode == "auto":
            return "live" if self.openai_api_key else "demo"
        if self.agent_mode not in {"live", "demo"}:
            raise ValueError("AGENT_MODE must be one of: auto, live, demo")
        return self.agent_mode
