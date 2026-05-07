FROM python:3.11-slim

# 系统依赖 + 编译 ta-lib C 库
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential wget && \
    wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && ./configure --prefix=/usr && make -j$(nproc) && make install && \
    cd / && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz && \
    apt-get purge -y build-essential wget && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建数据和日志目录
RUN mkdir -p data/db logs

EXPOSE 8000

CMD ["python", "scripts/run_dashboard.py"]
