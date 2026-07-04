# Cloud Run用コンテナ（docs/infra.md）
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

# SSEストリーミングのため --timeout 0（Cloud Run側は --timeout=3600 を明示設定する）
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
