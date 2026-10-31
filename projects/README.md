# 포트폴리오 등록·운영

포트폴리오는 프로젝트의 메뉴 분류입니다. 완성된 프로젝트도 기존 `PoC/NN-project/` 폴더와 최초 번호, 서비스 URL을 유지합니다. `portfolio_loader.py`는 `PoC/`와 `projects/`의 `project.json`을 함께 읽습니다.

## 현재 포트폴리오

| 최초 번호 | 폴더 | 프로젝트 |
| --- | --- | --- |
| 07 | `PoC/07-NationalAssembly` | 지금 우리 국회에선 |
| 08 | `PoC/08-AICommonPlatformRadar` | 조달췤! |
| 10 | `PoC/10-home` | HOME |
| 12 | `PoC/12-epub-reader` | 책자리 · EPUB · PDF 리더 |

이전 청킹 실습·청킹 RAG·멀티에이전트 하네스·보고서 초안 프로젝트는 삭제했습니다.

## 메뉴 전환

프로젝트의 `project.json`에서 `menu_group`을 `portfolio`로 바꿉니다. PoC에 남길 때는 `poc`를 사용합니다. `display_no`, `id`, 폴더명과 `app_path`는 유지합니다. 목록 순서가 바뀌어도 번호를 다시 매기지 않습니다.

```json
{
  "id": "national-assembly",
  "order": 7,
  "display_no": "07",
  "menu_group": "portfolio",
  "lifecycle": "live"
}
```

`title`, `summary`, `description`, `features`, `usage`, `note`, `entry_file`로 프로젝트 설명을 관리합니다. 독립 앱은 `app_path`로 기존 경로를 연결하며, 사용하지 않는 코드 전문은 메뉴 HTML에 넣지 않습니다.

## 검증과 배포

```bash
python3 -m unittest discover -s tests -p 'test_portfolio_catalog.py'
python3 -m py_compile portfolio_loader.py main.py
git diff --check
```

운영 반영은 기존 연결을 마친 뒤 전환하고 공개 경로와 인증을 점검합니다. 단순 메뉴 분류 변경을 위해 개별 프로젝트의 API·DB·워커를 재시작하지 않습니다.

실제 키·DB·수집 파일·실행 상태는 Git에 넣지 않습니다. 서비스별 설정과 복구 방법은 해당 프로젝트 문서를 따릅니다.
