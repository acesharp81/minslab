# HOME 주택파동 공통규격 v1.4 제출본

입력은 HOME 운영 DB의 읽기 전용 공유 스냅샷 `home-20261010-live-v3`이다. DB·API·화면을 변경하거나 외부에서 재수집하지 않는다. CSV 8종의 헤더는 `docs/common_form` 원본을 읽어 쓴다.

## 재생성

`PoC/10-home`에서 실행:

```bash
python exports/housing_wave_common_v1_4/program/convert.py --input data/exports/home-20261010-live-v3 --output exports/housing_wave_common_v1_4
python exports/housing_wave_common_v1_4/program/validate.py exports/housing_wave_common_v1_4
```

같은 입력으로 다시 실행하면 같은 CSV·보고서가 생성된다. `--sample 8 --output /tmp/home-common-sample`은 실제 사업 8건의 시험 변환이다.

`review_required.csv`는 공통규격 8종에 포함되지 않는 검토 대장이다. `HOME-LH-BLOCK-*`는 HOME 내부 임시 블록 ID이며 팀 최종 통합 ID가 아니다. `TEST_SAMPLE`은 공식 자료의 부분 수집이고 DEMO가 아니다. 물량 유형 간 단순 합산은 금지한다. 공공 여부·지구/블록 일치가 검토 중인 행은 `REVIEW_REQUIRED`로 표시했다.
