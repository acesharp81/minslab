"""Compressed immutable source objects and credential-free conditional metadata."""
import gzip
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

TEXT_SUFFIXES={'html','xml','json','csv','txt','raw'}

def atomic_write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def read_raw(path):
    path=Path(path)
    data=path.read_bytes()
    return gzip.decompress(data) if path.suffix=='.gz' else data

def preserve(folder,digest,suffix,data):
    folder=Path(folder);plain=folder/(digest+'.'+suffix);packed=plain.with_name(plain.name+'.gz')
    if plain.exists():return plain
    if packed.exists():return packed
    compressed=gzip.compress(data,compresslevel=6,mtime=0) if suffix in TEXT_SUFFIXES and len(data)>=4096 else data
    path=packed if len(compressed)<len(data)*.90 else plain
    atomic_write(path,compressed if path==packed else data)
    return path

class ConditionalCache:
    def __init__(self,root,source,url,headers=None):
        self.root=Path(root)
        # Hash credentials as part of identity, never persist the request URL/key.
        key=hashlib.sha256(json.dumps([source,str(url),headers or {}],sort_keys=True).encode()).hexdigest()
        self.path=self.root/'.http-cache'/key[:2]/(key+'.json');self.meta=None
        try:
            meta=json.loads(self.path.read_text())
            candidate=(self.root/meta['file']).resolve()
            if candidate.is_relative_to(self.root.resolve()) and candidate.is_file() and time.time()-meta['verified']<7*86400:self.meta=meta
        except (OSError,ValueError,KeyError):pass
    def headers(self):
        if not self.meta:return {}
        return {k:self.meta[v] for k,v in [('If-None-Match','etag'),('If-Modified-Since','modified')] if self.meta.get(v)}
    def body(self):
        if not self.meta:return None
        try:
            value=read_raw(self.root/self.meta['file'])
            if hashlib.sha256(value).hexdigest()==self.meta['sha256']:return value
        except (OSError,ValueError,EOFError):pass
        self.meta=None
        return None
    def save(self,response,entry):
        if 'no-store' in response.headers.get('cache-control','').lower():return
        etag=response.headers.get('etag');modified=response.headers.get('last-modified')
        if not etag and not modified:return
        atomic_write(self.path,json.dumps(dict(file=entry['file'],sha256=entry['sha256'],etag=etag,modified=modified,verified=time.time())).encode())
