# 데이터 인터페이스 패키지

지도에 들어갈 데이터를 정해진 표로 넘기기 위한 자료입니다.

| 무엇 | 어디 |
|---|---|
| 정의서 (먼저 읽으세요) | `정의서.pdf` (원본 `정의서.md`) |
| 빈 CSV 틀 | `templates/` |
| 채워진 예 | `examples/` |
| 검증기 | `tools/validate_input.py` (패키지 ZIP 안 또는 저장소) |

## 빠른 시작

1. `templates/`의 파일을 복사해 `input/<지역 slug>/` 폴더에 채웁니다. 엑셀에서는 "CSV UTF-8(쉼표로 분리)"로 저장하세요.
2. 검증합니다: `python3 tools/validate_input.py input/ --out 검증결과`
3. `검증결과/validation_report.md`를 보고 error를 고칩니다. 문제 행은 `검증결과/quarantine/`에 모입니다.
4. error가 0이면 `input/`을 ZIP으로 묶어 전달합니다.

자세한 규칙은 정의서 11절을 보세요.
