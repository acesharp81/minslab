/* 설정 파일 (index.html이 가장 먼저 읽습니다)
   - VWORLD_KEY : V-World 인증키. 비어 있으면 OpenFreeMap 어두운 지도로 대신 표시합니다.
                  키는 발급할 때 등록한 서비스 URL에서만 동작합니다. 배포 주소를 V-World 콘솔에 등록하세요.
                  화면이 열린 브라우저에서 키가 그대로 보이므로 '서비스 URL 제한'이 유일한 보호 수단입니다.
   - VWORLD_LAYER: (선택) 배경 종류. 기본 'midnight'(야간, 상황판 시안 M3의 네이비). 'Base'(일반)·'Satellite'(위성)도 가능하지만 어두운 화면에 맞춘 색이 아닙니다.
   키가 든 이 파일은 공유하지 마세요. 키 없이 나누려면 config.example.js를 복사해 쓰세요. */
window.VWORLD_KEY = '';   // 여기에 V-World 인증키를 넣으세요
// window.VWORLD_LAYER = 'midnight';
