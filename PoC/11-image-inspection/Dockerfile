FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY web web
COPY rules rules
COPY samples samples
COPY scripts scripts
COPY docs docs
RUN useradd --uid 10001 --create-home inspector && mkdir /app/data && chown inspector:inspector /app/data
USER inspector
EXPOSE 18110
CMD ["python", "scripts/serve.py"]
