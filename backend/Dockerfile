# 后端 Dockerfile — 生产环境
FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

EXPOSE 8000

# 启动命令：worker 数通过 WORKERS 环境变量控制（默认 2）
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-2}"
