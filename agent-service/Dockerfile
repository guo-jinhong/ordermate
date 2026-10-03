# ===== 构建阶段：安装依赖 =====
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

COPY requirements.txt .
# --prefix=/install 把依赖装到独立目录，runtime 阶段直接拷贝
RUN python -m pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===== 运行阶段：最小镜像 =====
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# 让 Python 能找到 builder 阶段安装的依赖
ENV PYTHONPATH=/app/lib/python3.12/site-packages
# --prefix installs uvicorn and other console scripts under /app/bin.
ENV PATH="/app/bin:${PATH}"

WORKDIR /app

# 从 builder 拷贝已安装的依赖
COPY --from=builder /install /app

COPY app ./app
# 静态资源（前端页面）必须显式 COPY，否则可能因 .dockerignore 遗漏
COPY app/static ./app/static

EXPOSE 8000

# 非 root 用户运行（安全加固）
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
