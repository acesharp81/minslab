import hashlib,importlib.util,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('retention',Path(__file__).with_name('home_retention.py'));r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class RecoveryTests(unittest.TestCase):
 def test_verified_archive_preserves_original_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source';source.mkdir();folder=root/'backup';folder.mkdir()
   body=b'<html>unchanged official facts</html>';name=hashlib.sha256(body).hexdigest()+'.html';p=source/name;p.write_bytes(body);s=p.stat()
   out=r.archive([dict(name=name,inode=s.st_ino,mtime_ns=s.st_mtime_ns,bytes=s.st_size)],folder,source)
   self.assertTrue(out.exists());self.assertEqual(p.read_bytes(),body)
 def test_changed_source_aborts_before_deletion(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source';source.mkdir();folder=root/'backup';folder.mkdir();p=source/('a'*64+'.html');p.write_bytes(b'changed');s=p.stat()
   with self.assertRaises(AssertionError):r.archive([dict(name=p.name,inode=s.st_ino,mtime_ns=s.st_mtime_ns,bytes=s.st_size)],folder,source)
   self.assertEqual(p.read_bytes(),b'changed')
 def test_archive_rejects_paths_outside_source(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source';source.mkdir();folder=root/'backup';folder.mkdir()
   with self.assertRaises(AssertionError):r.archive([dict(name='../outside.html',inode=0,mtime_ns=0,bytes=0)],folder,source)
