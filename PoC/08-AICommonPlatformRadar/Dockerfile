FROM debian:bookworm-slim AS hwp-cli

ARG HWP_CLI_VERSION=0.17.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && architecture="$(dpkg --print-architecture)" \
    && case "$architecture" in \
         amd64) asset="hwp-v${HWP_CLI_VERSION}-x86_64-unknown-linux-gnu.tar.gz"; checksum="842c05600b70cb04639958269426e5ffe83ef390a069df7936286c6081ac0f1b" ;; \
         arm64) asset="hwp-v${HWP_CLI_VERSION}-aarch64-unknown-linux-gnu.tar.gz"; checksum="ecaa404650bc5e3c1c1a437caa8d1de95928bc5df7cb3202482a2e65d3138124" ;; \
         *) echo "Unsupported architecture: $architecture"; exit 1 ;; \
       esac \
    && curl -fsSL "https://github.com/STAIxBWLB/hwp-cli/releases/download/v${HWP_CLI_VERSION}/${asset}" -o /tmp/hwp-cli.tar.gz \
    && echo "${checksum}  /tmp/hwp-cli.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/hwp-cli \
    && tar -xzf /tmp/hwp-cli.tar.gz -C /opt/hwp-cli hwp

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HWP_CLI_PATH=/usr/local/bin/hwp

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=hwp-cli /opt/hwp-cli/hwp /usr/local/bin/hwp
COPY . .
RUN mkdir -p data/raw data/parsed data/reports data/logs \
    && useradd --create-home --uid 10001 radar \
    && chown -R radar:radar /app
USER radar

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
