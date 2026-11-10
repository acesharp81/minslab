"""Preserve explicit HWPX text controls for the pinned syhwp reader.

Only the temporary parsing copy changes; uploaded bytes/hashes remain untouched.
"""
import tempfile,zipfile,uuid
from defusedxml import ElementTree as ET
from pathlib import Path

def open_with_breaks(path):
 import syhwp
 from syhwp.models import Paragraph,Table
 marker='HWB'+uuid.uuid4().hex
 breaks={'lineBreak':marker+'N','tab':marker+'T'}
 with tempfile.TemporaryDirectory(prefix='handover-hwpx-') as folder:
  target=Path(folder)/'read.hwpx'
  with zipfile.ZipFile(path) as src,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as dst:
   for info in src.infolist():
    data=src.read(info)
    if info.filename.startswith('Contents/section') and info.filename.endswith('.xml'):
     root=ET.fromstring(data, forbid_dtd=True);changed=False
     for node in root.iter():
      if node.tag.rsplit('}',1)[-1]!='t':continue
      controls=[c for c in node.iter() if c.tag.rsplit('}',1)[-1] in {'lineBreak','tab'}]
      if not controls:continue
      for control in controls:control.text=breaks[control.tag.rsplit('}',1)[-1]]+(control.text or '')
      text=''.join(node.itertext())
      for child in list(node):node.remove(child)
      node.text=text;changed=True
     if changed:data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    dst.writestr(info,data)
  doc=syhwp.open(target)
  def restore(text):return text.replace(breaks['lineBreak'],'\n').replace(breaks['tab'],'\t')
  for block in doc.blocks:
   if isinstance(block,Paragraph):block.text=restore(block.text)
   elif isinstance(block,Table):
    for cell in block.cells:cell.text=restore(cell.text)
  return doc
