#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv-ocr
.venv-ocr/bin/python -m pip install -r requirements-ocr.lock
printf '한국어 OCR 설치 완료. 첫 실행 시 공식 모델 약 20MB를 data/ocr-models에 저장합니다.\n'
