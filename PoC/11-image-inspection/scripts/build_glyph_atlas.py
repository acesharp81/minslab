"""Rebuild deterministic Hangul shape assets from installed OFL Noto fonts.
No test images, answer labels, word lists or external API are used.
"""
from pathlib import Path
import hashlib,json
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]

def build():
    dest=ROOT/'rules/glyph-shapes';dest.mkdir(exist_ok=True)
    names=['NotoSansCJK-Regular','NotoSansCJK-Bold','NotoSansCJK-Black','NotoSerifCJK-Regular']
    arrays=[];sources=[]
    for name in names:
        path=Path('/usr/share/fonts/opentype/noto')/(name+'.ttc');font=ImageFont.truetype(str(path),64,index=1);glyphs=[]
        for code in range(0xAC00,0xD7A4):
            im=Image.new('L',(100,110),0);ImageDraw.Draw(im).text((8,0),chr(code),font=font,fill=255)
            a=np.asarray(im);_,a=cv2.threshold(a,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU);y,x=np.nonzero(a)
            a=a[y.min():y.max()+1,x.min():x.max()+1]
            glyphs.append(cv2.resize(a,(64,64),interpolation=cv2.INTER_AREA))
        arrays.append(np.stack(glyphs));sources.append(dict(name=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),face=1))
        print(name,flush=True)
    path=dest/'hangul-v1.npz';np.savez_compressed(path,glyphs=np.stack(arrays))
    (dest/'manifest.json').write_text(json.dumps(dict(version='hangul-shape-v1',range=['AC00','D7A3'],size=64,sources=sources,asset_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),purpose='Glyph pixel similarity, not a spelling dictionary or official text reference'),ensure_ascii=False,indent=2))
    print('Bytes',path.stat().st_size,flush=True)
if __name__=='__main__':build()
