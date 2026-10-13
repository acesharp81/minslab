/* Vercel 빌드: 배포에 필요한 파일만 public/ 으로 모으고, 환경변수로 config.js 를 만듭니다.
   - assets/ · regions/ 만 복사합니다(원천 data·tools·tests·docs 와 *.md 는 올라가지 않습니다). 지도 마크업의 정본 index.html 은 복사하지 않습니다:
     Next.js 가 /map 을 그릴 때 프로젝트 루트에서 읽습니다(app/(map)/map/page.tsx).
   - 운영 빌드(VERCEL_ENV=production)는 regions/index.json 에서 visibility 가 preview 인 지역을 빼고 그 폴더도 복사하지 않습니다.
   - VWORLD_KEY   : V-World 인증키 (Vercel 프로젝트 환경변수)
   - VWORLD_LAYER : (선택) 배경 종류(기본 midnight)
   환경변수가 없으면 로컬 config.js 를, 그것도 없으면 빈 키(OpenFreeMap 어두운 지도)를 씁니다.
   로컬 config.js 는 읽기만 하고 고치지 않습니다. 로그에는 키 값을 찍지 않습니다. */
const fs = require('fs');
const path = require('path');

/* 지역 색인에서 이번 빌드에 넣을 지역만 남긴다. 기본 지역이 빠지면 남은 첫 지역이 기본이 된다. 원본은 바꾸지 않는다. */
function pickRegions(index, production) {
  const regions = index.regions.filter((r) => !(production && r.visibility === 'preview')).map((r) => ({ ...r }));
  if (regions.length && !regions.some((r) => r.default)) regions[0].default = true;
  return { ...index, regions };
}

function configText(root, env) {
  if (env.VWORLD_KEY) {
    let c = 'window.VWORLD_KEY = ' + JSON.stringify(env.VWORLD_KEY) + ';\n';
    if (env.VWORLD_LAYER) c += 'window.VWORLD_LAYER = ' + JSON.stringify(env.VWORLD_LAYER) + ';\n';
    return c;
  }
  const local = path.join(root, 'config.js');
  return fs.existsSync(local) ? fs.readFileSync(local, 'utf8') : "window.VWORLD_KEY = '';\n";
}

function build({ root = '.', out = 'public', env = process.env, log = console.log } = {}) {
  const OUT = path.join(root, out), production = env.VERCEL_ENV === 'production';
  const index = pickRegions(JSON.parse(fs.readFileSync(path.join(root, 'regions/index.json'), 'utf8')), production);
  const homeMap = path.join(root, 'data/home10/map.json');
  if (fs.existsSync(homeMap)) { index.regions = []; index.homeDefault = 'home-907'; index.policyOnly = 'POL_2025_0907'; }
  for (const r of index.regions) {
    if (!fs.existsSync(path.join(root, 'regions', r.slug))) throw new Error(`regions/index.json 의 지역 폴더가 없습니다: regions/${r.slug}`);
  }
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  const keep = (f) => !f.endsWith('.md') && !f.endsWith('.DS_Store');
  for (const p of ['assets']) fs.cpSync(path.join(root, p), path.join(OUT, p), { recursive: true, filter: keep });
  for (const r of index.regions) fs.cpSync(path.join(root, 'regions', r.slug), path.join(OUT, 'regions', r.slug), { recursive: true, filter: keep });
  fs.mkdirSync(path.join(OUT, 'regions'), { recursive: true });
  fs.writeFileSync(path.join(OUT, 'regions/index.json'), JSON.stringify(index, null, 2) + '\n');
  // HOME 지도 자료는 읽기 전용 변환 스냅샷이다. 원본 지역 번들과 별도로 배포한다.
  if (fs.existsSync(homeMap)) {
    fs.mkdirSync(path.join(OUT, 'home10'), { recursive: true });
    fs.copyFileSync(homeMap, path.join(OUT, 'home10/map.json'));
    const scenePath = path.join(root, 'data/home10/scene.json');
    if (fs.existsSync(scenePath)) {
      const scene = JSON.parse(fs.readFileSync(scenePath, 'utf8'));
      const map = JSON.parse(fs.readFileSync(homeMap, 'utf8'));
      if (scene.candidateSnapshotAt !== map.readFinishedAt) throw new Error('3D 형상과 후보 자료의 변환 시각이 다릅니다. python3 scripts/build-home10-3d.py 를 실행하세요.');
      fs.copyFileSync(scenePath, path.join(OUT, 'home10/scene.json'));
    }
  }
  const config = configText(root, env);
  fs.writeFileSync(path.join(OUT, 'config.js'), config);
  log(`build ok -> ${out}/ (지역 ${index.regions.map((r) => r.slug).join(', ')}${production ? ' · 운영: 미리보기 지역 제외' : ''}; V-World 키: ${/VWORLD_KEY\s*=\s*['"][^'"]+['"]/.test(config) ? '있음' : '없음'})`);
  return index;
}

module.exports = { pickRegions, build };
if (require.main === module) build();
