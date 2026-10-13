'use client';
/* 상단 메뉴 바(한 줄, PC 높이 64px). 왼쪽 로고, 가운데 메뉴 글자 링크(전부 한 줄에 보인다), 오른쪽 테마 토글. 900px 이하에서는 햄버거 하나로 접혀 아래로 펼쳐진다.
   지도 화면(compact)도 동일한 헤더와 테마 토글을 사용하며 문서 단위로 이동한다.
   안쪽 상자는 스크롤바를 뺀 폭이 아니라 화면 폭(100vw) 기준으로 폭·자리를 정한다: 문서 스크롤바가 있는 화면(종합상황판·사업…)과 없는 화면(단계별·우리 동네·지도)을
   오갈 때 메뉴 바가 움직이지 않게. 폭도 100vw 기준이라 1470px 보다 좁은 화면에서도 같고(2026-10-10: 메뉴 7px·테마 단추 14px 이동), 스크롤바 밑으로 들어가는 몫은 overflow-x-clip 으로 자른다
   (오른쪽 여백 28px 이 스크롤바 15px 보다 넓어 단추는 가려지지 않는다). 900px 이하는 여백이 12px 이라 예전처럼 남은 폭을 쓴다.
   지도로 가는 링크와 지도 안의 모든 링크는 <Link> 대신 <a> 로 둔다: 지도는 루트 레이아웃이 달라 들어갈 때·나올 때 전체 문서가 새로 열린다
   (app.js 는 문서당 한 번만 도는 스크립트라서). */
import { Menu, Moon, Sun, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { cn } from 'cn';
import { MENU, activeMenuId } from '../lib/shell/menu';
import { withBasePath } from '../lib/shell/base-path';

const linkBase = 'relative flex items-center whitespace-nowrap text-muted-foreground no-underline hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary';

export default function TopNav({ compact = false }: { compact?: boolean }) {
  const pathname = usePathname();
  const active = compact ? 'map' : activeMenuId(pathname);
  const [open, setOpen] = useState(false);          // 900px 이하의 펼침 메뉴
  const [dark, setDark] = useState(false);
  useEffect(() => { setDark(document.documentElement.classList.contains('dark')); }, []);
  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    try { localStorage.setItem('theme', next ? 'dark' : 'light'); } catch (_) { /* 저장소를 못 써도 이번 화면에서는 바뀐다 */ }
    window.dispatchEvent(new Event('housing:theme-change'));
  };

  const items = MENU.map((m) => {
    const on = active === m.id;
    const exact = pathname === m.href || pathname === withBasePath(m.href);
    const label = (<>{m.label}{m.soon ? <em className="ml-1.5 hidden rounded-full border border-border px-1.5 py-px text-[12px] not-italic min-[1280px]:inline">준비 중</em> : null}</>);
    const cls = cn(linkBase, 'h-16 px-2 text-[16px] font-normal min-[1101px]:px-3 min-[1101px]:text-[18px] mobile:h-11 mobile:px-4 mobile:text-[14px]', on && 'text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:bg-primary min-[1101px]:after:inset-x-3 mobile:after:inset-x-0 mobile:after:inset-y-2 mobile:after:right-auto mobile:after:h-auto mobile:after:w-0.5');
    return (
      <li key={m.id} className="flex">
        {compact || m.id === 'map'
          ? <a href={withBasePath(m.href)} className={cls} aria-current={on && (compact ? m.id === 'map' : exact) ? 'page' : undefined} title={m.label}>{label}</a>
          : <Link href={m.href} className={cls} aria-current={exact ? 'page' : undefined} title={m.label}>{label}</Link>}
      </li>
    );
  });

  return (
    <header className="sticky top-0 z-40 shrink-0 overflow-x-clip border-b border-border bg-card font-display font-normal text-card-foreground shadow-[0_1px_8px_rgba(15,23,42,.025)]">
      <div className="ml-[max(0px,50vw_-_720px)] flex h-16 w-[min(1440px,100vw)] items-center gap-2 px-7 mobile:ml-0 mobile:h-12 mobile:w-auto mobile:px-3">
        <a className="mr-3 flex h-full shrink-0 items-center gap-[9px] text-[#0F1A3D] no-underline dark:text-foreground focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary" href="/poc/housing-board/" aria-label="주택파동 종합상황판 처음으로">
          <svg className="block size-[33px] shrink-0" viewBox="4 4 64 60" aria-hidden="true">
            <path fill="currentColor" d="M8 28 27 12Q36 4 45 12L64 28 57 36 39 21Q36 18 33 21L15 36Z" />
            <path fill="#D65535" d="M8 43C18 33 27 32 38 40C48 48 54 45 64 35V48C54 58 45 60 34 51C25 44 18 43 8 54Z" />
          </svg>
          <span className="whitespace-nowrap text-[30px] font-normal leading-none tracking-[-0.035em]">주택파동</span>
        </a>
        <nav id="main-menu" aria-label="주 메뉴" className="mx-auto mobile:hidden"><ul className="m-0 flex list-none p-0">{items}</ul></nav>
        <div className="flex items-center gap-1 mobile:ml-auto">
          <button type="button" className="flex size-9 cursor-pointer items-center justify-center rounded-[8px] border-0 bg-transparent p-0 text-muted-foreground hover:bg-pn2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary" aria-pressed={dark} aria-label="다크 모드" title="다크 모드 전환" onClick={toggleTheme}>
              <Moon className="size-[18px] dark:hidden" aria-hidden="true" /><Sun className="hidden size-[18px] dark:block" aria-hidden="true" />
          </button>
          <button type="button" className="hidden size-9 cursor-pointer items-center justify-center rounded-[8px] border-0 bg-transparent p-0 text-foreground hover:bg-pn2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary mobile:flex" aria-expanded={open} aria-controls="main-menu-list" aria-label="메뉴" onClick={() => setOpen(!open)}>
            {open ? <X className="size-[20px]" aria-hidden="true" /> : <Menu className="size-[20px]" aria-hidden="true" />}
          </button>
        </div>
      </div>
      {open ? <nav id="main-menu-list" aria-label="주 메뉴" className="hidden border-t border-border bg-card shadow-[var(--shadow-pop)] mobile:block"><ul className="m-0 flex list-none flex-col p-0">{items}</ul></nav> : null}
    </header>
  );
}
