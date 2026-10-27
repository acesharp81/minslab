# 설명자료 업로드 폴더

관리자 화면에서 등록한 발표용 HTML은 이 폴더 아래에 자동 저장됩니다.

```text
presentations/{slug}/
├── index.html
└── presentation.json
```

파일을 직접 수정하기보다 홈페이지 관리자 메뉴의 `설명자료 관리`에서 새 항목을 등록하세요.

설명자료는 기본적으로 등록일의 최신순으로 표시합니다. `presentation.json`에 양의 정수
`position`을 지정하면 해당 자료를 그 순번(1부터 시작)에 배치합니다. 제목·HTML을
관리자 화면에서 수정해도 지정 순번은 유지됩니다.

`the-jutaek-data-pipeline`은 메인 홈페이지의 네 번째 설명자료로 관리하는 학습서입니다.
이 폴더는 저장소에 포함하며, 원본 Markdown은
`PoC/10-home/docs/THE_JUTAEK_DATA_PIPELINE_STUDY_AND_GOVERNANCE_20261023.md`입니다.
다운로드용 `static/downloads/the-jutaek-data-pipeline-20261023.md`는 원본과 동일하게
유지합니다. 보고서 개정 시 원본과 다운로드 파일을 함께 갱신해야 합니다.
