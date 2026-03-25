FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv curl git \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/glm-ocr/requirements.txt requirements.txt
RUN python3 -m pip install --no-cache-dir -r requirements.txt
COPY services/glm-ocr/server.py .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["python3", "server.py"]
