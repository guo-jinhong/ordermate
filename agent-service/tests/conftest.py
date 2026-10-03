"""应用测试使用独立操作日志，避免固定假身份在不同测试间污染持久化记录。"""
import pytest


@pytest.fixture(autouse=True)
def isolate_default_operation_log(tmp_path, monkeypatch):
    import app.main as main
    from app.operation_store import OperationStore

    def create_store(path, redis=None):
        # 显式指定路径的重启/共享测试保留其测试语义。
        if path == "agent_operations.db":
            path = str(tmp_path / "default_operations.db")
        return OperationStore(path, redis)

    monkeypatch.setattr(main, "OperationStore", create_store)
