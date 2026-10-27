FROM python:3.11-slim

# 国内构建可传入镜像源，例如：
#   docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
# 设为 false 可构建不含本地语音识别的轻量镜像（只能用 mock 演示模式）
ARG WITH_ASR=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements*.txt backend/
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r backend/requirements.txt
RUN if [ "$WITH_ASR" = "true" ]; then \
      pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
      && pip install --no-cache-dir -i "$PIP_INDEX_URL" -r backend/requirements-asr.txt; \
    fi

COPY backend backend
COPY frontend frontend

ENV XW_DATA_DIR=/data \
    XW_FRONTEND_DIR=/app/frontend \
    MODELSCOPE_CACHE=/models

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
