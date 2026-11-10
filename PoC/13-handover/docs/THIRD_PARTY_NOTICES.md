# 외부 라이브러리 고지

실제 설치한 `requirements.lock`의 배포 메타데이터와 LICENSE/NOTICE 파일을 수집했습니다. 아래는 라이선스 메타데이터 목록이며, 모든 배포 상황의 의무 충족에 관한 법률 판단은 아닙니다. 원본 고지 파일은 `third_party_licenses/`와 설치된 패키지의 dist-info에 보존됩니다.

| 패키지 | 고정 버전 | 배포 메타데이터 | 원본 고지 |
|---|---|---|---|
| annotated-doc | 0.0.5 | MIT | [LICENSE](third_party_licenses/annotated-doc/LICENSE) |
| annotated-types | 0.8.0 | MIT | [LICENSE](third_party_licenses/annotated-types/LICENSE) |
| anyio | 4.16.0 | MIT | [LICENSE](third_party_licenses/anyio/LICENSE) |
| certifi | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) | [LICENSE](third_party_licenses/certifi/LICENSE) |
| charset-normalizer | 3.5.2 | MIT | [LICENSE](third_party_licenses/charset-normalizer/LICENSE) |
| click | 8.5.1 | BSD-3-Clause | [LICENSE.txt](third_party_licenses/click/LICENSE.txt) |
| et_xmlfile | 2.0.0 | MIT License | 별도 파일 없음 · 배포 메타데이터 확인 |
| fastapi | 0.162.2 | MIT | [LICENSE](third_party_licenses/fastapi/LICENSE) |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | [LICENSE](third_party_licenses/greenlet/LICENSE), [LICENSE.PSF](third_party_licenses/greenlet/LICENSE.PSF) |
| h11 | 0.16.0 | MIT License | [LICENSE.txt](third_party_licenses/h11/LICENSE.txt) |
| httpcore | 1.0.9 | BSD-3-Clause | [LICENSE.md](third_party_licenses/httpcore/LICENSE.md) |
| httpx | 0.28.1 | BSD License | [LICENSE.md](third_party_licenses/httpx/LICENSE.md) |
| idna | 3.20 | BSD-3-Clause | [LICENSE.md](third_party_licenses/idna/LICENSE.md) |
| iniconfig | 2.3.1 | MIT | [LICENSE](third_party_licenses/iniconfig/LICENSE) |
| lxml | 6.1.3 | BSD-3-Clause | [LICENSE.txt](third_party_licenses/lxml/LICENSE.txt), [LICENSES.txt](third_party_licenses/lxml/LICENSES.txt) |
| olefile | 0.47 | BSD License | [LICENSE.txt](third_party_licenses/olefile/LICENSE.txt) |
| openpyxl | 3.1.5 | MIT License | 별도 파일 없음 · 배포 메타데이터 확인 |
| opentelemetry-api | 1.45.2 | Apache-2.0 | [LICENSE](third_party_licenses/opentelemetry-api/LICENSE) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | [LICENSE](third_party_licenses/packaging/LICENSE), [LICENSE.APACHE](third_party_licenses/packaging/LICENSE.APACHE), [LICENSE.BSD](third_party_licenses/packaging/LICENSE.BSD) |
| pillow | 13.0.0 | MIT-CMU | [LICENSE](third_party_licenses/pillow/LICENSE) |
| playwright | 1.64.1 | Apache-2.0 | [LICENSE](third_party_licenses/playwright/LICENSE) |
| pluggy | 1.7.0 | MIT License | [LICENSE](third_party_licenses/pluggy/LICENSE) |
| pydantic | 2.14.3 | MIT | [LICENSE](third_party_licenses/pydantic/LICENSE) |
| pydantic-settings | 2.16.2 | MIT | [LICENSE](third_party_licenses/pydantic-settings/LICENSE) |
| pydantic_core | 2.50.4 | MIT | [LICENSE](third_party_licenses/pydantic_core/LICENSE) |
| pyee | 14.0.0 | MIT License | [LICENSE](third_party_licenses/pyee/LICENSE) |
| Pygments | 2.21.0 | BSD-2-Clause | [LICENSE](third_party_licenses/Pygments/LICENSE) |
| pypdf | 7.0.0 | BSD-3-Clause | [LICENSE](third_party_licenses/pypdf/LICENSE) |
| pytest | 9.2.0 | MIT | [LICENSE](third_party_licenses/pytest/LICENSE) |
| python-docx | 1.2.0 | MIT License | [LICENSE](third_party_licenses/python-docx/LICENSE) |
| python-dotenv | 1.2.4 | BSD-3-Clause | [LICENSE](third_party_licenses/python-dotenv/LICENSE) |
| python-multipart | 0.0.33 | Apache-2.0 | [LICENSE.txt](third_party_licenses/python-multipart/LICENSE.txt) |
| reportlab | 5.1.0 | BSD License | [LICENSE](third_party_licenses/reportlab/LICENSE) |
| starlette | 1.10.0 | BSD-3-Clause | [LICENSE.md](third_party_licenses/starlette/LICENSE.md) |
| syhwp | 0.0.8 | MIT License | [LICENSE](third_party_licenses/syhwp/LICENSE) |
| typing-inspection | 0.4.5 | MIT | [LICENSE](third_party_licenses/typing-inspection/LICENSE) |
| typing_extensions | 4.16.0 | PSF-2.0 | [LICENSE](third_party_licenses/typing_extensions/LICENSE) |
| uvicorn | 0.54.0 | BSD-3-Clause | [LICENSE.md](third_party_licenses/uvicorn/LICENSE.md) |

## 채택하지 않은 구성

minirag-mcp, mcp-local-rag, MuPDF, 외부 임베딩 모델은 이 버전의 의존성에 없습니다. 실제 검색 방식은 로컬 키워드 검색입니다.

## API 참고

Upstage 연결은 [공식 Chat completions API](https://console.upstage.ai/api/chat)의 엔드포인트·모델 별칭·JSON 응답 계약을 참고했습니다. 서비스 사용 요금·약관은 라이브러리 라이선스와 별개입니다. 모델 가중치는 배포하지 않습니다.

## 샘플과 화면

앱 내 혼합 샘플과 화면 그래픽은 프로젝트에서 생성한 합성 데이터·CSS입니다. 기존 공개 HWP 샘플 3건은 읽기 전용 추가 시험에만 사용했고 출품 데이터나 실행 이미지에 복사하지 않았습니다. 외부 폰트·사진·CDN 자산은 화면 실행에 필요하지 않습니다.

## 샘플 저작 도구

python-hwpx 6.11.0 (Apache-2.0): 합성 HWPX 작성·검증에 사용합니다. 런타임 서버 의존성과 분리된 requirements-authoring.txt에 고정했습니다. 라이선스 원문은 third_party_licenses/python-hwpx-LICENSE.txt를 참조하세요.
