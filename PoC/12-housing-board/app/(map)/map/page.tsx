import fs from 'node:fs';
import path from 'node:path';
import MapIsland from '../../../components/MapIsland';

/* 지도 섬: 기존 지도 앱의 마크업(index.html 의 body)을 그대로 넣고, 스크립트는 MapIsland 가 기존 순서대로 불러온다.
   app.js·시험은 건드리지 않는다. 마크업의 정본은 지금 루트 index.html 이다.
   index.html 은 그릴 때 읽는다: 개발 서버는 요청마다 다시 읽어 고친 마크업이 바로 보이고, 운영 빌드는 정적으로 한 번 그린다(모듈 맨 위에서 읽으면 개발 서버를 다시 켜야 반영됐다) */
function mapMarkup() {
  const html = fs.readFileSync(path.join(process.cwd(), 'index.html'), 'utf8');
  const markup = (html.match(/<body>([\s\S]*)<\/body>/)?.[1] ?? '').replace(/<noscript>[\s\S]*?<\/noscript>/, '');
  if (!markup.includes('id="map"')) throw new Error('index.html 에서 지도 마크업을 찾지 못했습니다');
  return markup;
}

export default function MapPage() {
  const markup = mapMarkup();
  return (
    <>
      <div style={{ display: 'contents' }} suppressHydrationWarning dangerouslySetInnerHTML={{ __html: markup }} />
      <MapIsland />
    </>
  );
}
