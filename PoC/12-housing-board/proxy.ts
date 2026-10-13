import { NextResponse, type NextRequest } from 'next/server';

/* 옛 지도 주소 호환(기획서 M6): 지도가 `/`였을 때의 링크(`/?region=…` `/?code=…` `/?pnu=…` `/?at=…` 등)는 `/map?…`로 보낸다.
   `/`에는 쿼리를 쓰는 화면이 없으므로 쿼리가 있으면 전부 지도다. 쿼리 이름·우선순위는 스펙 2.1 그대로다. */
export function proxy(request: NextRequest) {
  const { search } = request.nextUrl;
  if (search) return NextResponse.redirect(new URL('/poc/housing-board/map' + search, request.url));
  return NextResponse.next();
}

export const config = { matcher: '/' };
