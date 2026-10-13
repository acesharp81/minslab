'use strict';

/* 프로젝트 루트 폴더(regions/·registry/·.cache/ 가 있는 곳).
   Next.js(Turbopack)는 번들 안의 __dirname 을 가짜 경로("/ROOT/lib")로 바꿔 컴파일해 그 기준 경로로는 파일을 못 찾는다.
   그래서 일반 Node(시험·scripts/dev.js)에서는 이 파일 위치로 계산한 실제 루트를 쓰고, 번들 안에서는 실행 때의 작업 폴더
   (process.cwd(): next start 는 프로젝트 루트, Vercel 함수는 추적한 파일이 놓인 /var/task)를 쓴다.
   다른 파일에서 데이터 경로를 __dirname 으로 만들지 않는다(tests/js/root.test.cjs 가 막는다). */
const fs = require('fs');
const path = require('path');

const here = path.join(__dirname, '..');
const ROOT = fs.existsSync(path.join(here, 'package.json')) ? here : process.cwd();

module.exports = { ROOT };
