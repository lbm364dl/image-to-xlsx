# Main application image — lightweight, no ML frameworks.
# All heavy inference is delegated to the extraction microservices.

FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/image-to-xlsx
COPY requirements_app.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/image-to-xlsx/ ./src/image-to-xlsx/

EXPOSE 8080
WORKDIR /opt/image-to-xlsx/src/image-to-xlsx
CMD ["python", "-m", "gui"]
