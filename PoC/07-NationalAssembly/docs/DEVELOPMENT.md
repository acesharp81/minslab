# Development

## 원칙

- 프로젝트 루트에서 `.env.example`을 `.env`로 복사합니다.
- 부모 저장소의 `.env`나 `.venv`를 사용하지 않습니다.
- 외부 API test는 기본 test suite에 포함하지 않습니다.
- formatter나 의존성을 추가할 때 requirements와 이 문서를 함께 갱신합니다.

## Backend

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8070 --reload
```

API 문서는 `http://127.0.0.1:8070/docs`에서 확인합니다.

## Test와 정적 검사

```bash
python3 -m unittest discover -s backend/tests -v
ruff check backend
```

## 검증된 일정 수집

```bash
python3 scripts/fetch_schedule.py --date 2026-08-12
```

원본 JSON과 secret이 제거된 manifest가 `data/raw/assembly_schedule/YYYY/MM/DD/`에 저장됩니다. 같은 본문은 SHA-256으로 중복 판정합니다.
## Migration과 정규화

```bash
PYTHONPATH=backend python3 -m app.db.migrate
PYTHONPATH=backend python3 -m app.ingestion.schedule_file
PYTHONPATH=backend python3 -m app.ingestion.committee_sync --date 2026-07-30
```
PYTHONPATH=backend python3 -m app.ingestion.bill_sync --assembly-term 제22대

Docker 이미지는 시작할 때 migration을 자동 적용합니다. 동일 manifest 재처리는 신규 row를 만들지 않습니다.

## Fixture

의안정보 API의 `ERACO` 값은 `22`가 아니라 `제22대` 형식을 사용합니다. `bill_sync`는 대상 회의에 이미 연결된 `BILL_ID`만 상세 보강합니다.

fixture 파일에는 source 이름, 조회일, 원본/합성 여부와 이용조건 검토 결과를 인접 README 또는 metadata에 기록합니다. API key와 개인정보는 포함하지 않습니다.
