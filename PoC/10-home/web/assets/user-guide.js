'use strict';
/* Read-only user guidance: no API calls, no changes to filters or saved data. */
const UserGuide = (() => {
  let ready=false, printState=null, searchOpen=null;
  const content=String.raw`
    <div class="guide-hero">
      <div><span class="guide-kicker">처음 쓰는 HOME</span><h3>정책이 계획대로 진행되고 있는지,<br>사업과 근거까지 확인해 보세요.</h3><p>처음에는 정책별 추진현황에서 시작하세요. 지역을 고르고 목표와 현황을 비교한 뒤, 확인이 필요한 사업의 근거를 열면 됩니다.</p><div class="guide-actions"><button type="button" class="button" data-view="policy-progress">9·7 정책부터 보기 →</button><button type="button" class="button secondary" data-guide-section="guide-start">3분 따라하기</button></div></div>
      <aside class="guide-access"><strong>조회는 로그인 없이</strong><p>지도·사업·원천·수집현황을 누구나 볼 수 있습니다.</p><strong>입력·확정은 관리자 로그인 후</strong><p>목표 수정과 연결 검토는 업무 담당자가 근거를 확인하고 저장합니다.</p></aside>
    </div>
    <div class="guide-controls"><label for="guide-search">어떤 도움이 필요한가요?<input id="guide-search" type="search" placeholder="예: 지연, 목표 수정, 미정, 입주, CSV" autocomplete="off"></label><div><output id="guide-search-status" role="status" aria-live="polite"></output><button id="guide-print" type="button" class="button secondary">인쇄 / PDF 저장</button></div></div>
    <div class="guide-tasks" aria-label="원하는 작업 바로 시작">
      <article><span>01 · 정책 판단</span><h4>어디가 지연되는지 보고 싶어요</h4><p>지역을 선택하고 목표면·현황면과 우선 점검 사업을 봅니다.</p><button type="button" data-view="policy-progress">정책별 추진현황 열기 →</button></article>
      <article><span>02 · 사업 확인</span><h4>특정 사업의 일정을 찾고 싶어요</h4><p>사업명으로 검색하고 단계·예정일·원문을 확인합니다.</p><button type="button" data-view="projects">사업별 추진현황 열기 →</button></article>
      <article><span>03 · 위치와 입지</span><h4>주변 여건도 함께 보고 싶어요</h4><p>지도에서 지역·사업을 고르고 오른쪽 입지 정보를 봅니다.</p><button type="button" data-view="overview">공급 지도 열기 →</button></article>
      <article><span>04 · 자료 점검</span><h4>왜 미확보인지 알고 싶어요</h4><p>사업×단계 표와 연결 다이어그램에서 누락 원인을 찾습니다.</p><button type="button" data-view="project-collection">사업별 수집·연계 열기 →</button></article>
    </div>
    <div class="guide-layout">
      <nav class="guide-nav" aria-label="사용 안내 목차"><strong>필요한 설명 찾기</strong><button type="button" data-guide-section="guide-start">1. 3분 따라하기</button><button type="button" data-guide-section="guide-policy">2. 정책·프로그램·사업</button><button type="button" data-guide-section="guide-map">3. 지도와 입지</button><button type="button" data-guide-section="guide-meaning">4. 그래프·수치 읽기</button><button type="button" data-guide-section="guide-data">5. 자료·오류 확인</button><button type="button" data-guide-section="guide-manage">6. 담당자 입력</button><button type="button" data-guide-section="guide-help">7. 자주 묻는 질문</button></nav>
      <div class="guide-reading">
        <p id="guide-no-results" class="guide-no-results" hidden>일치하는 안내가 없습니다. 짧은 단어로 다시 검색하거나 <button id="guide-reset-search" type="button">전체 안내 보기</button>를 선택하세요.</p>
        <article id="guide-start" class="guide-block" data-guide-topic data-guide-keywords="초보 시작 처음 빠른 사용 방법">
          <span class="guide-section-number">01 · 시작하기</span><h3 tabindex="-1">3분 따라하기: 서울의 정책 진행 확인</h3><p>다음 순서로 한 번만 따라 해 보세요. 목표와 현황이 다른 이유를 사업 근거까지 확인하는 흐름입니다.</p>
          <ol class="guide-steps">
            <li><div><strong>정책별 추진현황을 엽니다.</strong><p>왼쪽 <b>정책현황 → 정책별 추진현황</b>을 선택합니다. 상단 정책은 9·7입니다.</p><button type="button" class="guide-inline-action" data-view="policy-progress">이 화면 열기 →</button></div></li>
            <li><div><strong>지역 탭에서 ‘서울’을 선택합니다.</strong><p>정책 개요 오른쪽의 <b>전체 / 서울 / 경기 / 인천</b> 탭을 사용합니다. 지도와 아래 그래프의 범위·Y축이 서울에 맞게 바뀝니다.</p></div></li>
            <li><div><strong>단계와 기준 연도를 고릅니다.</strong><p>사업화·인허가·건설·공급·입주 중 관심 단계를 선택하고 연도 조절기로 기준 연도를 맞춥니다. 월별 흐름은 그래프의 시간 단위에서 선택합니다.</p></div></li>
            <li><div><strong>목표 대비 부족·지연 영역을 확인합니다.</strong><p>사선 목표면과 실색 현황면의 차이를 보고, 부족률을 확인합니다. <b>2% 이상은 지연(빨강)</b>, <b>0% 초과~2% 미만은 주의(노랑)</b>로 관리합니다. 자료가 없으면 판단이 보류될 수 있습니다.</p></div></li>
            <li><div><strong>대상 사업의 근거를 엽니다.</strong><p>구성 사업이나 프로그램에서 상세로 이동합니다. <b>목표 기한, 실제 근거 날짜, 적용 물량, 원문</b>을 함께 확인합니다. 이전 단계 자료가 빠졌다면 사업별 수집·연계에서 이유를 봅니다.</p></div></li>
          </ol><p class="guide-result"><b>여기까지 하면</b> 선택 지역의 목표·현황·확인할 사업과 그 근거를 설명할 수 있습니다.</p>
        </article>
        <article id="guide-policy" class="guide-block" data-guide-topic data-guide-keywords="정책 프로그램 사업 조회 검색 목표 편집 연필 올해 누적 범위">
          <span class="guide-section-number">02 · 범위를 좁혀 보기</span><h3 tabindex="-1">정책 → 프로그램 → 사업으로 확인하기</h3>
          <div class="guide-route" aria-label="조회 순서"><span>정책 전체</span><b aria-hidden="true">→</b><span>프로그램 묶음</span><b aria-hidden="true">→</b><span>개별 사업</span></div>
          <div class="guide-columns"><section><h4>정책 전체를 볼 때</h4><ol><li>정책 개요에서 목표와 기간을 확인합니다.</li><li>지역 탭·지도를 선택해 조회 범위를 좁힙니다.</li><li>진행 그래프와 우선 점검 사업을 비교합니다.</li></ol><p><b>올해 사업 기준</b>은 기본 체크 해제입니다. 체크하면 올해 누적 목표 범위로 Y축을 조정하므로 정책 전체 목표 축과 구분합니다.</p><button type="button" class="guide-inline-action" data-view="policy-progress">정책별 추진현황 →</button></section><section><h4>프로그램·사업을 볼 때</h4><ol><li>프로그램을 선택하거나 프로그램별 추진현황을 엽니다.</li><li>상단 프로그램 선택에서 관심 묶음을 고릅니다.</li><li>구성 사업을 열어 개별 일정·공정·원천·입지를 봅니다.</li></ol><p>프로그램 목록은 저장된 <b>9·7 연결 범위</b>를 따릅니다. 독립 목표가 없는 경우 표시된 값이 연결 사업계획인지 확인합니다.</p><button type="button" class="guide-inline-action" data-view="program-progress">프로그램별 추진현황 →</button></section></div>
          <div class="guide-tip"><strong>사업 이름을 알고 있다면</strong><p>사업별 추진현황에서 정책명 → 프로그램명 → 포함된 사업을 선택하세요. 사업 개요와 작은 위치 지도, 단계별 목표·수집 근거, 입지 분석이 바뀝니다. 관리자는 사업명 옆 ‘사업정보수정’에서 수집된 목표일·목표량·진행일·진행량을 바로 확인하고, 빈칸을 입력하거나 값을 수정할 수 있습니다. 서류철을 누르면 어디서 어떻게 수집했는지 확인합니다. 변경자와 사유를 입력하여 저장하며 서류철 버튼으로 원천과 사용자 입력 이력을 확인합니다.</p><button type="button" class="guide-inline-action" data-view="projects">사업 찾기 →</button></div>
          <p class="guide-note">목표를 고치려면 목표 옆 <b>연필 버튼</b>을 사용합니다. 수정은 관리자 권한과 근거가 필요합니다.</p>
        </article>
        <article id="guide-map" class="guide-block" data-guide-topic data-guide-keywords="지도 위치 입지 고용 가구 연령 미분양 인프라 학교 교통 원형 퍼센트 물음표">
          <span class="guide-section-number">03 · 위치와 지역 여건</span><h3 tabindex="-1">지도에서는 왼쪽 진행, 오른쪽 입지를 봅니다</h3>
          <div class="guide-map-layout"><section><strong>왼쪽 · 정책과 사업 진행</strong><p>정책·프로그램·사업, 목표·계획·확인량과 근거를 봅니다.</p></section><span aria-hidden="true">지도에서<br>지역·사업 선택</span><section><strong>오른쪽 · 입지와 지역 여건</strong><p>고용, 가구 구성, 연령, 미분양·준공 후 미분양, 핵심 인프라를 봅니다.</p></section></div>
          <ol><li><b>공급현황 → 공급 지도</b>를 열고 지역·사업을 선택합니다.</li><li>자료 연도와 예정량 기준을 확인합니다. 단계 기본값은 <b>전체 단계</b>입니다.</li><li>원형 표시에서 단계별 구성과 도달률을 보고 사업 근거를 확인합니다.</li><li>오른쪽 바로가기에서 고용·가구·연령·미분양·인프라를 선택합니다.</li></ol>
          <div class="guide-columns"><section><h4>동그라미의 퍼센트는?</h4><p><b>전체 단계</b>: 계획 물량 중 사업화~입주에 도달한 물량의 비율입니다. 원형 조각은 단계별 구성입니다.</p><p><b>단계 선택</b>: 해당 단계와 이후 단계의 물량을 포함합니다. 건설을 선택하면 공급·입주 단계로 넘어간 물량도 건설 도달에 포함됩니다.</p></section><section><h4>입지 숫자는 어떻게 읽나요?</h4><p>기준연도·지역·분모를 확인합니다. 가구 비율과 연령 비율은 분모가 다릅니다. 시군구 대신 시도 참고 자료가 표시되는 경우 그 범위를 확인하세요.</p><p>준공 후 미분양은 전체 미분양의 일부입니다. 둘을 더하거나 특정 사업의 미입주량으로 읽지 않습니다.</p></section></div>
          <p class="guide-note"><b>대표 위치·근사 모델</b>은 위치 참고입니다. 공식 사업 경계나 실제 아파트 동의 높이를 뜻하지 않습니다. 시설 거리는 학교 배정·수용능력의 확정 정보와도 다릅니다.</p><p class="guide-note">패널은 각각 접을 수 있습니다. 모바일에서는 아래 <b>정책 / 입지</b> 버튼으로 전환합니다.</p><button type="button" class="guide-inline-action" data-view="overview">공급 지도에서 확인 →</button>
        </article>
        <article id="guide-meaning" class="guide-block" data-guide-topic data-guide-keywords="그래프 색 범례 사선 목표 현황 차이 격차 지연 확인 예정 실제 기간 분기 하반기 수치">
          <span class="guide-section-number">04 · 그래프 읽기</span><h3 tabindex="-1">색은 단계, 무늬는 자료의 성격입니다</h3><p>먼저 범례를 선택해 관심 단계를 강조하세요. 목표와 현황은 선 대신 <b>면</b>으로 비교합니다.</p>
          <div class="guide-stage-legend" aria-label="진행 단계 색상"><span><i class="guide-stage-policy">1</i>정책</span><span><i class="guide-stage-business">2</i>사업화</span><span><i class="guide-stage-approval">3</i>인허가</span><span><i class="guide-stage-construction">4</i>건설</span><span><i class="guide-stage-supply">5</i>공급</span><span><i class="guide-stage-movein">6</i>입주</span></div>
          <p class="guide-note"><b>정책 구간</b>에는 아직 사업이나 단계가 확인되지 않은 목표 물량도 포함될 수 있습니다. 이 구간을 실제 사업의 진행 실적으로 읽지 마세요.</p>
          <div class="guide-surface-legend"><span><i class="guide-fill-actual"></i><b>실색 면</b> 확인된 현황</span><span><i class="guide-fill-plan"></i><b>사선 면</b> 목표·예정</span><span><i class="guide-fill-unknown"></i><b>회색 점</b> 단계 미확인</span><span><i class="guide-fill-gap"></i><b>빨간 격차</b> 지연 · 2% 이상</span><span><i class="d907-key-warning"></i><b>노란 격차</b> 주의 · 2% 미만</span></div>
          <figure class="guide-chart-example"><svg viewBox="0 0 500 214" role="img" aria-labelledby="guide-chart-title guide-chart-desc"><title id="guide-chart-title">목표면과 확인 현황면 사이의 격차를 읽는 예시</title><desc id="guide-chart-desc">사선 목표면이 실색 현황면 위에 있고, 기준일 이전의 두 면 차이가 빨간 격차로 표시됩니다. 실제 사업 수치를 사용하지 않은 사용법 예시입니다.</desc><defs><pattern id="guide-plan-pattern" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 7L7 0" stroke="#0072b2" stroke-width="1.2"/></pattern><pattern id="guide-gap-pattern" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 0L7 7M0 7L7 0" stroke="#c43150" stroke-width="1"/></pattern></defs><path d="M30 172L115 113L235 49L465 28L465 181L30 181Z" fill="#e4f1f8"/><path d="M30 172L115 113L235 49L465 28L465 181L30 181Z" fill="url(#guide-plan-pattern)"/><path d="M30 175L115 142L235 101L465 71L465 181L30 181Z" fill="#0072b2"/><path d="M115 113L235 49L235 101L115 142Z" fill="#fce2e7"/><path d="M115 113L235 49L235 101L115 142Z" fill="url(#guide-gap-pattern)"/><path d="M235 15V181" stroke="#183e59" stroke-width="1.5" stroke-dasharray="4 4"/><text x="245" y="24">목표·예정</text><text x="300" y="135" fill="#fff">확인 현황</text><text x="109" y="91">지연 · 2% 이상</text><text x="235" y="202" text-anchor="middle">기준일</text></svg><figcaption>읽는 방법 예시 · 실제 정책·사업 수치가 아닙니다.</figcaption></figure>
          <p><b>예:</b> 같은 단계·범위·기준일에서 기한이 도래한 목표가 100호, 확인량이 80호라면 차이는 20호입니다. 실제 이행과 물량 범위를 검토한 뒤 지연을 판단합니다. 실제 근거가 없다면 0호로 놓고 지연을 확정하지 않습니다.</p>
          <div class="guide-columns"><section><h4>수치를 비교하기 전 4가지</h4><ol><li>같은 정책·지역·사업 범위인가?</li><li>같은 단계·물량 정의인가?</li><li>목표 기한과 실제 근거 기준일은 언제인가?</li><li>전체 물량과 부분 모집량이 섞이지 않았는가?</li></ol></section><section><h4>예정일과 실제는 다릅니다</h4><ul><li>준공 예정은 건설 일정이며 공급·입주일의 대체값이 아닙니다.</li><li>착공~준공의 0~100% 계획은 기간 비례 추정입니다. 실제 공정률은 날짜 있는 관측자료로 확인합니다.</li><li>3분기는 9월, 하반기는 12월에 표시하지만 원문은 범위 일정입니다.</li><li>입주 시작 확인 물량과 실제 거주 세대수는 다릅니다.</li></ul></section></div>
        </article>
        <article id="guide-data" class="guide-block" data-guide-topic data-guide-keywords="자료 데이터 원천 근거 오류 이력 미확보 미정 연결 수집 상태 CSV 다운로드 공통 과제">
          <span class="guide-section-number">05 · 자료와 오류 확인</span><h3 tabindex="-1">‘미확보’가 보이면 이 순서로 확인하세요</h3>
          <ol class="guide-steps"><li><div><strong>사업별 수집·연계에서 사업을 찾습니다.</strong><p>정책·지역·사업명과 <b>확인할 상태</b> 조건을 선택합니다.</p></div></li><li><div><strong>사업×단계 표의 해당 칸을 누릅니다.</strong><p>위쪽 목표·예정 일정과 아래쪽 확보 정보를 확인합니다. 하나만 확보된 경우에는 해당 정보만 표시됩니다.</p></div></li><li><div><strong>원천과 연결 사유를 확인합니다.</strong><p>다이어그램의 상자·화살표를 누르면 원천·연결키·단절 사유를 볼 수 있습니다. 상세에서 원문과 자료 기준일을 확인하세요.</p></div></li><li><div><strong>공통 과제와 조치 이력을 펼칩니다.</strong><p>기관·단계별 묶음의 사업 버튼을 누르면 해당 칸으로 이동합니다. 오류 유형별 건수를 펼쳐 원인·조치·남은 확인을 봅니다.</p></div></li></ol>
          <div class="guide-state-table"><table><caption>표에 표시된 상태와 다음 행동</caption><thead><tr><th scope="col">상태</th><th scope="col">뜻</th><th scope="col">무엇을 할까요?</th></tr></thead><tbody><tr><th scope="row">원천 확보</th><td>연결된 자료가 있습니다.</td><td>날짜·적용 물량·검토 상태와 원문을 확인합니다.</td></tr><tr><th scope="row">미정</th><td>원문이 일정 미정을 명시합니다.</td><td>나중에 발표되는 변경 일정을 확인합니다.</td></tr><tr><th scope="row">아직 계획 미수립</th><td>근거로 계획 미수립을 확인했습니다.</td><td>판정 근거·기준일과 다음 계획을 확인합니다.</td></tr><tr><th scope="row">수집 필요</th><td>필요한 자료를 아직 가져오지 못했습니다.</td><td>목록·상세·첨부·조회 기간 누락을 확인합니다.</td></tr><tr><th scope="row">연결 필요</th><td>후보 자료는 있지만 같은 사업인지 미확인입니다.</td><td>지역·블록·물량·원천을 대조합니다.</td></tr><tr><th scope="row">수집 방안 미확인</th><td>제공처·확보 방법이 미확인입니다.</td><td>공통 수집 과제와 기관 요청 항목을 확인합니다.</td></tr></tbody></table></div>
          <p class="guide-note"><b>미확보는 0호가 아닙니다.</b> 원천 확보와 담당자 확정도 다릅니다. ‘확인 필요’ 연결은 최종 검토 전 후보로 읽으세요.</p><div class="guide-actions"><button type="button" class="button" data-view="project-collection">사업별 수집·연계 열기 →</button><button type="button" class="button secondary" data-view="sources">출처·수집 상태 보기</button></div>
          <p>전달 자료가 필요하면 조회 조건을 확인한 뒤 <b>수집현황 CSV</b>를 내려받습니다. 서비스 구조·원천 정비 설명은 같은 화면의 <b>HOME 데이터 정비 방안</b>에서 확인합니다.</p>
        </article>
        <article id="guide-manage" class="guide-block" data-guide-topic data-guide-keywords="관리자 로그인 담당자 입력 목표 수정 편집 연필 승인 확정 병목 조치 일정 기준선 기관 신청 API 저장 충돌">
          <span class="guide-section-number">06 · 업무 담당자</span><h3 tabindex="-1">연결 확인·목표 입력·지연 조치하기</h3><p>조회만 한다면 입력하지 않아도 됩니다. 목표와 연결을 저장할 담당자는 관리자 로그인 후 아래 절차를 따릅니다.</p>
          <details class="guide-manager-details"><summary>담당자 입력 절차 펼치기 · 관리자 권한 필요</summary><div>
            <ol class="guide-steps"><li><div><strong>관리자 로그인 후 연결 관리로 이동합니다.</strong><p>상단 <b>관리자 로그인</b>을 사용하고, <b>데이터현황 → 정책-프로그램-사업연결</b>을 엽니다.</p><div class="guide-actions"><a class="button secondary" href="/admin">관리자 로그인 ↗</a><button type="button" class="guide-inline-action" data-view="tree">연결 관리 열기 →</button></div></div></li><li><div><strong>정책·프로그램·사업의 연결을 확인합니다.</strong><p>각 연결의 근거를 읽고 확인·수정·확정·해제를 선택합니다. 명칭이 비슷해도 블록·전체/부분 물량을 먼저 확인하세요.</p></div></li><li><div><strong>목표와 단계 근거를 입력합니다.</strong><p><b>③ 사업 단계·목표 근거</b>에서 단계 원천을 검토합니다. 목표 옆 연필 버튼 또는 목표 입력 화면에서 <b>단계·물량·기한·적용 범위·근거</b>를 저장합니다. 미등록 목표는 0으로 입력하지 않습니다.</p></div></li><li><div><strong>최초 일정과 기관 목표를 등록합니다.</strong><p><b>일정·병목·시나리오</b>에서 최초 약속·현재 예정·실제 사건과 변경사유를 구분합니다. 기관 역할·배정 목표도 근거와 기한을 함께 등록합니다.</p></div></li><li><div><strong>지연 조치의 책임과 기한을 남깁니다.</strong><p>병목 원인, 영향 물량, 책임·협력기관, 다음 조치, 처리기한·상태를 입력합니다. 저장 후 이력과 조회 결과를 확인합니다.</p></div></li></ol>
            <p class="guide-note">다른 담당자가 먼저 수정했다는 메시지가 나오면 다시 조회한 뒤 조정하세요. 원천 후보 자동 갱신은 담당자의 확정·해제를 보존합니다.</p>
            <h4>정책정보와 프로그램 구성을 바꾸려면</h4><p>관리자 로그인 후 <b>정책별 추진현황 → 정책 개요 오른쪽 정책정보</b>를 엽니다. 화면의 입력칸에서 정책명·개요·기간·지역별/연도별 목표를 바로 수정합니다. 지역명을 누르면 연도별 목표가 전환됩니다. 진행현황 위 프로그램을 체크하고 저장하면 실제 정책–프로그램 연결이 바뀝니다. 다른 정책 소속은 이동 여부를 확인합니다. 변경자·사유를 입력해 저장하고, 서류철에서 사용자 변경값과 기존 근거를 확인하세요. 입력칸의 <b>↺ 원천값 사용</b>은 해당 입력 우선값만 해제합니다. 비로그인 화면에서는 정책정보 관리 버튼이 표시되지 않습니다.</p><h4>자료를 더 요청해야 한다면</h4><p>출처와 수집현황의 <b>API 연결 안내</b>에서 신청 경로·요청 항목을 확인하고 초안을 내려받습니다. 접수번호·담당자·기한·상태를 기록할 수 있습니다. 기관 사이트에 자동 제출되지는 않습니다.</p><button type="button" class="guide-inline-action" data-view="keys">API 연결 안내 열기 →</button>
          </div></details>
        </article>
        <article id="guide-help" class="guide-block" data-guide-topic data-guide-keywords="도움말 FAQ 질문">
          <span class="guide-section-number">07 · 자주 묻는 질문</span><h3 tabindex="-1">화면을 보다가 막혔나요?</h3>
          <details data-guide-faq><summary>로그인이 꼭 필요한가요?</summary><p>지도·사업·원천·수집현황 조회는 로그인 없이 가능합니다. 목표 수정, 연결 확정, 수집 실행과 조치 저장은 관리자 권한이 필요합니다.</p></details>
          <details data-guide-faq><summary>지도에서 퍼센트 대신 물음표·‘물량 미확인’이 보여요.</summary><p>계획 물량이나 단계 근거가 없어 비율을 계산할 수 없는 상태입니다. 0%로 해석하지 마세요. 선택한 사업의 계획량과 단계 근거를 사업별 수집·연계에서 확인합니다.</p></details>
          <details data-guide-faq><summary>입주 정보가 있는데 인허가·건설은 왜 미확보인가요?</summary><p>입주 예정 자료와 이전 단계 원천이 서로 연결되지 않았을 수 있습니다. 사업별 수집·연계의 해당 칸과 원문을 확인하세요. 후행 정보가 있다는 이유만으로 실제 승인일·착공일을 만들어 넣지는 않습니다.</p></details>
          <details data-guide-faq><summary>준공 예정일이 있는데 공급 계획에는 안 보여요.</summary><p>준공은 건설 일정이고, 공급은 분양·모집 일정입니다. 준공 예정일은 건설 칸에서 확인합니다. 공급 원천이 없으면 준공 예정으로 대신 채우지 않습니다.</p></details>
          <details data-guide-faq><summary>‘미정’이면 자료 수집에 실패한 건가요?</summary><p>원문이 날짜 미정을 명시했다면 그 상태를 확보한 것입니다. 수집 실패·원문 공란·항목 미제공·연결 필요와는 다릅니다. 상세의 일정 원문과 상태를 함께 확인하세요.</p></details>
          <details data-guide-faq><summary>프로그램이나 사업 검색 결과가 없어요.</summary><p>프로그램 목록은 현재 저장된 9·7 연결 범위입니다. 사업 검색에서는 지역·정책·검색어·조회일을 확인하고 필터 초기화 후 다시 찾으세요. 원천을 확보했어도 정책 연결 검토가 끝나지 않았을 수 있습니다.</p></details>
          <details data-guide-faq><summary>메뉴마다 숫자가 달라요.</summary><p>정책 전체 목표, 연결 사업 소계, 지역 전체 통계는 범위가 다릅니다. 단계·자료 연도·기준일과 검토 포함 여부를 맞춰 비교하세요. 단계별 누적량, 단지 총량과 금회 모집량을 더하면 중복됩니다.</p></details>
          <details data-guide-faq><summary>입주 예정·입주 시작 확인은 실제 입주 세대수인가요?</summary><p>아닙니다. 예정은 계획이고 입주 시작은 사건 확인입니다. 실제 거주 세대수와 미입주량은 같은 범위의 별도 집계가 필요합니다.</p></details>
          <details data-guide-faq><summary>대표 위치와 3D 아파트는 실제 단지인가요?</summary><p>대표·근사 위치와 가상 모델은 조회를 위한 참고 표시일 수 있습니다. 위치 근거와 공식 경계·건물 자료 확보 여부를 확인하세요. 근사 위치가 정확한 필지 PNU를 증명하지는 않습니다.</p></details>
          <details data-guide-faq><summary>목표를 수정하거나 지연 원인을 등록하려면 어디로 가나요?</summary><p>관리자 로그인 후 목표 옆 연필 버튼 또는 정책-프로그램-사업연결의 단계 목표 화면을 사용합니다. 지연 원인·책임기관·조치기한은 일정·병목·시나리오에서 등록합니다. 공식 근거와 변경사유를 함께 남기세요.</p></details>
          <div class="guide-more"><strong>요구사항과 기능 구현도 확인하고 싶다면</strong><p>총리님 요구사항에서 항목별 기능·이용 경로·자료 확보 상태를 확인하세요.</p><button type="button" class="guide-inline-action" data-view="requirements">총리님 요구사항 열기 →</button><a href="/poc/home/assets/reports/HOME_DATA_REMEDIATION_20261013.html" target="_blank" rel="noopener">HOME 데이터 정비 방안 ↗</a></div>
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
    document.getElementById('guide-search-status').textContent=tokens.length?`검색 결과 ${count}개 안내`:'7개 안내 · 화면에서 바로 따라 하기';
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
