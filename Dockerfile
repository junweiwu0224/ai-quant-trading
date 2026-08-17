ARG NODE_IMAGE=node:22-alpine
ARG PYTHON_IMAGE=python:3.11-slim
FROM ${NODE_IMAGE} AS ui-builder

WORKDIR /ui
COPY dashboard/ui/package.json dashboard/ui/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund
COPY dashboard/ui/ ./
RUN npm run build

FROM ${PYTHON_IMAGE}

ARG INSTALL_OPTIONAL_AI=false

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 系统依赖（LightGBM 需要 libgomp）
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .
# The runtime uses the repository's lightweight ``data/qlib`` compatibility
# layer; it does not import the heavyweight pyqlib package. pyqlib currently
# publishes no aarch64 Linux wheel, so keep it out of the deploy image rather
# than making the whole local stack unbuildable on Apple Silicon.
# pytest is a development tool, Jinja2 belonged to the retired server-rendered
# frontend, and LiteLLM is only needed by the optional AI worker profile. Keep
# the normal Dashboard image small while preserving the full local requirements
# contract and the opt-in multi-vendor provider path.
RUN --mount=type=cache,target=/root/.cache/pip \
    set -eux; \
    grep -Ev '^(pyqlib|pytest|jinja2)([<>=!~]|$)' requirements.txt > /tmp/runtime-requirements.txt; \
    if [ "${INSTALL_OPTIONAL_AI}" != "true" ]; then \
        sed -i -E '/^litellm([<>=!~]|$)/d' /tmp/runtime-requirements.txt; \
    fi; \
    pip install --prefer-binary --no-compile -r /tmp/runtime-requirements.txt

# 复制项目代码
COPY . .
# The production Dashboard serves the Vue shell from FastAPI.  Build it in a
# separate Node stage so the source checkout never needs to commit generated
# assets and the Python runtime stays free of Node/npm.
COPY --from=ui-builder /ui/dist /app/dashboard/ui/dist

# 创建数据和日志目录
RUN mkdir -p data/db logs

EXPOSE 8001

CMD ["python", "scripts/run_dashboard.py", "--port", "8001"]
