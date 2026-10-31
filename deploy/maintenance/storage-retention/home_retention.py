"""Dry-run by default. Only old, unreferenced LH-detail HTML; never business rows.

Rolling recovery archives expire after seven days. No network/source collection.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,re,subprocess,tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'PoC/10-home/data/raw/lh_notice_detail'
STATE=ROOT/'data/storage-maintenance/home'
CONTAINER='poc10-home-api'
WORKER=r'''
import os,sys,json,re,time,hashlib
from pathlib import Path
import psycopg
payload=json.load(sys.stdin);root=Path('/app/data/raw/lh_notice_detail')
key=int.from_bytes(hashlib.sha256(b'home-source:lh_notice_detail').digest()[:8],'big',signed=True)
url=os.environ['POC10_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')
with psycopg.connect(url,autocommit=True) as con:
 with con.cursor() as c:
  c.execute('SET statement_timeout=15000')
  if payload['mode']=='apply':
   c.execute('SELECT pg_try_advisory_lock(%s)',(key,))
   if not c.fetchone()[0]:print(json.dumps({'status':'collector_busy','deleted_files':0}));sys.exit(0)
  try:
   c.execute("SELECT payload::text FROM home_revision WHERE source_id='lh_notice_detail'")
   refs=set()
   for row in c:refs.update(re.findall('[a-f0-9]{64}',row[0]))
   cutoff=time.time()-86400
   if payload['mode']=='plan':
    files=[]
    for p in root.glob('*.html'):
     if p.is_symlink() or not re.fullmatch('[a-f0-9]{64}[.]html',p.name):continue
     st=p.stat()
     if p.stem in refs or st.st_mtime>=cutoff:continue
     files.append(dict(name=p.name,bytes=st.st_size,allocated_bytes=st.st_blocks*512,inode=st.st_ino,mtime_ns=st.st_mtime_ns))
    print(json.dumps({'files':files,'protected_hashes':len(refs)}))
   else:
    deleted=0;freed=0;skipped=0
    for f in payload['files']:
     assert re.fullmatch('[a-f0-9]{64}[.]html',f['name'])
     p=root/f['name']
     if p.stem in refs:skipped+=1;continue
     if not p.exists():continue
     st=p.stat()
     if p.is_symlink() or st.st_mtime>=cutoff or (st.st_ino,st.st_size,st.st_mtime_ns)!=(f['inode'],f['bytes'],f['mtime_ns']):skipped+=1;continue
     p.unlink();deleted+=1;freed+=st.st_blocks*512 if st.st_nlink==1 else 0
    print(json.dumps({'status':'complete','deleted_files':deleted,'freed_allocated_bytes':freed,'skipped_changed_or_protected':skipped}))
  finally:
   if payload['mode']=='apply':c.execute('SELECT pg_advisory_unlock(%s)',(key,))
'''

def worker(payload):
 r=subprocess.run(['docker','exec','-i',CONTAINER,'python','-c',WORKER],input=json.dumps(payload),text=True,capture_output=True,timeout=90)
 if r.returncode:raise RuntimeError('Read-only/retention worker failed: '+r.stderr[-600:])
 return json.loads(r.stdout)

def archive(files,folder,source=SOURCE):
 path=folder/'recovery.tar.zst'
 with path.open('wb') as dest:
  z=subprocess.Popen(['zstd','-q','-3','-T1','-c'],stdin=subprocess.PIPE,stdout=dest)
  try:
   with tarfile.open(fileobj=z.stdin,mode='w|') as tar:
    for f in files:
     assert re.fullmatch(r'[a-f0-9]{64}\.html',f['name'])
     p=source/f['name'];st=p.stat()
     assert not p.is_symlink() and p.resolve().parent==source.resolve()
     assert (st.st_ino,st.st_size,st.st_mtime_ns)==(f['inode'],f['bytes'],f['mtime_ns'])
     with p.open('rb') as src:assert hashlib.file_digest(src,'sha256').hexdigest()==p.stem
     tar.add(p,arcname=f['name'],recursive=False)
   z.stdin.close();assert z.wait()==0
  except BaseException:
   z.kill();z.wait()
   if z.stdin and not z.stdin.closed:
    try:z.stdin.close()
    except BrokenPipeError:pass
   raise
 expected={f['name'] for f in files};seen=set()
 z=subprocess.Popen(['zstd','-q','-d','-c',str(path)],stdout=subprocess.PIPE)
 try:
  with tarfile.open(fileobj=z.stdout,mode='r|') as tar:
   for member in tar:
    assert member.isfile() and member.name in expected and member.name not in seen
    assert hashlib.file_digest(tar.extractfile(member),'sha256').hexdigest()==Path(member.name).stem
    seen.add(member.name)
  z.stdout.close();assert z.wait()==0 and seen==expected
 except BaseException:
  z.kill();z.wait()
  if z.stdout and not z.stdout.closed:z.stdout.close()
  raise
 return path

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 plan=worker({'mode':'plan'});files=plan['files'];allocated=sum(f['allocated_bytes'] for f in files)
 result={'apply':args.apply,'candidate_files':len(files),'candidate_allocated_bytes':allocated,'protected_hashes':plan['protected_hashes']}
 if args.apply and allocated>8*1024**3:
  result['status']='manual_review_required_over_8GiB'
 elif args.apply and files:
  folder=STATE/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder.mkdir(parents=True,mode=0o700)
  (folder/'plan.json').write_text(json.dumps(plan)+'\n')
  recovery=archive(files,folder);result['archive_bytes']=recovery.stat().st_size
  result.update(worker({'mode':'apply','files':files}))
  (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 if args.apply:
  # Only our own verified archives; a failed/unverified run is never expired automatically.
  cutoff=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=7)
  for folder in STATE.glob('*'):
   if not folder.is_dir() or folder.is_symlink() or not (folder/'result.json').is_file():continue
   try:stamp=datetime.datetime.strptime(folder.name,'%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
   except ValueError:continue
   if stamp>=cutoff:continue
   allowed={'plan.json','result.json','recovery.tar.zst'}
   if {p.name for p in folder.iterdir()}<=allowed:
    for p in folder.iterdir():p.unlink()
    folder.rmdir()
 print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
