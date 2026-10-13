/* 루트 레이아웃이 달라도 저장된 테마를 첫 화면을 그리기 전에 복원한다. */
export const THEME_INIT = "try{if(localStorage.getItem('theme')==='dark')document.documentElement.classList.add('dark')}catch(e){}";
