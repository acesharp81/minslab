from pathlib import Path
import os,time,json,collections
root=Path('/app/data/raw');now=time.time();groups=collections.defaultdict(lambda:dict(files=0,bytes=0,new_24h_files=0,new_24h_bytes=0));large=[]
for parent,dirs,files in os.walk(root):
 source=Path(parent).relative_to(root).parts
 if not source:continue
 g=groups[source[0]]
 for name in files:
  try:s=os.stat(os.path.join(parent,name))
  except OSError:continue
  g['files']+=1;g['bytes']+=s.st_size
  if s.st_mtime>=now-86400:g['new_24h_files']+=1;g['new_24h_bytes']+=s.st_size
print(json.dumps(dict(measured_at=now,raw_sources=sorted((dict(source=k,**v) for k,v in groups.items()),key=lambda r:r['bytes'],reverse=True)),indent=2))
