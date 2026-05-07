FROM python:3.11-slim

WORKDIR /app

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建数据和日志目录
RUN mkdir -p data/db logs

EXPOSE 8001

CMD ["python", "scripts/run_dashboard.py", "--port", "8001"]
