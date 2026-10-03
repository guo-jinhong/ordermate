from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    embedding_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str | None = None
    rerank_base_url: str | None = None
    openai_fallback_model: str | None = None
    openai_fallback_base_url: str | None = None
    openai_fallback_api_key: str | None = None
    chat_timeout_seconds: float = 60
    read_retry_budget_seconds: float = 20
    confirmation_ttl_seconds: int = 180
    operation_retention_days: int = 7
    operation_db_path: str = "agent_operations.db"
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
    # SEC-1: CORS 白名单（逗号分隔），生产环境禁止使用 *
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    # SEC-3: /admin 接口鉴权 token
    admin_token: str | None = None
    # 公网安全：共享账号下禁用写操作（购物车/下单/支付/取消/退款）
    public_readonly: bool = False
    # 本机临时公网演示入口；仅提供 Vue 页面和所需 API。
    public_demo: bool = False
    demo_chat_daily_limit: int = 30
    demo_chat_max_concurrent: int = 2
    demo_allowed_users: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            embedding_api_key=os.getenv("EMBEDDING_API_KEY") or None,
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL") or None,
            rerank_base_url=os.getenv("RERANK_BASE_URL") or None,
            openai_fallback_model=os.getenv("OPENAI_FALLBACK_MODEL") or None,
            openai_fallback_base_url=os.getenv("OPENAI_FALLBACK_BASE_URL") or None,
            openai_fallback_api_key=os.getenv("OPENAI_FALLBACK_API_KEY") or None,
            ecommerce_api_base_url=os.getenv(
                "ECOMMERCE_API_BASE_URL", "http://localhost:8080/api"
            ).rstrip("/"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")),
            chat_timeout_seconds=float(os.getenv("CHAT_TIMEOUT_SECONDS", "60")),
            read_retry_budget_seconds=float(os.getenv("READ_RETRY_BUDGET_SECONDS", "20")),
            confirmation_ttl_seconds=max(1, int(os.getenv("CONFIRMATION_TTL_SECONDS", "180"))),
            operation_retention_days=max(1, int(os.getenv("OPERATION_RETENTION_DAYS", "7"))),
            operation_db_path=os.getenv("OPERATION_DB_PATH", "agent_operations.db"),
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
            cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
            admin_token=os.getenv("ADMIN_TOKEN") or None,
            public_readonly=os.getenv("PUBLIC_READONLY", "false").lower() in {"1", "true", "yes", "on"},
            public_demo=os.getenv("PUBLIC_DEMO", "false").lower() in {"1", "true", "yes", "on"},
            demo_chat_daily_limit=int(os.getenv("DEMO_CHAT_DAILY_LIMIT", "30")),
            demo_chat_max_concurrent=int(os.getenv("DEMO_CHAT_MAX_CONCURRENT", "2")),
            demo_allowed_users=[u.strip() for u in os.getenv("DEMO_ALLOWED_USERS", "").split(",") if u.strip()],
        )

    def resolved_agent_mode(self) -> str:
        if self.agent_mode == "auto":
            return "live" if self.openai_api_key else "demo"
        if self.agent_mode not in {"live", "demo"}:
            raise ValueError("AGENT_MODE must be one of: auto, live, demo")
        return self.agent_mode

    # 生产环境禁止使用的默认/示例密码与密钥（防止忘记改配置直接上线）
    _FORBIDDEN_SECRETS = frozenset({
        "123456",
        "password",
        "admin",
        "agent_readonly_123456",
        "local-demo-jwt-secret-key-change-before-production-2026-at-least-64-bytes-long",
        "ecommerce-secret-key-very-long-and-secure-key-for-jwt-token-generation",
        "dev-ecommerce-secret-key-only-for-local-development-do-not-use-in-prod",
    })

    def validate_for_production(self) -> None:
        """Fail fast if production-critical secrets are still defaults/examples.

        Only enforced when the app is running in a non-dev environment.
        """
        import os

        if os.getenv("APP_ENV", "dev").lower() in {"dev", "development", "local", "test"}:
            return

        mode = self.resolved_agent_mode()
        issues: list[str] = []

        if mode == "live":
            if not self.openai_api_key:
                issues.append("OPENAI_API_KEY 未配置，live 模式无法运行")
            elif self.openai_api_key in {"sk-demo", "test-key", "your-api-key-here"}:
                issues.append("OPENAI_API_KEY 仍是示例值")

        if self.db_type == "mysql":
            if self.mysql_password in self._FORBIDDEN_SECRETS:
                issues.append(f"MYSQL_PASSWORD 仍是默认/示例值: {self.mysql_password}")
            if self.mysql_user in {"root", "agent_user"} and self.mysql_password in self._FORBIDDEN_SECRETS:
                issues.append("MySQL 使用 root/agent_user + 默认密码，生产必须使用独立账号与强密码")

        # D1-1: 生产环境禁止直连数据库，必须走后端 API，避免两套数据源不一致
        if self.ecommerce_backend != "api":
            issues.append(
                f"ECOMMERCE_BACKEND 必须为 api（当前: {self.ecommerce_backend}）。"
                "禁止直连数据库，所有业务数据必须通过后端 API 访问。"
            )
        if self.ecommerce_api_base_url in {"http://localhost:8080/api", "http://127.0.0.1:8080/api"}:
            issues.append(f"ECOMMERCE_API_BASE_URL 指向 localhost: {self.ecommerce_api_base_url}")

        if not self.redis_url:
            issues.append("REDIS_URL 未配置，会话状态将丢失在进程内存中，多实例部署不可用")

        # SEC-1: 生产环境 CORS 不能用通配符
        if "*" in self.cors_origins:
            issues.append("CORS_ORIGINS 包含通配符 *，生产环境必须配置具体域名白名单")

        if issues:
            raise RuntimeError(
                "生产环境配置校验失败，请修正以下问题后再启动:\n  - "
                + "\n  - ".join(issues)
            )
