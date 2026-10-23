"""Create a DB-only handoff in the established format; verify in an isolated container.

Run on the Docker host. No production writes, environment files or raw attachments
are exported. The established backup_database.INSPECT owns the read-only snapshot.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.backup_database import INSPECT, digest

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ['sudo', 'docker'] if os.geteuid() else ['docker']
KST = ZoneInfo('Asia/Seoul')
DB = 'poc10-home-db'
API = 'poc10-home-api'
PREVIOUS = ROOT/'backups/HOME_DB_20261022_062310_TEST'


def run(*args, **kwargs):
    return subprocess.run(DOCKER+list(args), check=True, **kwargs)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def inspect_sql(metadata):
    def q(s):
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]*', s):
            raise ValueError('Unexpected SQL identifier')
        return '"'+s+'"'
    counts=[]
    for name in metadata['row_counts']:
        schema, table=name.split('.')
        if name=='public.home_revision':
            counts.append("SELECT 'public.home_revision' AS name, coalesce(sum(n),0) AS n FROM revision_counts")
        else:
            counts.append("SELECT '"+name+"' AS name, count(*) AS n FROM "+q(schema)+'.'+q(table))
    return "WITH revision_counts AS MATERIALIZED (SELECT kind,count(*) n,count(*) FILTER (WHERE superseded_at IS NULL) current_n FROM home_revision GROUP BY kind) SELECT json_build_object('row_counts',(SELECT json_object_agg(name,n) FROM ("+' UNION ALL '.join(counts)+") x),'extensions',(SELECT json_object_agg(extname,extversion) FROM pg_extension),'current_revision_counts',(SELECT json_object_agg(kind,current_n) FROM revision_counts WHERE current_n>0),'alembic_version',(SELECT version_num FROM alembic_version),'invalid_public_indexes',(SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT i.indisvalid));"


def normalized_schema(sql):
    lines=[line for line in sql.splitlines() if line.strip() and not line.startswith(('--','\\restrict','\\unrestrict'))]
    statements=[part.strip() for part in re.split(r';\s*\n', '\n'.join(lines)) if part.strip()]
    canonical=[]
    for stmt in statements:
        # PostgreSQL 16 deparses these saved varchar-array -> text[] casts
        # as element-wise casts after a restore. Canonicalize only the two
        # known index definitions, keeping every literal and other SQL intact.
        if stmt.startswith(('CREATE INDEX ix_home_delivery_revision ', 'CREATE UNIQUE INDEX uq_home_active_collection_job ')):
            def array_key(match):
                body=match.group(1)
                literal=r"'(?:[^']|'')*'::character varying"
                element='(?:'+literal+r'|\('+literal+r'\)::text)'
                if not re.fullmatch(r'\s*'+element+r'(?:,\s*'+element+r')*\s*',body):return match.group(0)
                values=re.findall(r"'((?:[^']|'')*)'::character varying",body)
                if not values:return match.group(0)
                return 'TEXT_ARRAY['+','.join(repr(v) for v in values)+']'
            stmt=re.sub(r"\(\(ARRAY\[(.*?)\]\)::text\[\]\)",array_key,stmt)
            stmt=re.sub(r"\(ARRAY\[(.*?)\]\)",array_key,stmt)
        canonical.append(stmt)
    return Counter(canonical)


def main():
    os.umask(0o077)
    stamp=datetime.now(KST).strftime('%Y%m%d_%H%M%S')
    folder=ROOT/'backups'/('HOME_DB_'+stamp)
    folder.mkdir(parents=True, exist_ok=False)
    name='home-share-verify-'+stamp.replace('_','-')
    save(folder/'build-status.json', {'phase':'SNAPSHOT_STARTING','temporary_container':name,'verified':False})
    print('PACKAGE_DIRECTORY '+str(folder), flush=True)
    snapshot=None
    started=False
    image=run('inspect','--format','{{.Image}}',DB,capture_output=True,text=True).stdout.strip()
    try:
        snapshot=subprocess.Popen(DOCKER+['exec','-i',API,'python','-c',INSPECT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        first=snapshot.stdout.readline()
        if not first:raise RuntimeError('Snapshot inspection did not return metadata')
        metadata=json.loads(first)
        token=metadata.pop('snapshot')
        if not re.fullmatch('[A-Fa-f0-9-]+',token):raise ValueError('Invalid snapshot token')
        metadata['snapshot_at_kst']=datetime.fromisoformat(metadata['snapshot_at']).astimezone(KST).isoformat()
        metadata['previous_package']=PREVIOUS.name
        metadata['previous_package_status']='IN_PROGRESS_TEST_ONLY; restore_verified=false'
        save(folder/'manifest.pending.json',metadata)
        print('SNAPSHOT_READY '+metadata['snapshot_at_kst'],flush=True)
        with (folder/'home.dump').open('wb') as out:
            run('exec',DB,'pg_dump','-U','home','-d','home','--format=custom','--no-owner','--no-privileges','--snapshot='+token,stdout=out)
        snapshot.stdin.write('\n');snapshot.stdin.flush();snapshot.wait(timeout=30)
        if snapshot.returncode:raise RuntimeError('Snapshot inspection failed')
        print('DUMP_COMPLETE '+str((folder/'home.dump').stat().st_size),flush=True)
        for target, flags in [('archive-contents.txt',['--list']),('schema.sql',['--schema-only','--no-owner','--no-privileges','--file=-'])]:
            with (folder/'home.dump').open('rb') as src,(folder/target).open('wb') as out:
                run('exec','-i',DB,'pg_restore',*flags,stdin=src,stdout=out)
        previous=json.loads((PREVIOUS/'manifest.json').read_text())
        with (PREVIOUS/'home.dump').open('rb') as src:
            prior_schema=run('exec','-i',DB,'pg_restore','--schema-only','--no-owner','--no-privileges','--file=-',stdin=src,capture_output=True).stdout.decode()
        current=(folder/'schema.sql').read_text()
        norm_current=normalized_schema(current);norm_previous=normalized_schema(prior_schema)
        schema=dict(previous_package=PREVIOUS.name,physical_schema_identical=norm_current==norm_previous,
            normalization='Ignore comments, blank lines, and random restrict/unrestrict tokens; compare SQL statement multisets',
            previous_normalized_schema_sha256=hashlib.sha256('\n'.join(sorted(norm_previous.elements())).encode()).hexdigest(),
            current_normalized_schema_sha256=hashlib.sha256('\n'.join(sorted(norm_current.elements())).encode()).hexdigest(),
            removed_statements=list((norm_previous-norm_current).elements()),added_statements=list((norm_current-norm_previous).elements()))
        save(folder/'schema-comparison.json',schema)
        tables={key:dict(previous=previous['row_counts'].get(key,0),current=value,delta=value-previous['row_counts'].get(key,0)) for key,value in metadata['row_counts'].items()}
        kinds={key:dict(previous=previous['current_revision_counts'].get(key,0),current=value,delta=value-previous['current_revision_counts'].get(key,0)) for key,value in metadata['current_revision_counts'].items()}
        save(folder/'data-comparison.json',dict(previous_package=PREVIOUS.name,previous_snapshot_at_kst=previous['snapshot_at_kst'],snapshot_at_kst=metadata['snapshot_at_kst'],tables=tables,current_revision_kinds=kinds))
        print('ISOLATED_RESTORE_STARTING '+name,flush=True)
        save(folder/'build-status.json',dict(phase='RESTORING',temporary_container=name,verified=False))
        run('run','-d','--name',name,'--network','none','--memory','4g','--memory-swap','6g','--cpus','2',
            '-e','POSTGRES_USER=home','-e','POSTGRES_DB=postgres','-e','POSTGRES_HOST_AUTH_METHOD=trust',
            '-v','/var/lib/postgresql/data','--mount','type=bind,source='+str(folder)+',target=/backup,readonly',
            image,'postgres','-c','shared_buffers=256MB','-c','maintenance_work_mem=128MB',
            '-c','max_parallel_maintenance_workers=0','-c','max_wal_size=4GB','-c','synchronous_commit=off',
            '-c','fsync=off','-c','full_page_writes=off',stdout=subprocess.DEVNULL)
        started=True
        for _ in range(90):
            result=subprocess.run(DOCKER+['exec',name,'pg_isready','-U','home','-d','postgres'],capture_output=True)
            if result.returncode==0:
                logs=run('logs',name,capture_output=True,text=True)
                if 'init process complete; ready for start up' in logs.stdout+logs.stderr:break
            time.sleep(1)
        else:raise RuntimeError('Isolated database did not become ready')
        run('exec',name,'createdb','-U','home','-T','template0','home_verify')
        begin=time.monotonic()
        with (folder/'restore-check.log').open('wb') as log:
            restore=subprocess.Popen(DOCKER+['exec',name,'pg_restore','-U','home','-d','home_verify','--no-owner','--no-privileges','--exit-on-error','--jobs=8','/backup/home.dump'],stdout=log,stderr=log)
            heartbeat=0
            while restore.poll() is None:
                time.sleep(10)
                heartbeat+=1
                if heartbeat%6==0:print('RESTORE_IN_PROGRESS '+str(round(time.monotonic()-begin))+'s',flush=True)
            if restore.returncode:raise RuntimeError('Restore failed; inspect restore-check.log')
        print('RESTORE_LOADED '+str(round(time.monotonic()-begin))+'s',flush=True)
        verified_sql=(folder/'restore-verify.sql').read_text() if (folder/'restore-verify.sql').exists() else inspect_sql(metadata)
        verified=json.loads(run('exec',name,'psql','-X','-U','home','-d','home_verify','-Atc',verified_sql,capture_output=True,text=True).stdout)
        for key in ['row_counts','extensions','current_revision_counts']:
            if verified[key]!=metadata[key]:raise RuntimeError('Restore comparison failed: '+key)
        if verified['invalid_public_indexes']:raise RuntimeError('Invalid restored indexes')
        restored_schema=run('exec',name,'pg_dump','-U','home','-d','home_verify','--schema-only','--no-owner','--no-privileges',capture_output=True,text=True).stdout
        (folder/'restored-schema.sql').write_text(restored_schema)
        if normalized_schema(restored_schema)!=norm_current:
            save(folder/'restore-schema-mismatch.json',dict(source_only=list((norm_current-normalized_schema(restored_schema)).elements()),restored_only=list((normalized_schema(restored_schema)-norm_current).elements())))
            raise RuntimeError('Restored schema mismatch')
        save(folder/'restore-verification.json',dict(verified_at=datetime.now(KST).isoformat(),row_counts_equal=True,extensions_equal=True,current_revision_counts_equal=True,physical_schema_equal=True,invalid_public_indexes=0,alembic_version=verified['alembic_version'],restore_seconds=round(time.monotonic()-begin,2),verification_container=name,network='none',production_database_modified=False,production_limits_modified=False,resource_limits=dict(memory='4GiB',memory_and_swap='6GiB',cpus=2,restore_jobs=8,maintenance_work_mem='128MB'),ephemeral_only_settings=['fsync=off','full_page_writes=off','synchronous_commit=off']))
        metadata.update(format='PostgreSQL custom archive',dump_file='home.dump',dump_bytes=(folder/'home.dump').stat().st_size,sha256=digest(folder/'home.dump'),restore_verified=True,restore_verified_at=datetime.now(KST).isoformat(),restore_row_counts=verified['row_counts'],restore_current_revision_counts=verified['current_revision_counts'],alembic_version=verified['alembic_version'],source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_worktree_dirty=bool(subprocess.check_output(['git','status','--porcelain','--','.'],cwd=ROOT,text=True).strip()),api_image_id=run('inspect','--format','{{.Image}}',API,capture_output=True,text=True).stdout.strip(),excluded=['Application source code; source fingerprints and change notes are included','Environment files, passwords, API credentials, database roles/grants','Raw PDFs, HTML files, and other attachments outside PostgreSQL'])
        save(folder/'manifest.json',metadata)
        (folder/'manifest.pending.json').unlink()
        save(folder/'build-status.json',dict(phase='RESTORE_VERIFIED_PENDING_PACKAGING',verified=True))
        print('RESTORE_VERIFIED '+str(len(metadata['row_counts']))+' tables',flush=True)
    finally:
        if snapshot and snapshot.poll() is None:
            snapshot.stdin.close();snapshot.wait(timeout=30)
        if started:
            run('rm','-f','-v',name,stdout=subprocess.DEVNULL)
            save(folder/'temporary-resource-cleanup.json',dict(container=name,container_and_anonymous_volume_removed=True,production_database_modified=False,production_resource_limits_modified=False,at=datetime.now(KST).isoformat()))
            print('TEMPORARY_CONTAINER_REMOVED '+name,flush=True)
    print('READY_FOR_PACKAGE '+str(folder),flush=True)

if __name__=='__main__':main()
