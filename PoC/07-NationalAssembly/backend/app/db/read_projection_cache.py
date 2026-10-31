"""Bounded copies of derived reads; source rows and model responses stay in DB."""
from collections import OrderedDict
import pickle
from threading import RLock
from time import monotonic
import zlib

class ProjectionCache:
    def __init__(self, max_bytes=32*1024*1024, max_entries=256, ttl=300, clock=monotonic):
        self.max_bytes=max_bytes;self.max_entries=max_entries;self.ttl=ttl;self.clock=clock
        self.rows=OrderedDict();self.bytes=0;self.lock=RLock();self.hits=0;self.misses=0

    def get(self,key):
        with self.lock:
            row=self.rows.get(key)
            if row is None:
                self.misses+=1;return None
            stamp,size,payload=row
            if self.clock()-stamp>=self.ttl:
                self.rows.pop(key);self.bytes-=size;self.misses+=1;return None
            self.rows.move_to_end(key);self.hits+=1
        # These bytes are generated only by put(), never read from a client/file.
        # Deserializing also isolates each caller's mutations from cached evidence.
        return pickle.loads(zlib.decompress(payload))

    def put(self,key,value):
        payload=zlib.compress(pickle.dumps(value,protocol=5),level=1);size=len(payload)
        if size>self.max_bytes:return
        with self.lock:
            previous=self.rows.pop(key,None)
            if previous:self.bytes-=previous[1]
            while self.rows and (self.bytes+size>self.max_bytes or len(self.rows)>=self.max_entries):
                _,(_,removed,_) = self.rows.popitem(last=False);self.bytes-=removed
            self.rows[key]=(self.clock(),size,payload);self.bytes+=size

    def clear(self):
        with self.lock:self.rows.clear();self.bytes=0

projection_cache=ProjectionCache()
