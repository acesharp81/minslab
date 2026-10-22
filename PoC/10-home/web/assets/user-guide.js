'use strict';
/* Read-only user guidance: no API calls, no changes to filters or saved data. */
const UserGuide = (() => {
  let ready=false, printState=null, searchOpen=null;
  const content=String.raw`
    <div class="guide-hero">
      <div><span class="guide-kicker">the주택 사용법 · 2026-10-15 화면 기준</span><h3>지역의 수급 여건을 살피고,<br>사업의 추진 상황을 확인하세요.</h3><p>지역을 비교할 때는 공급현황의 지역여건, 목표와 일정을 관리할 때는 추진현황을 사용합니다. 수치의 기준과 원문은 각 화면에서 필요할 때 펼쳐 확인하세요.</p><div class="guide-actions"><button type="button" class="button" data-view="supply-conditions">지역여건부터 보기 →</button><button type="button" class="button secondary" data-view="policy-progress">정책 추진현황 →</button><button type="button" class="button secondary" data-guide-section="guide-start">3분 따라하기</button></div></div>
      <aside class="guide-access"><strong>조회는 로그인 없이</strong><p>지도·사업·원천·수집현황을 누구나 볼 수 있습니다.</p><strong>입력·확정은 관리자 로그인 후</strong><p>목표 수정과 연결 검토는 업무 담당자가 근거를 확인하고 저장합니다.</p></aside>
    </div>
    <div class="guide-controls"><label for="guide-search">어떤 도움이 필요한가요?<input id="guide-search" type="search" placeholder="예: 지역여건, 주택보급률, 지연, PIR, 수집 샘플" autocomplete="off"></label><div><output id="guide-search-status" role="status" aria-live="polite"></output><button id="guide-print" type="button" class="button secondary">인쇄 / PDF 저장</button></div></div>
    <div class="guide-tasks" aria-label="원하는 작업 바로 시작">
      <article><span>01 · 정책 판단</span><h4>어디가 지연되는지 보고 싶어요</h4><p>지역을 선택하고 단계별 목표·측정·갭과 지연·주의 추이를 봅니다.</p><button type="button" data-view="policy-progress">정책 추진현황 열기 →</button></article>
      <article><span>02 · 사업 확인</span><h4>특정 사업의 일정을 찾고 싶어요</h4><p>사업명으로 검색하고 단계·예정일·원문을 확인합니다.</p><button type="button" data-view="projects">사업 추진현황 열기 →</button></article>
      <article><span>03 · 지역 비교</span><h4>가격·가구·공급을 비교하고 싶어요</h4><p>정책과 지역을 고르고 네 주제의 시장·수급 지표를 비교합니다.</p><button type="button" data-view="supply-conditions">지역여건 열기 →</button></article>
      <article><span>04 · 자료 점검</span><h4>왜 미확보인지 알고 싶어요</h4><p>사업×단계 표와 연결 다이어그램에서 누락 원인을 찾습니다.</p><button type="button" data-view="project-collection">사업별 수집연계 열기 →</button></article>
    </div>
    <div class="guide-layout">
      <nav class="guide-nav" aria-label="사용법 목차"><strong>필요한 설명 찾기</strong><button type="button" data-guide-section="guide-menu">1. 메뉴와 화면</button><button type="button" data-guide-section="guide-start">2. 3분 따라하기</button><button type="button" data-guide-section="guide-region">3. 지역여건</button><button type="button" data-guide-section="guide-policy">4. 정책·프로그램·사업</button><button type="button" data-guide-section="guide-map">5. 지도와 입지</button><button type="button" data-guide-section="guide-meaning">6. 그래프·수치 읽기</button><button type="button" data-guide-section="guide-data">7. 자료·오류 확인</button><button type="button" data-guide-section="guide-manage">8. 담당자 입력</button><button type="button" data-guide-section="guide-help">9. 자주 묻는 질문</button></nav>
      <div class="guide-reading">
        <p id="guide-no-results" class="guide-no-results" hidden>일치하는 안내가 없습니다. 짧은 단어로 다시 검색하거나 <button id="guide-reset-search" type="button">전체 안내 보기</button>를 선택하세요.</p>
        <article id="guide-menu" class="guide-block" data-guide-topic data-guide-keywords="메뉴 대주제 소메뉴 공급현황 지도 지역여건 추진현황 정책 프로그램 사업 데이터관리 매뉴얼 사용법 요구사항정의">
          <span class="guide-section-number">01 · 메뉴와 화면</span><h3 tabindex="-1">확인하려는 내용에 맞춰 화면을 고르세요</h3><p>왼쪽 대주제를 누르면 소메뉴가 펼쳐집니다. 지도·진행 체크·데이터베이스·책 아이콘으로 구분하며, 왼쪽 위 메뉴 버튼으로 메뉴 전체를 접거나 펼칠 수 있습니다.</p>
          <div class="guide-state-table"><table><caption>현재 메뉴 구성과 이용 목적</caption><thead><tr><th scope="col">대주제</th><th scope="col">소메뉴</th><th scope="col">확인하는 내용</th></tr></thead><tbody>
            <tr><th scope="row">공급현황</th><td><button type="button" class="guide-inline-action" data-view="overview">공급현황 지도</button><br><button type="button" class="guide-inline-action" data-view="supply-conditions">지역여건</button></td><td>사업 위치와 주변 시설, 지역의 가구·주택·가격·공급 실적·향후 수급을 봅니다.</td></tr>
            <tr><th scope="row">추진현황</th><td><button type="button" class="guide-inline-action" data-view="policy-progress">정책</button> · <button type="button" class="guide-inline-action" data-view="program-progress">프로그램</button> · <button type="button" class="guide-inline-action" data-view="projects">사업</button></td><td>같은 범위의 목표·측정·지연과 단계별 일정·근거를 관리합니다.</td></tr>
            <tr><th scope="row">데이터관리</th><td><button type="button" class="guide-inline-action" data-view="sources">출처와 수집현황</button><br><button type="button" class="guide-inline-action" data-view="tree">정책-프로그램-사업 연결</button><br><button type="button" class="guide-inline-action" data-view="project-collection">사업별 수집연계</button></td><td>수집 상태·실제 샘플·사업 연결과 단계별 남은 수집 항목을 확인합니다.</td></tr>
            <tr><th scope="row">문서</th><td>사용법 · <button type="button" class="guide-inline-action" data-view="requirements">요구사항정의</button></td><td>화면 이용 순서와 기능별 요구사항·구현 범위·남은 과제를 봅니다.</td></tr>
          </tbody></table></div><p class="guide-note">이 문서 위쪽 검색창에서 필요한 안내를 찾고, 목차 버튼으로 해당 설명에 이동하세요. <b>인쇄 / PDF 저장</b>은 검색을 해제하고 접힌 설명을 모두 펼쳐 인쇄합니다. 인쇄 후에는 검색과 펼침 상태를 복원합니다.</p>
        </article>
        <article id="guide-start" class="guide-block" data-guide-topic data-guide-keywords="초보 시작 처음 빠른 사용 방법">
          <span class="guide-section-number">02 · 시작하기</span><h3 tabindex="-1">3분 따라하기: 서울의 정책 진행 확인</h3><p>다음 순서로 한 번만 따라 해 보세요. 목표와 현황이 다른 이유를 사업 근거까지 확인하는 흐름입니다.</p>
          <ol class="guide-steps">
            <li><div><strong>정책 추진현황을 엽니다.</strong><p>왼쪽 <b>추진현황 → 정책</b>을 선택합니다. 상단 정책은 9·7입니다.</p><button type="button" class="guide-inline-action" data-view="policy-progress">이 화면 열기 →</button></div></li>
            <li><div><strong>지역 탭에서 ‘서울’을 선택합니다.</strong><p>정책 개요 오른쪽의 <b>전체 / 서울 / 경기 / 인천</b> 탭을 사용합니다. 지도와 아래 그래프의 범위·Y축이 서울에 맞게 바뀝니다.</p></div></li>
            <li><div><strong>단계와 기준 연도를 고릅니다.</strong><p>사업화·인허가·건설·공급·입주 중 관심 단계를 선택하고 연도 조절기로 기준 연도를 맞춥니다. 월별 흐름은 그래프의 시간 단위에서 선택합니다.</p></div></li>
            <li><div><strong>현재 물량과 연말 예상량을 확인합니다.</strong><p>단계별 카드의 <b>현재 누적 측정량</b>은 지도와 같은 사업 범위·기준일의 값입니다. <b>12월 말 기준 누적 예상량</b>은 선택 연도 12월 31일까지 저장된 계획 누계이며 현재값에 더하지 않습니다. 연말 이후 일정은 제외하고, 계획이 없으면 미확보로 표시합니다. 정책·프로그램 화면은 승인 연결된 전체 사업을 표시하며, 과거 착공일만으로 사업을 제외하지 않습니다. 그래프 아래의 <b>10월 공식 발표 사업·물량 대조</b>에서 발표에 언급된 사업과 원장 규모·착공연도·미반영 단계를 확인합니다. 공식 올해 실적과 전체 연결 사업 누계는 기준이 다릅니다. 그래프의 목표 점선과 실적 실선으로 현재 도래 목표 대비 부족률도 확인합니다. <b>2% 이상은 지연(빨강)</b>, <b>0% 초과~2% 미만은 주의(노랑)</b>로 관리합니다. 자료가 없으면 판단이 보류될 수 있습니다.</p></div></li>
            <li><div><strong>대상 사업의 근거를 엽니다.</strong><p>아래의 <b>선택 범위의 프로그램 펼쳐보기</b>에서 프로그램을 열고, 프로그램의 <b>소속 사업</b>에서 사업 상세로 이동합니다. <b>목표 기한, 실제 근거 날짜, 적용 물량, 원문</b>을 함께 확인합니다. 이전 단계 자료가 빠졌다면 사업별 수집연계에서 이유를 봅니다.</p></div></li>
          </ol><p class="guide-result"><b>여기까지 하면</b> 선택 지역의 목표·현황·확인할 사업과 그 근거를 설명할 수 있습니다.</p>
        </article>
        <article id="guide-region" class="guide-block" data-guide-topic data-guide-keywords="지역여건 가구 구성 주택 기반 매매가격 미분양 공급 실적 입주 예정 장기 수요 보급률 지역 비교 공식 산출 옹진군 원천">
          <span class="guide-section-number">03 · 지역여건</span><h3 tabindex="-1">정책과 지역을 고르고 네 주제를 비교하세요</h3><p><b>공급현황 → 지역여건</b>에는 9개 시장·수급 지표와 1·2·3·4인 이상 가구 변화가 모여 있습니다. 모든 주제에 위쪽 조회 조건이 공통으로 적용됩니다.</p>
          <ol class="guide-steps"><li><div><strong>정책을 먼저 선택합니다.</strong><p>현재 원장이 연결된 9·7 정책을 선택할 수 있습니다. 비활성 정책은 선택되지 않습니다. 정책을 다시 설정하면 비교 지역과 시군구가 전체 범위로 초기화됩니다.</p></div></li><li><div><strong>비교 지역 → 시군구를 고릅니다.</strong><p>시도 선택에 맞춰 시군구 목록이 바뀝니다. 지도에서 지역을 선택해도 해당 시도·시군구 조건이 연계됩니다.</p></div></li><li><div><strong>예정·목표 연도와 평균 비교 기간을 맞춥니다.</strong><p>예정 물량과 목표는 선택 연도로 비교하고, 평균은 최근 3·5·10년 중 고릅니다. 가격·재고 등의 최근 확보 기준월은 각 카드에서 별도로 확인합니다.</p></div></li><li><div><strong>관련 지표를 나란히 읽습니다.</strong><p>두 지표 주제는 넓은 화면에서 2열, 세 지표 주제는 3열입니다. 좁은 화면에서는 최대 2열, 모바일에서는 1열로 이어집니다.</p></div></li><li><div><strong>필요하면 수치·기준·원천을 펼칩니다.</strong><p>공식·산출 기준, 전체 수치 표와 원문 링크를 확인합니다. <b>공식 공표값 / 최신 동일 정의 산출</b>, <b>월별 / 연초 누계</b> 버튼으로 비교 방식을 바꿀 수 있습니다.</p></div></li></ol>
          <div class="guide-state-table"><table><caption>주제별 그래프·차트 구성</caption><thead><tr><th scope="col">주제</th><th scope="col">지표</th><th scope="col">함께 확인할 내용</th></tr></thead><tbody>
            <tr><th scope="row">가구 구성과 주택 기반</th><td>1·2·3·4인 이상 가구 변화<br>주택보급률과 공급 배치</td><td>가구 변화와 주택 보급 수준, 사업의 지역 배치를 비교합니다.</td></tr>
            <tr><th scope="row">주택시장과 수급</th><td>아파트 매매가격 변동률<br>전체·준공 후 미분양</td><td>가격 상승·하락과 미분양 재고의 변화를 함께 봅니다.</td></tr>
            <tr><th scope="row">공급 실적과 구성</th><td>인허가·착공·준공과 장기 평균<br>월별·누계 착공실적<br>공공주택·비아파트 공급 구성</td><td>승인에서 건설까지 이어지는 실적과 공급 유형을 비교합니다.</td></tr>
            <tr><th scope="row">향후 공급과 목표</th><td>향후 입주예정물량과 공급 공백<br>장기 수요·적정 공급·부족분<br>과거 실적 대비 목표 규모</td><td>확보 일정과 수요·목표의 기준기간·모집단을 확인합니다.</td></tr>
          </tbody></table></div>
          <div class="guide-columns"><section><h4>지도 색의 뜻</h4><p>가격 지도는 <b>빨강이 상승, 파랑이 하락</b>이고, 공급계획 규모가 클수록 진합니다. 주택보급률 지도는 <b>100% 이상 초록, 미만 빨강</b>이며 100%와의 차이가 클수록 진합니다. 지연 느낌표는 목표 대비 부족률 2% 이상인 사업이 있는 지역을 표시합니다.</p><p>옹진군 도서는 왼쪽 아래 별도 축척 지도에 표시합니다. 도서도 지역 선택과 통계 집계에 포함됩니다.</p></section><section><h4>숫자와 기준일의 뜻</h4><p>지역 전체 통계와 정책 귀속·근거 확정 실적은 별도 계열입니다. 부분 연도는 완결 연도 평균에 넣지 않으며, 비교 범위가 다르면 목표 배율을 보류합니다.</p><p>발표 당시 장기 평균·수요·입주 전망은 원문 기준일을 따릅니다. 미확보는 0이 아니며, 준공 후 미분양은 전체 미분양의 일부입니다.</p></section></div>
          <p>분석 자료를 전달하려면 상단 오른쪽 <b>보고서용 MD파일 만들기</b>를 누르세요. 현재 선택 조건의 그래프 수치·원천과 요구사항별 분석 프롬프트·보고서 양식을 한 파일로 저장합니다.</p><button type="button" class="guide-inline-action" data-view="supply-conditions">지역여건에서 비교하기 →</button>
        </article>
        <article id="guide-policy" class="guide-block" data-guide-topic data-guide-keywords="정책 프로그램 사업 조회 검색 목표 편집 연필 올해 누적 범위">
          <span class="guide-section-number">04 · 범위를 좁혀 보기</span><h3 tabindex="-1">정책 → 프로그램 → 사업으로 확인하기</h3>
          <div class="guide-route" aria-label="조회 순서"><span>정책 전체</span><b aria-hidden="true">→</b><span>프로그램 묶음</span><b aria-hidden="true">→</b><span>개별 사업</span></div>
          <div class="guide-columns"><section><h4>정책 전체를 볼 때</h4><ol><li>정책 개요에서 목표와 기간을 확인합니다.</li><li>지역 탭·지도를 선택해 조회 범위를 좁힙니다.</li><li>단계별 목표·측정·갭과 추진현황 통계를 비교합니다.</li></ol><p><b>전체 목표 범위</b>는 전체 물량 축으로 전환합니다. 기본 자동 축은 화면에 보이는 기간의 누적 최대값에 약 1.3을 곱해 정하며, 좌우 이동에 맞춰 조정합니다. 프로그램 목록은 <b>선택 범위의 프로그램 펼쳐보기</b>에서 조회하며, 그 아래에 지역·블록 상세 시계열과 원본 자료가 있습니다.</p><button type="button" class="guide-inline-action" data-view="policy-progress">정책 추진현황 →</button></section><section><h4>프로그램·사업을 볼 때</h4><ol><li>프로그램을 선택하거나 프로그램 추진현황을 엽니다.</li><li>상단 프로그램 선택에서 관심 묶음을 고릅니다.</li><li>구성 사업을 열어 개별 일정·공정·원천·입지를 봅니다.</li></ol><p>프로그램 목록은 저장된 <b>9·7 연결 범위</b>를 따릅니다. 독립 목표가 없는 경우 표시된 값이 연결 사업계획인지 확인합니다.</p><button type="button" class="guide-inline-action" data-view="program-progress">프로그램 추진현황 →</button></section></div>
          <div class="guide-tip"><strong>사업 이름을 알고 있다면</strong><p>사업 추진현황에서 정책명 → 프로그램명 → 포함된 사업을 선택하세요. 사업 개요와 작은 위치 지도, 단계별 목표·수집 근거, 입지 분석이 바뀝니다. <b>평균 가구소득·주택가격 부담</b>은 원천의 6개 연소득 구간별 가구 비중을 막대로 표시합니다. 평균·중위소득과 PIR도 함께 봅니다. 원천은 <b>기준·원천</b>에서 펼칩니다. 관리자는 사업명 옆 ‘사업정보수정’에서 수집된 목표일·목표량·진행일·진행량을 바로 확인하고, 빈칸을 입력하거나 값을 수정할 수 있습니다. 서류철을 누르면 어디서 어떻게 수집했는지 확인합니다. 변경자와 사유를 입력하여 저장하며 서류철 버튼으로 원천과 사용자 입력 이력을 확인합니다.</p><button type="button" class="guide-inline-action" data-view="projects">사업 찾기 →</button></div>
          <div class="guide-state-table"><table><caption>정책·프로그램 추진현황의 관리 통계 · 넓은 화면 3열 × 2행</caption><thead><tr><th scope="col">위치</th><th scope="col">통계</th><th scope="col">읽는 기준</th></tr></thead><tbody><tr><th scope="row">1행 1열</th><td>월별 실적 흐름</td><td>단계별 누적 측정값의 월 증가분</td></tr><tr><th scope="row">1행 2열</th><td>지연·주의 추이</td><td>같은 범위의 목표·측정값과 2% 기준</td></tr><tr><th scope="row">1행 3열</th><td>향후 12개월 공급 예정</td><td>확보된 미래 목표 증가분과 남은 물량</td></tr><tr><th scope="row">2행 1열</th><td>기관별 진행현황</td><td>기관별 사업계획량을 위험 상태로 한 번 집계</td></tr><tr><th scope="row">2행 2열</th><td>가구 증가와 공급 일정 비교</td><td>시도 가구 추계·재고와 확인된 준공 예정의 참고 비교</td></tr><tr><th scope="row">2행 3열</th><td>인구·가구 변화와 주택 재고</td><td>확보된 지역 통계의 기준연도·분모</td></tr></tbody></table></div><p class="guide-note">가구 규모별 변화와 시장·수급 지표는 <b>공급현황 → 지역여건</b>에서 조회합니다. 시군구 미래 가구 추계가 없으면 시도 전망을 시군구 물량에 임의 배분하지 않습니다.</p><p class="guide-note">목표를 고치려면 목표 옆 <b>연필 버튼</b>을 사용합니다. 수정은 관리자 권한과 근거가 필요합니다.</p>
        </article>
        <article id="guide-map" class="guide-block" data-guide-topic data-guide-keywords="지도 위치 입지 고용 가구 연령 미분양 인프라 학교 교통 원형 퍼센트 물음표">
          <span class="guide-section-number">05 · 위치와 입지</span><h3 tabindex="-1">지도에서는 왼쪽 진행, 오른쪽 입지를 봅니다</h3>
          <div class="guide-map-layout"><section><strong>왼쪽 · 정책과 사업 진행</strong><p>정책·프로그램·사업, 목표·계획·확인량과 근거를 봅니다.</p></section><span aria-hidden="true">지도에서<br>지역·사업 선택</span><section><strong>오른쪽 · 입지와 지역 여건</strong><p>고용, 가구 구성, 연령, 미분양·준공 후 미분양, 핵심 인프라를 봅니다.</p></section></div>
          <ol><li><b>공급현황 → 공급현황 지도</b>를 열고 지역·사업을 선택합니다.</li><li>지도 위 한 줄의 <b>전국 / 시도 / 사업</b>에서 표시 범위를 고릅니다. 전국은 서울·인천·경기 카드가 보이는 수도권 시야, 시도는 시군구 원그래프가 보이는 확대 시야, 사업은 개별 사업 위치로 전환됩니다.</li><li><b>범주</b>에서 정책·프로그램·지역을 고르고, <b>블록 이동</b>에서 사업 위치로 이동합니다. 시도·시군구에서는 단계별 구성과 도달량, 사업에서는 목표·측정 막대와 근거를 확인합니다.</li><li>오른쪽 바로가기에서 고용·가구·연령·미분양·인프라를 선택합니다.</li></ol>
          <div class="guide-columns"><section><h4>동그라미의 퍼센트는?</h4><p><b>전체 단계</b>: 계획 물량 중 사업화~입주에 도달한 물량의 비율입니다. 원형 조각은 단계별 구성입니다.</p><p><b>단계 선택</b>: 해당 단계와 이후 단계의 물량을 포함합니다. 건설을 선택하면 공급·입주 단계로 넘어간 물량도 건설 도달에 포함됩니다.</p></section><section><h4>입지 숫자는 어떻게 읽나요?</h4><p>기준연도·지역·분모를 확인합니다. 가구 비율과 연령 비율은 분모가 다릅니다. 시군구 대신 시도 참고 자료가 표시되는 경우 그 범위를 확인하세요.</p><p>준공 후 미분양은 전체 미분양의 일부입니다. 둘을 더하거나 특정 사업의 미입주량으로 읽지 않습니다.</p></section></div>
          <p>블록을 선택하면 <b>500m·1km·3km</b> 반경을 확인합니다. 주변 기존 건물의 <b>투명도</b>는 기본 50%이며 슬라이더로 조절합니다. 시설 아이콘을 누르면 확보된 학생·교원 수, 어린이집 정원·현원, 버스 노선·배차간격, 지하철 노선·시간표 간격, 병원 진료과목, 대형마트 휴점일·영업시간을 확인할 수 있습니다. 항목별 원천이 없으면 미확보로 표시합니다. 시설 원천과 표시 기준은 <b>입지 지표의 기준·원천</b>에서 펼칩니다.</p><p class="guide-note"><b>대표 위치·근사 모델</b>은 위치 참고입니다. 공식 사업 경계나 실제 아파트 동의 높이를 뜻하지 않습니다. 시설 거리는 학교 배정·수용능력의 확정 정보와도 다릅니다.</p><p class="guide-note">패널은 각각 접을 수 있습니다. 모바일에서는 아래 <b>정책 / 입지</b> 버튼으로 전환합니다.</p><button type="button" class="guide-inline-action" data-view="overview">공급현황 지도에서 확인 →</button>
        </article>
        <article id="guide-meaning" class="guide-block" data-guide-topic data-guide-keywords="그래프 색 범례 사선 목표 현황 차이 격차 지연 확인 예정 실제 기간 분기 하반기 수치">
          <span class="guide-section-number">06 · 그래프 읽기</span><h3 tabindex="-1">색은 단계, 무늬는 자료의 성격입니다</h3><p>먼저 범례를 선택해 관심 단계를 강조하세요. 목표와 현황은 선 대신 <b>면</b>으로 비교합니다.</p>
          <div class="guide-stage-legend" aria-label="진행 단계 색상"><span><i class="guide-stage-policy">1</i>정책</span><span><i class="guide-stage-business">2</i>사업화</span><span><i class="guide-stage-approval">3</i>인허가</span><span><i class="guide-stage-construction">4</i>건설</span><span><i class="guide-stage-supply">5</i>공급</span><span><i class="guide-stage-movein">6</i>입주</span></div>
          <p class="guide-note"><b>정책 구간</b>에는 아직 사업이나 단계가 확인되지 않은 목표 물량도 포함될 수 있습니다. 이 구간을 실제 사업의 진행 실적으로 읽지 마세요.</p>
          <div class="guide-surface-legend"><span><i class="guide-fill-actual"></i><b>실색 면</b> 현재 단계 물량</span><span><i class="guide-fill-plan"></i><b>연한색</b> 현재 시점 이후 예상</span><span><i class="guide-fill-unknown"></i><b>회색 배경</b> 단계 미확인</span><span><i class="guide-fill-gap"></i><b>붉은색 사선</b> 목표 물량 대비 부족분</span></div>
          <figure class="guide-chart-example"><svg viewBox="0 0 500 214" role="img" aria-labelledby="guide-chart-title guide-chart-desc"><title id="guide-chart-title">목표면과 확인 현황면 사이의 격차를 읽는 예시</title><desc id="guide-chart-desc">목표는 점선, 측정값은 실선과 실색 면으로 표시합니다. 각 단계는 해당 누적량에서 다음 단계 누적량을 뺀 물량으로 표시하고, 목표 물량 대비 부족분에 붉은색 사선을 표시합니다. 실제 사업 수치를 사용하지 않은 사용법 예시입니다.</desc><defs><pattern id="guide-shortfall" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 8L8 0" stroke="#b51f38" stroke-width="1.2"/></pattern></defs><path d="M30 172L115 113L235 49L465 28L465 181L30 181Z" fill="#e4f1f8"/><path d="M30 175L115 142L235 101L235 181L30 181Z" fill="#0072b2"/><path d="M30 172L115 113L235 49L465 28" fill="none" stroke="#0072b2" stroke-width="2" stroke-dasharray="7 4"/><path d="M30 172L115 113L235 49L235 101L115 142L30 175Z" fill="url(#guide-shortfall)"/><path d="M235 15V181" stroke="#183e59" stroke-width="1.5" stroke-dasharray="4 4"/><text x="245" y="24">예상 물량</text><text x="145" y="155" fill="#fff">현재 물량</text><text x="109" y="91">목표 물량 부족분</text><text x="235" y="202" text-anchor="middle">기준일</text></svg><figcaption>한 단계의 읽는 방법 예시 · 실색은 해당 누적량 − 다음 누적량, 빗금은 목표 물량 대비 부족분입니다. 사업화부터 입주까지 순서대로 쌓고 현재 시점 이후는 단계별 현재 실적·목표 중 큰 물량에서 출발하여, 이후 예정일별 단계 이동을 반영한 연한 예상값입니다. Y축 상한은 화면에 표시되는 기간의 누적 최대값 × 약 1.3입니다. 처음 버튼은 포함 사업 중 가장 이른 시작일로, 현재 버튼은 오늘로, 마지막 버튼은 그래프 끝으로 이동합니다. 날짜 입력은 카드 조회값과 기준 막대만 바꾸며 그래프의 실적·예상 전환점은 현재 시점에 고정됩니다.</figcaption></figure>
          <p><b>예:</b> 같은 단계·범위·기준일에서 기한이 도래한 목표가 100호, 확인량이 80호라면 차이는 20호입니다. 실제 이행과 물량 범위를 검토한 뒤 지연을 판단합니다. 실제 근거가 없다면 0호로 놓고 지연을 확정하지 않습니다.</p>
          <div class="guide-columns"><section><h4>수치를 비교하기 전 4가지</h4><ol><li>같은 정책·지역·사업 범위인가?</li><li>같은 단계·물량 정의인가?</li><li>목표 기한과 실제 근거 기준일은 언제인가?</li><li>전체 물량과 부분 모집량이 섞이지 않았는가?</li></ol></section><section><h4>예정일과 실제는 다릅니다</h4><ul><li>준공 예정은 건설 일정이며 공급·입주일의 대체값이 아닙니다.</li><li>착공~준공의 0~100% 계획은 기간 비례 추정입니다. 실제 공정률은 날짜 있는 관측자료로 확인합니다.</li><li>3분기는 9월, 하반기는 12월에 표시하지만 원문은 범위 일정입니다.</li><li>입주 시작 확인 물량과 실제 거주 세대수는 다릅니다.</li></ul></section></div>
        </article>
        <article id="guide-data" class="guide-block" data-guide-topic data-guide-keywords="자료 데이터 원천 근거 오류 이력 미확보 미정 연결 수집 상태 CSV 다운로드 보고서 MD 외부 AI 프롬프트 공통 과제">
          <span class="guide-section-number">07 · 자료와 오류 확인</span><h3 tabindex="-1">‘미확보’가 보이면 이 순서로 확인하세요</h3>
          <ol class="guide-steps"><li><div><strong>사업별 수집연계에서 사업을 찾습니다.</strong><p>정책·지역·사업명과 <b>확인할 상태</b> 조건을 선택합니다.</p></div></li><li><div><strong>사업×단계 표의 해당 칸을 누릅니다.</strong><p>위쪽 목표·예정 일정과 아래쪽 확보 정보를 확인합니다. 하나만 확보된 경우에는 해당 정보만 표시됩니다.</p></div></li><li><div><strong>원천과 연결 사유를 확인합니다.</strong><p><b>전체 흐름</b>은 <b>정책 → 사업화 → 인허가 → 건설 → 공급 → 입주</b> 순서입니다. <b>1~6 단계 탭</b>에서는 기존의 수집 원천·연결 키·보완 경로 도식을 확인합니다. 정책·프로그램 ID로 사업을 찾고, 각 단계의 자료를 같은 <b>사업 ID</b>에 연결합니다. 전체 흐름의 <b>네모</b>는 연결한 이유와 실제 근거 자료명·기준일·원문 링크를, <b>화살표</b>는 두 단계의 대조 정보와 연결 사유를 <b>팝업</b>으로 보여줍니다. 자료별 카드에서 <b>연결 사유 → 근거 자료 → 확인한 내용</b>을 읽고 원문을 열 수 있습니다. 팝업 안에서 사업을 선택하면 해당 사업만 표시합니다. 정책·프로그램·사업 ID는 매칭·배정 후 사용하는 내부 관리번호입니다. 1~6 탭 상세도 팝업으로 열리며 닫기 버튼이나 Esc로 닫습니다. 화살표의 건수는 양쪽 단계에 자료가 연결된 사업 수입니다.</p></div></li><li><div><strong>공통 과제와 조치 이력을 펼칩니다.</strong><p>기관·단계별 묶음의 사업 버튼을 누르면 해당 칸으로 이동합니다. 오류 유형별 건수를 펼쳐 원인·조치·남은 확인을 봅니다.</p></div></li></ol>
          <div class="guide-state-table"><table><caption>표에 표시된 상태와 다음 행동</caption><thead><tr><th scope="col">상태</th><th scope="col">뜻</th><th scope="col">무엇을 할까요?</th></tr></thead><tbody><tr><th scope="row">원천 확보</th><td>연결된 자료가 있습니다.</td><td>날짜·적용 물량·검토 상태와 원문을 확인합니다.</td></tr><tr><th scope="row">미정</th><td>원문이 일정 미정을 명시합니다.</td><td>나중에 발표되는 변경 일정을 확인합니다.</td></tr><tr><th scope="row">아직 계획 미수립</th><td>근거로 계획 미수립을 확인했습니다.</td><td>판정 근거·기준일과 다음 계획을 확인합니다.</td></tr><tr><th scope="row">수집 필요</th><td>필요한 자료를 아직 가져오지 못했습니다.</td><td>목록·상세·첨부·조회 기간 누락을 확인합니다.</td></tr><tr><th scope="row">연결 필요</th><td>후보 자료는 있지만 같은 사업인지 미확인입니다.</td><td>지역·블록·물량·원천을 대조합니다.</td></tr><tr><th scope="row">수집 방안 미확인</th><td>제공처·확보 방법이 미확인입니다.</td><td>공통 수집 과제와 기관 요청 항목을 확인합니다.</td></tr></tbody></table></div>
          <p class="guide-note"><b>미확보는 0호가 아닙니다.</b> 원천 확보와 담당자 확정도 다릅니다. ‘확인 필요’ 연결은 최종 검토 전 후보로 읽으세요.</p><div class="guide-actions"><button type="button" class="button" data-view="project-collection">사업별 수집연계 열기 →</button><button type="button" class="button secondary" data-view="sources">출처·수집 상태 보기</button></div>
          <h4 id="guide-estimate-rule">미측정 항목의 추정값 산정 기준 · 2026-10-22</h4><p><b>수집값 우선 → 확인 사건과 선후관계 검증 → 합당한 미확보 항목만 같은 단계 목표값으로 추정</b>합니다. 목표일 경과만으로 실적을 만들지 않습니다. 수집된 날짜·0호·부분 물량은 보존하며, 목표·추정값을 다른 추정의 사건 근거로 쓰지 않습니다.</p><p>사업화→인허가→착공→준공→입주, 인허가→공급→입주 순서를 확인합니다. <b>공급은 착공 전에도 가능하므로 인허가·공급만으로 착공을 추정하지 않습니다.</b> 실제 준공·입주 또는 수집된 양의 공정률은 이전 착공의 근거가 될 수 있습니다. 공정률 관측일은 실제 착공일로 복사하지 않고 날짜 경계로만 사용합니다.</p><p>추정 목표일이 확인된 선행 사건보다 빠르거나 후행 사건·관측일보다 늦으면 채우지 않습니다. 후행 단계의 부분 물량만 확인된 경우 전체 목표량으로 확대하지 않습니다. 미래 목표·미진행·목표 미확보·수집값 상충·독립 사건 근거 부족은 빈 값이나 확인 대기로 남깁니다. 추정 표시와 필드별 목표·확인 사건 근거, 변경 이력을 보존합니다.</p><p>사업 보고서의 범례는 옅은 파랑이 목표, 분홍 ●가 수집 측정일, 분홍 ○가 선후관계 검증 후 목표 동일 추정일입니다. 추정을 포함한 100%를 실제 완료 확인으로 해석하지 않습니다. 정책·프로그램 보고서는 기존 형식을 유지하며 범례에 선 색과 모양을 표시합니다.</p><h4>수집량과 소스 유형을 비교하려면</h4><p><b>출처와 수집현황</b> 상단에서 수집 출처·추출 데이터·연결 데이터의 현재량과 아래 회색 글씨의 오늘 수집량을 확인합니다. 추출량은 출처·자료 구조별 <b>행 × 컬럼 수</b>를 합산하고 빈칸도 포함합니다. 연결량은 사업과 연결된 고유 원천 레코드 수입니다. 오늘은 한국시간 기준 성공 수집·재수집을 집계하며 같은 레코드의 반복은 제외합니다. 연결 데이터의 오늘 수집량은 오늘 수집한 자료 중 현재 연결된 레코드입니다. <b>소스 유형별 자세히 보기</b>를 펼치면 API 연계·보도자료·뉴스·모집공고 등 유형별 출처·행·컬럼·추출량을 비교할 수 있습니다. 각 유형에는 자료의 내용과 활용 항목을 설명하며, <b>실제 수집 자료 N개 보기</b>에서 집계에 포함된 출처명과 원문 링크를 확인합니다.</p><h4>실제 수집 샘플을 보려면</h4><p><b>데이터관리 → 출처와 수집현황</b>에서 수집항목당 한 행을 확인하고 표본 확장을 엽니다. 수집 필드와 최근 실제 저장 데이터 최대 <b>50행</b>을 표시합니다. 10행을 넘으면 표 안에서 스크롤하고, 긴 값은 셀을 눌러 전체 내용을 봅니다.</p><h4>외부 AI에 분석 보고서를 요청하려면</h4><ol><li><b>지역여건</b> 또는 <b>추진현황 → 정책·프로그램·사업</b>에서 조회 조건을 맞춥니다.</li><li>기존 상단 오른쪽 <b>보고서용 MD파일 만들기</b>를 누릅니다. 그래프를 그린 원래 수치와 기준·단위·원천, 요구사항 F-01~F-12에 대응하는 점검 질문을 저장합니다. F-10은 보고서에서 갱신·변경 관리에 집중하도록 구성합니다.</li><li>파일을 외부 AI에 첨부하고 <b>“첨부 MD의 분석 프롬프트와 출력 양식에 따라 선택 범위의 보고서를 작성해 주세요”</b>라고 요청합니다.</li><li>보고서는 <b>추진현황 점검 결과와 지금 취할 조치 → 장기 중점 관리 방향 → 수치·도표·차트로 사유 설명</b> 순서로 답하도록 설정돼 있습니다. 즉시 조치에는 대상·담당·기한·이행 지표를, 장기 관리에는 기준값·관리 지표·경보 기준·점검 주기·기준 이탈 시 조치를 담습니다. 미등록 담당·기한·기준은 제안으로 구분합니다. the주택 채택값과 담당자 확인·매칭값은 확정 분석 기준으로 사용하며, 수치 생성·검토 정보는 파일에 담지 않습니다. 최종 보고서는 <b>인쇄·배포용 A4 책자</b>로 작성하도록 지시합니다. 표지·목차·요약·본문·부록, 쪽번호·도표·출처를 갖춘 PDF를 요청하며, PDF 생성이 불가능하면 인쇄용 독립형 HTML을 제공하도록 합니다. 표 ID·JSON 경로·원문으로 생성된 답변을 확인하세요.</li></ol><p class="guide-note">파일은 브라우저에서 내려받으며 외부 AI로 자동 전송되지 않습니다. 생성 중 조회 조건을 바꾸면 현재 범위에서 다시 실행해야 합니다. 추가 조회 실패와 미확보는 파일에 따로 표시되며 실적 0으로 바꾸지 않습니다.</p><p>전달 자료가 필요하면 조회 조건을 확인한 뒤 <b>수집현황 CSV</b>를 내려받습니다. 서비스 구조·원천 정비 설명은 같은 화면의 <b>the주택 데이터 정비 방안</b>에서 확인합니다.</p>
        </article>
        <article id="guide-manage" class="guide-block" data-guide-topic data-guide-keywords="관리자 로그인 담당자 입력 목표 수정 편집 연필 승인 확정 병목 조치 일정 기준선 기관 신청 API 저장 충돌">
          <span class="guide-section-number">08 · 업무 담당자</span><h3 tabindex="-1">연결 확인·사업 목표 입력하기</h3><p>조회만 한다면 입력하지 않아도 됩니다. 목표와 연결을 저장할 담당자는 관리자 로그인 후 아래 절차를 따릅니다.</p>
          <details class="guide-manager-details"><summary>담당자 입력 절차 펼치기 · 관리자 권한 필요</summary><div>
            <ol class="guide-steps"><li><div><strong>관리자 로그인 후 연결 관리로 이동합니다.</strong><p>상단 <b>관리자 로그인</b>을 사용하고, <b>데이터관리 → 정책-프로그램-사업 연결</b>을 엽니다.</p><div class="guide-actions"><a class="button secondary" href="/admin">관리자 로그인 ↗</a><button type="button" class="guide-inline-action" data-view="tree">연결 관리 열기 →</button></div></div></li><li><div><strong>정책·프로그램·사업의 연결을 확인합니다.</strong><p>각 연결의 근거를 읽고 확인·수정·확정·해제를 선택합니다. 명칭이 비슷해도 블록·전체/부분 물량을 먼저 확인하세요.</p></div></li><li><div><strong>사업정보에서 목표와 확인한 진행값을 수정합니다.</strong><p>사업을 선택하고 <b>사업정보 수정</b>을 엽니다. <b>단계별 일정 · 상태</b>에서 목표·예정일과 진행·확인일, 물량을 구분해 입력합니다. 변경자와 확인 근거를 함께 저장하고, 미확보 값을 0으로 입력하지 않습니다.</p></div></li></ol>
            <p class="guide-note">다른 담당자가 먼저 수정했다는 메시지가 나오면 다시 조회한 뒤 조정하세요. 원천 후보 자동 갱신은 담당자의 확정·해제를 보존합니다.</p>
            <h4>정책정보와 프로그램 구성을 바꾸려면</h4><p>관리자 로그인 후 <b>추진현황 → 정책 → 정책명 옆 정책정보수정</b>를 엽니다. 화면의 입력칸에서 정책명·개요·기간·지역별/연도별 목표를 바로 수정합니다. 지역명을 누르면 연도별 목표가 전환됩니다. 진행현황 위 프로그램을 체크하고 저장하면 실제 정책–프로그램 연결이 바뀝니다. 다른 정책 소속은 이동 여부를 확인합니다. 변경자·사유를 입력해 저장하고, 서류철에서 사용자 변경값과 기존 근거를 확인하세요. 입력칸의 <b>↺ 원천값 사용</b>은 해당 입력 우선값만 해제합니다. 비로그인 화면에서는 정책정보 관리 버튼이 표시되지 않습니다.</p><h4>프로그램·사업 정보를 바꾸려면</h4><p><b>추진현황 → 프로그램</b>의 프로그램명 옆 <b>프로그램정보수정</b>, <b>추진현황 → 사업</b>의 사업명 옆 <b>사업정보수정</b>을 엽니다. 사업별 수집연계의 사업명 아래 수정 버튼에서도 같은 사업 수정 팝업을 사용합니다. 권한과 근거를 확인하고 변경자·사유를 함께 저장합니다.</p><h4>자료연도별 수집현황을 보려면</h4><p>출처와 수집현황의 <b>소스 유형별 자세히 보기</b>를 펼칩니다. 자료 종류·지역·연도별 확보 여부를 확인할 수 있습니다.</p>
          </div></details>
        </article>
        <article id="guide-help" class="guide-block" data-guide-topic data-guide-keywords="도움말 FAQ 질문">
          <span class="guide-section-number">09 · 자주 묻는 질문</span><h3 tabindex="-1">화면을 보다가 막혔나요?</h3>
          <details data-guide-faq><summary>가구 변화와 지역 통계는 어디로 옮겨졌나요?</summary><p><b>공급현황 → 지역여건</b>에서 가구 구성과 주택 기반, 주택시장과 수급, 공급 실적과 구성, 향후 공급과 목표의 네 주제로 조회합니다. 정책·프로그램의 둘째 행 가운데에는 가구 증가와 공급 일정 비교가 표시됩니다.</p></details>
          <details data-guide-faq><summary>주택보급률 지도에 빨강·초록만 보이는 이유는?</summary><p>100% 이상은 초록, 미만은 빨강이며 100%와의 차이가 클수록 진합니다. 공식 공표값과 최신 동일 정의 산출값의 기준연도를 확인하세요. 공식 시군구 값이 없으면 시도 참고값을 표시할 수 있습니다.</p></details>
          <details data-guide-faq><summary>옹진군 섬이 작은 지도에 따로 보입니다.</summary><p>먼 섬 때문에 본토가 작아지지 않도록 왼쪽 아래 별도 축척으로 표시합니다. 해당 도서도 색 기준·지역 선택·통계 집계에 포함됩니다.</p></details>
          <details data-guide-faq><summary>소득 막대와 PIR은 어떤 수치인가요?</summary><p>X축은 원천의 6개 연소득 구간(1천만원 미만~1억원 이상)입니다. 막대 높이는 각 구간의 전국 가구 비중을 그대로 표시합니다. 평균·중위소득은 별도 수치로 표시하며 월 환산은 연소득을 12로 나눕니다. PIR은 주거실태조사의 수도권·전국 참고값으로, 소득 차트 평균을 이용해 다시 계산하지 않습니다. 조사연도와 대상은 기준·원천에서 확인합니다.</p></details>
          <details data-guide-faq><summary>예정 학교·어린이집이 안 보입니다.</summary><p>공식 계획과 위치가 연결된 시설 중 지도 표현 범위에 들어오는 곳을 아이콘으로 표시합니다. 계획 원천·위치·개교·개원 일정 중 미확보 항목이 있으면 실제 시설이 없다고 단정할 수 없습니다. 확보된 예정일은 아이콘 상세에서 확인합니다.</p></details>
          <details data-guide-faq><summary>보고서용 MD 파일에는 무엇이 들어가나요?</summary><p>지역여건·정책·프로그램·사업의 선택 조건, 그래프 원래 수치와 시계열, 기준·원천, 요구사항별 점검 질문과 보고서 양식이 들어갑니다. 채택된 값은 확정 분석 기준으로 사용하고 수치 생성 경위·검토 분류는 제외합니다. 추진현황이 목표·일정에 맞는지 점검한 뒤, 지금 취할 조치와 장기 중점 관리 과제를 먼저 답하고 수치·도표·차트로 사유를 설명하도록 지시합니다. 기존 조치의 이행 여부와 후속 조치, 관리 지표·주기·경보 기준도 포함합니다. 인쇄 후 바로 배포할 수 있도록 A4 판형·표지·목차·쪽번호·도표 편집 기준도 담습니다. 이 파일을 외부 AI 모델에 첨부해 책자 제작을 요청하고, 근거 표·원문과 답변을 대조하세요.</p></details><details data-guide-faq><summary>로그인이 꼭 필요한가요?</summary><p>지도·사업·원천·수집현황 조회는 로그인 없이 가능합니다. 목표 수정, 연결 확정, 수집 실행과 조치 저장은 관리자 권한이 필요합니다.</p></details>
          <details data-guide-faq><summary>지도에서 퍼센트 대신 물음표·‘물량 미확인’이 보여요.</summary><p>계획 물량이나 단계 근거가 없어 비율을 계산할 수 없는 상태입니다. 0%로 해석하지 마세요. 선택한 사업의 계획량과 단계 근거를 사업별 수집연계에서 확인합니다.</p></details>
          <details data-guide-faq><summary>입주 정보가 있는데 인허가·건설은 왜 미확보인가요?</summary><p>입주 예정 자료와 이전 단계 원천이 서로 연결되지 않았을 수 있습니다. 사업별 수집연계의 해당 칸과 원문을 확인하세요. 후행 정보가 있다는 이유만으로 실제 승인일·착공일을 만들어 넣지는 않습니다.</p></details>
          <details data-guide-faq><summary>준공 예정일이 있는데 공급 계획에는 안 보여요.</summary><p>준공은 건설 일정이고, 공급은 분양·모집 일정입니다. 준공 예정일은 건설 칸에서 확인합니다. 공급 원천이 없으면 준공 예정으로 대신 채우지 않습니다.</p></details>
          <details data-guide-faq><summary>‘미정’이면 자료 수집에 실패한 건가요?</summary><p>원문이 날짜 미정을 명시했다면 그 상태를 확보한 것입니다. 수집 실패·원문 공란·항목 미제공·연결 필요와는 다릅니다. 상세의 일정 원문과 상태를 함께 확인하세요.</p></details>
          <details data-guide-faq><summary>프로그램이나 사업 검색 결과가 없어요.</summary><p>프로그램 목록은 현재 저장된 9·7 연결 범위입니다. 사업 검색에서는 지역·정책·검색어·조회일을 확인하고 필터 초기화 후 다시 찾으세요. 원천을 확보했어도 정책 연결 검토가 끝나지 않았을 수 있습니다.</p></details>
          <details data-guide-faq><summary>메뉴마다 숫자가 달라요.</summary><p>정책 전체 목표, 연결 사업 소계, 지역 전체 통계는 범위가 다릅니다. 단계·자료 연도·기준일과 검토 포함 여부를 맞춰 비교하세요. 단계별 누적량, 단지 총량과 금회 모집량을 더하면 중복됩니다.</p></details>
          <details data-guide-faq><summary>입주 예정·입주 시작 확인은 실제 입주 세대수인가요?</summary><p>아닙니다. 예정은 계획이고 입주 시작은 사건 확인입니다. 실제 거주 세대수와 미입주량은 같은 범위의 별도 집계가 필요합니다.</p></details>
          <details data-guide-faq><summary>대표 위치와 3D 아파트는 실제 단지인가요?</summary><p>대표·근사 위치와 가상 모델은 조회를 위한 참고 표시일 수 있습니다. 위치 근거와 공식 경계·건물 자료 확보 여부를 확인하세요. 근사 위치가 정확한 필지 PNU를 증명하지는 않습니다.</p></details>
          <details data-guide-faq><summary>사업의 목표와 일정을 수정하려면 어디로 가나요?</summary><p>관리자 로그인 후 정책-프로그램-사업 연결에서 사업을 선택하고 사업정보 수정을 엽니다. 단계별 목표·예정일과 진행·확인일을 구분하고, 변경자와 확인 근거를 함께 저장하세요.</p></details>
          <div class="guide-more"><strong>요구사항과 기능 구현도 확인하고 싶다면</strong><p>문서 → 요구사항정의에서 항목별 기능·이용 경로·자료 확보 상태를 확인하세요.</p><button type="button" class="guide-inline-action" data-view="requirements">요구사항정의 열기 →</button><a href="/poc/home/assets/reports/HOME_DATA_REMEDIATION_20261013.html" target="_blank" rel="noopener">the주택 데이터 정비 방안 ↗</a></div>
        </article>
      </div>
    </div>`;
  const host=()=>document.getElementById('home-user-guide');
  const input=()=>document.getElementById('guide-search');
  const words=value=>value.trim().toLocaleLowerCase('ko-KR').split(/\s+/).filter(Boolean);
  function matches(node,tokens){const text=(node.textContent+' '+(node.dataset.guideKeywords||'')).toLocaleLowerCase('ko-KR');return tokens.every(t=>text.includes(t));}
  function filter(){
    const tokens=words(input().value),faqs=[...host().querySelectorAll('[data-guide-faq]')];
    const faqTokens=tokens.filter(t=>!['faq','도움말','자주','묻는','질문','자주묻는질문'].includes(t));
    if(tokens.length&&!searchOpen)searchOpen=faqs.map(n=>n.open);
    for(const [i,node] of faqs.entries()){
      node.hidden=!matches(node,faqTokens);
      if(tokens.length&& !node.hidden)node.open=true;
      else if(!tokens.length&&searchOpen)node.open=searchOpen[i];
    }
    if(!tokens.length)searchOpen=null;
    let count=0;
    for(const topic of host().querySelectorAll('[data-guide-topic]')){
      topic.hidden=!matches(topic,tokens)||(topic.id==='guide-help'&&tokens.length&&!faqs.some(n=>!n.hidden));
      if(!topic.hidden)count++;
    }
    document.getElementById('guide-no-results').hidden=count>0;
    document.getElementById('guide-search-status').textContent=tokens.length?`검색 결과 ${count}개 안내`:host().querySelectorAll('[data-guide-topic]').length+'개 안내 · 화면에서 바로 따라 하기';
    for(const button of host().querySelectorAll('.guide-nav button'))button.classList.toggle('guide-search-match',tokens.length>0&&!document.getElementById(button.dataset.guideSection).hidden);
  }
  function clear(){input().value='';filter();}
  function beforePrint(){
    if(!ready||document.getElementById('pane-manual').hidden||printState)return;
    printState={query:input().value,details:[...host().querySelectorAll('details')].map(n=>n.open)};
    clear();host().querySelectorAll('details').forEach(n=>n.open=true);
  }
  function afterPrint(){
    if(!printState)return;
    input().value=printState.query;filter();
    [...host().querySelectorAll('details')].forEach((n,i)=>n.open=printState.details[i]);printState=null;
  }
  function setup(){
    host().innerHTML=content;
    input().addEventListener('input',filter);
    host().addEventListener('click',event=>{
      const view=event.target.closest('[data-view]');
      if(view){event.stopPropagation();setView(view.dataset.view);window.scrollTo({top:0,behavior:'auto'});const label=document.getElementById('page-label');label.tabIndex=-1;label.focus({preventScroll:true});return;}
      const jump=event.target.closest('[data-guide-section]');
      if(jump){clear();const target=document.getElementById(jump.dataset.guideSection);if(!target)return;target.querySelector('details.guide-manager-details')?.setAttribute('open','');target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});target.querySelector('h3')?.focus({preventScroll:true});return;}
      if(event.target.closest('#guide-reset-search')){clear();input().focus();}
      if(event.target.closest('#guide-print')){beforePrint();window.print();}
    });
    window.addEventListener('beforeprint',beforePrint);window.addEventListener('afterprint',afterPrint);
    ready=true;filter();
  }
  return {visible(){if(!ready)setup();}};
})();
