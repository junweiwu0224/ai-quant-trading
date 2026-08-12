FROM python:3.11-slim

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 系统依赖（LightGBM 需要 libgomp）
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .
# The runtime uses the repository's lightweight ``data/qlib`` compatibility
# layer; it does not import the heavyweight pyqlib package. pyqlib currently
# publishes no aarch64 Linux wheel, so keep it out of the deploy image rather
# than making the whole local stack unbuildable on Apple Silicon.
RUN grep -v '^pyqlib[<>=!~]' requirements.txt > /tmp/runtime-requirements.txt \
    && pip install --no-cache-dir -r /tmp/runtime-requirements.txt

# 复制项目代码
COPY . .

# 创建数据和日志目录
RUN mkdir -p data/db logs

EXPOSE 8001

CMD ["python", "scripts/run_dashboard.py", "--port", "8001"]
