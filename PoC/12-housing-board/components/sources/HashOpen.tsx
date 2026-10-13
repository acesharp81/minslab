'use client';
/* 주소의 #id 가 닫힌 <details>(Fold) 안에 있으면 열고 그 자리로 간다 — 기관별 화면의 /sources#id 링크, 노선도 정거장(#step-…), 원천 카드의 흐름 위치 링크.
   Chromium 은 조각 이동 때 스스로 열지만 다른 브라우저를 위해 둔다. 처음 들어올 때와 같은 문서 안 이동(hashchange) 모두. */
import { useEffect } from 'react';

export default function HashOpen() {
  useEffect(() => {
    const open = () => {
      const id = decodeURIComponent(location.hash.slice(1));
      const el = id ? document.getElementById(id) : null;
      let box = el?.closest('details');
      if (!el || !box) return;
      let changed = false;
      while (box) { if (!box.open) { box.open = true; changed = true; } box = box.parentElement?.closest('details') ?? null; }
      if (changed) el.scrollIntoView();
    };
    open();
    window.addEventListener('hashchange', open);
    return () => window.removeEventListener('hashchange', open);
  }, []);
  return null;
}
