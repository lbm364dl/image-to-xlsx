FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/pdf-text/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/pdf-text/server.py .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "server.py"]
