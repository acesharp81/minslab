"""Explicit public release allowlist, secret scan, content hashes, reproducible ZIP metadata."""
import hashlib,json,os,sys,zipfile
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public'
SECRETS=[v for k,v in dotenv_values(ROOT/'.env').items() if v and any(s in k for s in ['KEY','TOKEN','PASSWORD'])]

def safe(path):
 data=path.read_bytes()
 for secret in SECRETS:
  assert secret.encode() not in data, f'Secret detected in {path.name}'
 return data

def zip_write(z,name,data):
 info=zipfile.ZipInfo(name,(2026,11,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data)

files=[]
for folder in ['app','scripts','tests']:
 files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and not any(x in p.parts for x in ['__pycache__','.pytest_cache']) and p.suffix not in ['.pyc']]
for name in ['README.md','requirements-authoring.txt','requirements.lock','Dockerfile','compose.yaml','.env.example','.gitignore','.dockerignore','project.json']:
 p=ROOT/name
 if p.exists():files.append(p)
files += [p for p in (ROOT/'docs/third_party_licenses').rglob('*') if p.is_file()]
for name in ['v167-pdf-citation-recovery.md','v166-comprehensive-stress.md','v165-comprehensive-demo.md','v164-delivery-guide.md','v163-compact-grouping.md','v162-welcome-design.md','v160-review.md','v150-review.md','ARCHITECTURE.md','RUNBOOK.md','SECURITY_LIMITS.md','THIRD_PARTY_NOTICES.md','상세실무편_개선_설계.md','최종_인수인계_상세실무편_검토결과.md','본문기준_최신판본_샘플_검증결과.md']:
 p=ROOT/'docs'/name
 if p.exists():files.append(p)
files += [p for p in (ROOT/'docs/submission').rglob('*') if p.is_file()]
# Audience views and the README video must travel with the master README.
for name in ['docs/readme-views/USER.md','docs/readme-views/MAINTAINER.md','docs/readme-views/DEVELOPER.md','docs/media/README.md','docs/media/workbaton-demo-3m45s-chat-support.mp4']:
 p=ROOT/name
 if p.is_file():files.append(p)
public=[p for p in OUT.iterdir() if p.is_file() and p.name in {x['file'] for x in json.loads((OUT/'manifest.json').read_text())['files']} and not p.name.startswith(('handover-source-', 'handover-demo-kit-'))]
records={str(p.relative_to(ROOT)):hashlib.sha256(safe(p)).hexdigest() for p in sorted(set(files))}
core={k:v for k,v in records.items() if k.startswith('app/') or k=='requirements.lock'}
fingerprint=hashlib.sha256(json.dumps(core,sort_keys=True).encode()).hexdigest()
release={'version':'1.6.7','application_source_sha256':fingerprint,'files':records,'contains':'source, synthetic samples, guide and quality evidence; no runtime DB or keys','video':'not included, deferred by user'}
(ROOT/'release/RELEASE.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
# Embedded manifest lists only the material actually included in the source package.
manifest=json.loads((OUT/'manifest.json').read_text());names={p.name for p in public};manifest['files']=[f for f in manifest['files'] if f['file'] in names]
with zipfile.ZipFile(OUT/'handover-source-v1.6.7.zip','w') as z:
 for p in sorted(set(files)):zip_write(z,'handover/'+str(p.relative_to(ROOT)),safe(p))
 for p in sorted(public):zip_write(z,'handover/release/public/'+p.name,safe(p))
 zip_write(z,'handover/release/public/manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode())
 zip_write(z,'handover/RELEASE.json',json.dumps(release,ensure_ascii=False,indent=2).encode())
with zipfile.ZipFile(OUT/'handover-demo-kit-v1.6.7.zip','w') as z:
 for p in sorted(public):zip_write(z,p.name,safe(p))
 zip_write(z,'README.txt','업무바통 직접 시연 자료\n1. handover-guide.pdf를 읽습니다.\n2. practice-samples.zip을 앱에 등록합니다.\n3. practice-report.*은 실제 모델 분석·전임자 수정·확정 결과 예시입니다.\n4. practice-expected.json과 practice-review.md에서 검증 기준과 한계를 확인합니다.\n5. version-samples.zip은 파일명·버전 혼선 13개 문서 체험입니다. version-guide.md, version-report.html, version-review.md를 함께 확인하세요.\n영상 제작 및 참가 접수는 이번 묶음에 포함하지 않습니다.\n'.encode())
print(json.dumps({'source_files':len(records),'application_source_sha256':fingerprint,'source_zip_bytes':(OUT/'handover-source-v1.6.7.zip').stat().st_size,'demo_kit_bytes':(OUT/'handover-demo-kit-v1.6.7.zip').stat().st_size}))
