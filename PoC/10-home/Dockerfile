FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor poppler-utils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && hwp5txt --version && tesseract --list-langs
COPY backend backend
COPY db db
COPY alembic.ini .
COPY web web
COPY ["docs/공급유형별_추진절차.html", "docs/데이터 신뢰도 확인.html", "/app/docs/"]
COPY scripts scripts
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app:app --host 0.0.0.0 --port 8000"]
