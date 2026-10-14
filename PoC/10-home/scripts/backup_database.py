"""Create a consistent, restore-verified HOME database handoff. Run from the host."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo('Asia/Seoul')
DOCKER = ['docker'] if os.geteuid() == 0 else ['sudo', 'docker']
DB = 'poc10-home-db'
API = 'poc10-home-api'

# Credentials remain inside the API container. No .env or connection URL is exported.
INSPECT = r'''
import json,sys
from sqlalchemy import text,create_engine
from backend.db import engine_for
engine=engine_for()
if len(sys.argv)>1:engine=create_engine(engine.url.set(database=sys.argv[1]))
with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
    conn.execute(text('SET TRANSACTION READ ONLY'))
    stamp=conn.execute(text('SELECT transaction_timestamp()')).scalar_one().isoformat()
    snapshot=conn.execute(text('SELECT pg_export_snapshot()')).scalar_one() if len(sys.argv)==1 else None
    tables=conn.execute(text("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') AND schemaname NOT LIKE 'pg_toast%' ORDER BY 1,2")).all()
    quote=engine.dialect.identifier_preparer.quote
    counts={schema+'.'+table:conn.execute(text('SELECT count(*) FROM '+quote(schema)+'.'+quote(table))).scalar_one() for schema,table in tables}
    extensions=dict(conn.execute(text('SELECT extname,extversion FROM pg_extension ORDER BY extname')).all())
    kinds=dict(conn.execute(text('SELECT kind,count(*) FROM home_revision WHERE superseded_at IS NULL GROUP BY kind ORDER BY kind')).all())
    result=dict(snapshot_at=stamp,snapshot=snapshot,postgresql=conn.execute(text('SHOW server_version')).scalar_one(),extensions=extensions,row_counts=counts,current_revision_counts=kinds)
    print(json.dumps(result),flush=True)
    if snapshot:sys.stdin.readline()
'''


def run(*args, **kw):
    return subprocess.run(DOCKER + list(args), check=True, **kw)


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    os.umask(0o077)
    stamp = datetime.now(KST).strftime('%Y%m%d_%H%M%S')
    directory = ROOT / 'backups' / ('HOME_DB_' + stamp)
    directory.mkdir(parents=True, exist_ok=False)
    print('EXPORT_DIRECTORY ' + str(directory), flush=True)
    verify_db = 'home_verify_' + stamp
    snapshot_process = None
    created = False
    try:
        snapshot_process = subprocess.Popen(DOCKER + ['exec', '-i', API, 'python', '-c', INSPECT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        metadata = json.loads(snapshot_process.stdout.readline())
        snapshot = metadata.pop('snapshot')
        if not re.fullmatch(r'[A-Fa-f0-9-]+', snapshot):
            raise ValueError('Invalid snapshot identifier')
        metadata['snapshot_at_kst'] = datetime.fromisoformat(metadata['snapshot_at']).astimezone(KST).isoformat()
        (directory / 'manifest.pending.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
        print('SNAPSHOT_READY ' + metadata['snapshot_at_kst'], flush=True)
        with (directory / 'home.dump').open('wb') as out:
            run('exec', DB, 'pg_dump', '-U', 'home', '-d', 'home', '--format=custom', '--no-owner', '--no-privileges', '--snapshot='+snapshot, stdout=out)
        snapshot_process.stdin.write('\n');snapshot_process.stdin.flush();snapshot_process.wait(timeout=30)
        if snapshot_process.returncode:raise RuntimeError('Snapshot transaction failed')
        print('DUMP_COMPLETE '+str((directory/'home.dump').stat().st_size), flush=True)
        with (directory/'home.dump').open('rb') as src, (directory/'archive-contents.txt').open('wb') as out:
            run('exec', '-i', DB, 'pg_restore', '--list', stdin=src, stdout=out)
        run('exec', DB, 'createdb', '-U', 'home', '-T', 'template0', verify_db)
        created = True
        print('RESTORE_VERIFY_STARTED '+verify_db, flush=True)
        with (directory/'home.dump').open('rb') as src, (directory/'restore-check.log').open('wb') as log:
            run('exec', '-i', DB, 'pg_restore', '-U', 'home', '-d', verify_db, '--no-owner', '--no-privileges', '--exit-on-error', stdin=src, stdout=log, stderr=log)
        verified = json.loads(run('exec', API, 'python', '-c', INSPECT, verify_db, capture_output=True, text=True).stdout)
        for key in ('row_counts', 'extensions', 'current_revision_counts'):
            if metadata[key] != verified[key]:raise RuntimeError('Restore verification mismatch: '+key)
        print('RESTORE_VERIFIED '+str(len(metadata['row_counts']))+' tables', flush=True)
        metadata.update(database='home',format='PostgreSQL custom archive',dump_file='home.dump',dump_bytes=(directory/'home.dump').stat().st_size,sha256=digest(directory/'home.dump'),restore_verified=True,restore_verified_at=datetime.now(KST).isoformat(),restore_row_counts=verified['row_counts'],restore_current_revision_counts=verified['current_revision_counts'])
        metadata['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        metadata['source_worktree_dirty']=bool(subprocess.check_output(['git','status','--porcelain','--','.'],cwd=ROOT,text=True).strip())
        metadata['api_image_id']=run('inspect','--format','{{.Image}}',API,capture_output=True,text=True).stdout.strip()
        metadata['excluded']=['Database login roles/passwords and grants','Server .env and environment API credentials','Raw files and attachments outside PostgreSQL','Application source code (README included separately)']
        (directory/'manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
        (directory/'manifest.pending.json').unlink()
        readme = f'''# HOME 데이터베이스 공유·복원 안내

- 스냅샷 기준: **{metadata['snapshot_at_kst']} (Asia/Seoul)**
- PostgreSQL: {metadata['postgresql']} / PostGIS: {metadata['extensions'].get('postgis')}
- 형식: `pg_dump` custom archive (`home.dump`)
- 검증: 별도 임시 DB 복원 성공. 사용자·확장 테이블 **{len(metadata['row_counts'])}개**의 행 수, 확장 버전, 현재 원천 종류별 건수를 원본과 대조했습니다.
- 소스 커밋: `{metadata['source_commit']}`. 미커밋 변경 포함 여부: `{metadata['source_worktree_dirty']}`. 앱 소스 자체는 이 패키지에 포함되지 않습니다.

## 포함 범위

운영 DB의 스키마·데이터·인덱스·제약조건·시퀀스·확장 정의를 포함합니다.
정책–프로그램–사업 연결, 담당자 확인/입력/추정 값과 변경 이력, 단계별 목표·측정값,
지역 통계와 소득·인구이동·거주기간·주거형태·PIR 수집 판본을 포함합니다.
진행 중인 수집 배치가 있다면 스냅샷 시점에 커밋된 상태까지 포함합니다.

DB 역할·로그인 비밀번호·권한 배정, `.env`·환경변수 인증키, DB 외부 PDF/HTML/첨부 파일은 제외합니다.
원문 경로·해시는 DB에 남지만 파일 실물은 `data/raw/` 등을 별도로 전달해야 합니다.
입력자 이름과 사유 등 업무 이력이 포함되므로 업무 공유 대상에게 전달합니다.
화면·그래프·팝업 변경을 재현하려면 해당 앱 소스를 함께 준비합니다. 기능 안내는 `APPLICATION_README.md`를 참고하세요.

## 무결성 확인

압축을 풀고 이 폴더에서 실행합니다.

```bash
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell에서는 `Get-FileHash .\\home.dump -Algorithm SHA256` 결과를 `manifest.json`과 비교합니다.

## 별도 빈 DB에 복원

1. 아래 내용으로 `restore.env`를 직접 만듭니다. 새 비밀번호를 설정합니다.

```dotenv
POSTGRES_USER=home
POSTGRES_PASSWORD=새로_정한_비밀번호
POSTGRES_DB=postgres
```

2. Docker가 설치된 환경에서 전용 PostgreSQL/PostGIS를 시작합니다.

```bash
docker run -d --name home-import-db --env-file ./restore.env -p 127.0.0.1:15432:5432 -v home-import-pgdata:/var/lib/postgresql/data postgis/postgis:16-3.5
docker exec home-import-db pg_isready -U home -d postgres
```

3. 준비 완료를 확인한 후 빈 DB를 만들고 복원합니다. 아래 명령은 bash 등 파일 리디렉션을 지원하는 셸에서 실행합니다.

```bash
docker exec home-import-db createdb -U home -T template0 home_import
docker exec -i home-import-db pg_restore -U home -d home_import --no-owner --no-privileges --exit-on-error < home.dump
docker exec home-import-db psql -U home -d home_import -c "SELECT count(*) FROM home_revision; SELECT extname,extversion FROM pg_extension ORDER BY extname;"
```

`manifest.json`의 테이블별 건수·확장 버전과 대조합니다. 기존 PostgreSQL을 사용한다면 PostgreSQL 16과 동일한 PostGIS 관련 확장이 설치된 별도 빈 DB를 사용합니다.

4. 앱 연결 예시:

```dotenv
POC10_DATABASE_URL=postgresql+psycopg://home:새_비밀번호@DB호스트:15432/home_import
```

특수문자가 있는 비밀번호는 URL 인코딩합니다. 앱이 같은 Docker 네트워크에 있다면 `home-import-db:5432`를 사용합니다.
외부 API 키와 앱 설정은 받는 환경에서 별도로 설정합니다. 복원 검증용 임시 DB는 검증 종료 후 삭제했습니다.
'''
        (directory/'README.md').write_text(readme)
        app_readme=ROOT/'README.md'
        content=app_readme.read_text()
        marker='2026-10-13 전달용 덤프는 동일 시점 스냅샷과 체크섬·복원 안내를 포함합니다.'
        start=content.index('최신 공유용 DB 덤프:') if '최신 공유용 DB 덤프:' in content else content.index(marker)
        end=content.index('\n\n| 자료·코드',start)
        latest=f'''최신 공유용 DB 덤프: **{metadata['snapshot_at_kst']} 기준**.

- ZIP: [backups/{directory.name}.zip](backups/{directory.name}.zip) · {{size_mb}} MiB
- SHA-256: [backups/{directory.name}.zip.sha256](backups/{directory.name}.zip.sha256)
- 복원 안내: [backups/{directory.name}/README.md](backups/{directory.name}/README.md)
- 검증 명세: [backups/{directory.name}/manifest.json](backups/{directory.name}/manifest.json)
- 동일 시점 스냅샷을 별도 임시 DB에 복원하고 사용자·확장 테이블 {len(metadata['row_counts'])}개의 행 수, 확장 버전, 현재 원천 종류별 건수를 대조했습니다. 이는 업무 테이블만 {len(metadata['row_counts'])}개라는 뜻이 아닙니다.
- 담당자 입력·승인·추정 상태와 변경 이력, 단계 목표·측정값 및 최신 입지 통계·PIR 판본을 포함합니다. DB 외부 원문 파일·앱 소스·환경변수 인증키는 포함하지 않습니다. 패키지에 이 README의 사본과 복원 안내·체크섬을 동봉합니다.
- 원본 DB를 변경하지 않았으며 검증용 임시 DB는 제거했습니다. 이전 공유본은 그대로 보존합니다. 덤프는 Git/정적 웹 공개 대상이 아닙니다.

같은 형식으로 다시 생성하고 복원 검증하려면 앱 디렉터리에서 `python3 scripts/backup_database.py`를 실행합니다. Docker 접근 권한이 필요하며 운영 API/DB 컨테이너가 실행 중이어야 합니다.'''
        # Archive is already compressed by pg_dump; store members without recompression.
        size_mb=round(metadata['dump_bytes']/1024/1024,1)
        app_readme.write_text(content[:start]+latest.replace('{size_mb}',str(size_mb))+content[end:])
        (directory/'APPLICATION_README.md').write_text(app_readme.read_text())
        sums=''.join(digest(p)+'  '+p.name+'\n' for p in sorted(directory.iterdir()) if p.is_file())
        (directory/'SHA256SUMS.txt').write_text(sums)
        archive=directory.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as out:
            for path in sorted(directory.iterdir()):out.write(path, directory.name+'/'+path.name)
        with zipfile.ZipFile(archive) as check:
            if check.testzip() is not None:raise RuntimeError('ZIP integrity verification failed')
        archive.with_suffix('.zip.sha256').write_text(digest(archive)+'  '+archive.name+'\n')
        print('PACKAGE_READY '+str(archive),flush=True)
    finally:
        if snapshot_process and snapshot_process.poll() is None:
            snapshot_process.stdin.close()
            snapshot_process.wait(timeout=30)
        if created:
            run('exec',DB,'dropdb','-U','home',verify_db)
            print('TEMPORARY_DATABASE_REMOVED '+verify_db,flush=True)

if __name__=='__main__':main()
