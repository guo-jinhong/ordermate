"""使用现有 MySQL 配置，在独立临时库验证迁移、锁、幂等及回滚；不打印凭证。"""
import os
from pathlib import Path
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "agent-service"))
from app.config import Settings
import pymysql

cfg = Settings.from_env()
database = "ordermate_check_" + uuid.uuid4().hex
env = os.environ.copy()
env.update(ORDERMATE_MYSQL_CHECK="1", ORDERMATE_MYSQL_TEST_SCHEMA=database,
           ORDERMATE_MYSQL_JDBC_BASE=f"jdbc:mysql://{cfg.mysql_host}:{cfg.mysql_port}",
           ORDERMATE_MYSQL_USER=cfg.mysql_user, ORDERMATE_MYSQL_PASSWORD=cfg.mysql_password)
try:
    result = subprocess.run(["cmd.exe", "/d", "/c", ".\\mvnw.cmd", "test", "-q"],
                            cwd=root, env=env)
finally:
    # Spring 初始化失败时 AfterAll 可能不运行；仅回收本次生成的唯一测试库。
    connection = pymysql.connect(host=cfg.mysql_host, port=int(cfg.mysql_port), user=cfg.mysql_user,
                                 password=cfg.mysql_password, connect_timeout=3)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
    finally:
        connection.close()
raise SystemExit(result.returncode)
