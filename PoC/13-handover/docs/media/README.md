# 업무바통 시연 영상

사용자가 README에 연결하도록 지정한 영상의 변경 없는 복사본이다.

- 파일: [workbaton-demo-3m45s-chat-support.mp4](workbaton-demo-3m45s-chat-support.mp4)
- 원본 위치: `/home/ubuntu/video-projects/baton-demo/output/chat-support-20261111/workbaton-demo-3m45s-chat-support.mp4`
- 길이: 225초(3분 45초)
- 화면: 1920×1080, H.264 / 음성: AAC
- 크기: 43,476,109바이트
- SHA-256: `24b2693a0958549bd814646c22017239148c68e3af04bbcbc198de52ec937ff7`

마스터 README와 사용자·유지보수·재개발자 문서의 최상단에 동영상 플레이어를 배치한다. PoC7·10과 같은 `<video src="…" controls>`와 MP4 `<img>` 폴백 구조를 사용한다. 일반 HTML 뷰어는 video를 재생하고, GitLab은 MP4 이미지 태그를 동영상 플레이어로 변환한다. 파생 문서의 상대 경로는 생성기가 자동 보정한다.

GitHub는 저장소 안의 상대 MP4 경로만으로 같은 인라인 플레이어를 보장하지 않는다. PoC7·10은 `https://github.com/user-attachments/assets/…` 첨부 주소를 video의 src로 사용한다. 업무바통 영상의 공개 GitHub 첨부 업로드는 자동 승인 검토에서 거절되어 아직 수행하지 않았다. 공개 업로드 승인 후 해당 주소로 video src만 바꾸고, GitLab용 img의 로컬 경로는 유지한 채 `python3 scripts/build_readme_views.py`로 파생 문서를 재생성한다.

이 복사는 영상의 음성·자막·화면·음악을 변경하거나 그 라이선스를 새로 확인한 작업은 아니다. 영상 원본과 앱 동작은 변경하지 않았다.
