/* 사업 레지스트리 파일(registry/projects.json) 읽기. 서버 함수(/api/v1/resolve · /api/v1/permits)가 쓰는 색인을 만든다.
   - 파일은 발급 도구(scripts/issue-projects.js)만 고친다. 사람이 고쳐도 되지만 tests/js/registry.test.cjs 가 일관성을 검사한다.
   - 파일이 없거나 깨졌으면 빈 레지스트리로 동작한다(인허가·코드 해석을 막지 않는다). 깨진 경우는 서버 로그에 한 번 남긴다.
   - 읽은 결과는 파일 수정 시각이 바뀔 때까지 메모리에 둔다(개발 서버에서 발급 도구를 돌리면 바로 반영, 서버리스에서는 배포마다 새 파일).
   시험: tests/js/registry.test.cjs */
'use strict';
const fs = require('fs');
const path = require('path');
const { emptyRegistry, indexRegistry, validateRegistry } = require('./projects.js');

const { ROOT } = require('./root.js');
const DEFAULT_FILE = path.join(ROOT, 'registry', 'projects.json');
const memo = new Map();   // 파일 → { mtimeMs, value }

function readRegistry(file = DEFAULT_FILE) {
  let st;
  try { st = fs.statSync(/*turbopackIgnore: true*/ file); } catch (e) { return { registry: emptyRegistry(), index: indexRegistry(emptyRegistry()), file, missing: true }; }
  const hit = memo.get(file);
  if (hit && hit.mtimeMs === st.mtimeMs) return hit.value;
  let registry = null, errors = [];
  try { registry = JSON.parse(fs.readFileSync(/*turbopackIgnore: true*/ file, 'utf8')); errors = validateRegistry(registry); } catch (e) { errors = [`읽지 못함: ${e.message}`]; }
  if (errors.length) { console.error(`registry ${path.basename(file)}: ${errors.length}건 문제 — 빈 레지스트리로 동작(${errors.slice(0, 3).join(' | ')})`); registry = emptyRegistry(); }
  const value = { registry, index: indexRegistry(registry), file, ...(errors.length ? { invalid: errors } : {}) };
  memo.set(file, { mtimeMs: st.mtimeMs, value });
  return value;
}
const writeRegistry = (registry, file = DEFAULT_FILE) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, `${JSON.stringify(registry, null, 1)}\n`); memo.delete(file); };

module.exports = { DEFAULT_FILE, readRegistry, writeRegistry };
