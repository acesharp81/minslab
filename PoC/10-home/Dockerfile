FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY db db
COPY alembic.ini .
COPY web web
COPY ["docs/공급유형별_추진절차.html", "docs/데이터 신뢰도 확인.html", "/app/docs/"]
COPY scripts scripts
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app:app --host 0.0.0.0 --port 8000"]
