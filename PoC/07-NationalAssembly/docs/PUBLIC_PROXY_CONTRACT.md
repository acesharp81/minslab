# PoC 7 공개 프록시 계약

PoC 7 자체 API는 `http://127.0.0.1:18070`에서 `/api/*`를 제공한다. 공개 호스트는 `/poc/national-assembly/` 아래 요청에서 prefix만 제거해 같은 경로로 전달한다.

## 필수 전달 규칙

- `GET`, `HEAD`: 전체 PoC 7 페이지와 API
- `POST`, `PUT`, `DELETE`: `/api/watch/*`와 문서화된 운영 변경 API
- `Cookie`: 다른 홈페이지 cookie는 제거하고 PoC7의 `gukjeongbomi_session`만 전달
- `Set-Cookie`: PoC7 session cookie를 속성 변경 없이 브라우저에 반환
- `Origin`, `Referer`: PoC7의 same-origin 변경 요청 검증을 위해 전달
- `X-Watch-Token`: 구형 사용자 알림 세션의 1회 cookie 승격 호환
- `X-Watch-Admin-Token`: 운영 검토 인증
- 요청 본문과 `Content-Type`: 최대 64 KiB
- upstream의 3xx `Location`: 자동 추적하지 않고 브라우저에 그대로 반환
- upstream의 `Content-Disposition`, `X-LLM-Calls`: 다운로드와 무료 호출 확인을 위해 반환
- 모든 PoC7 응답: CSP, HSTS, Referrer-Policy, Permissions-Policy, X-Frame-Options, nosniff 적용

Kakao callback은 다음 공개 URI를 upstream `/api/watch/kakao/callback`에 전달해야 한다.

`https://www.minslab.kr/poc/national-assembly/api/watch/kakao/callback`

PoC 7 애플리케이션·worker·DB는 부모 애플리케이션 모듈을 import하지 않는다. 이 문서는 reverse proxy를 교체하거나 PoC 7 폴더만 별도 서버에 배포할 때 필요한 외부 HTTP 계약이다.
