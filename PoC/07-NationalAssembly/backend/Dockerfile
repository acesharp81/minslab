FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN useradd --uid 1000 --create-home appuser

COPY app /app/backend/app
COPY migrations /app/backend/migrations

USER appuser

EXPOSE 8070

CMD ["sh", "-c", "python -m app.db.migrate && exec uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port 8070"]
