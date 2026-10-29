import hashlib
import io
import re
import warnings
from PIL import Image, ImageOps, ImageDraw, ImageFont

FORMATS = {'PNG': ('image/png', {'.png'}), 'JPEG': ('image/jpeg', {'.jpg', '.jpeg'}), 'WEBP': ('image/webp', {'.webp'})}
GRID = {'id': 'main-v1', 'rows': 12, 'cols': 12}


def cell_rect(cell, rows=12, cols=12):
    m = re.fullmatch(r'R(\d{2})C(\d{2})', cell)
    if not m:
        raise ValueError('invalid_cell_id')
    r, c = map(int, m.groups())
    if not 1 <= r <= rows or not 1 <= c <= cols:
        raise ValueError('cell_out_of_range')
    return [(c-1)/cols, (r-1)/rows, c/cols, r/rows]


def normalize(raw, filename, mime, max_pixels):
    from pathlib import Path
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(raw))
            fmt = im.format
            if fmt not in FORMATS or mime != FORMATS[fmt][0] or Path(filename).suffix.lower() not in FORMATS[fmt][1]:
                raise ValueError('파일 확장자·MIME·실제 이미지 형식이 일치해야 합니다. PNG/JPEG/WebP만 지원합니다.')
            if im.width * im.height > max_pixels or min(im.size) < 24 or getattr(im, 'n_frames', 1) != 1:
                raise ValueError('단일 정적 이미지, 최소 24px, 설정된 최대 해상도 이하만 허용합니다.')
            im.load()
            im = ImageOps.exif_transpose(im).convert('RGBA')
            out = Image.new('RGB', im.size, 'white')
            out.paste(im, mask=im.getchannel('A'))
            b = io.BytesIO(); out.save(b, format='PNG')
            return b.getvalue(), {'width': out.width, 'height': out.height, 'original_sha256': hashlib.sha256(raw).hexdigest(),
                                 'normalized_sha256': hashlib.sha256(b.getvalue()).hexdigest(), 'orientation_normalized': True}
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('이미지를 안전하게 해독할 수 없습니다.') from exc


def labeled(raw, rows=12, cols=12):
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    im.thumbnail((1800, 1800))
    if im.width < cols*65 or im.height < rows*28:
        scale = max(cols*65/im.width, rows*28/im.height)
        im = im.resize((round(im.width*scale), round(im.height*scale)))
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=12)
    for r in range(rows):
        for c in range(cols):
            x, y = round(c*im.width/cols), round(r*im.height/rows)
            d.rectangle((x,y,round((c+1)*im.width/cols)-1,round((r+1)*im.height/rows)-1),outline='#6b7280',width=1)
            label = f'R{r+1:02}C{c+1:02}'
            d.rectangle((x,y,x+56,y+15),fill='white')
            d.text((x+2,y+1),label,font=font,fill='#111827')
    b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()


def crop(raw, cells):
    rects = [cell_rect(x) for x in cells]
    if not rects: raise ValueError('crop_cells_required')
    rect = [min(r[0] for r in rects),min(r[1] for r in rects),max(r[2] for r in rects),max(r[3] for r in rects)]
    im=Image.open(io.BytesIO(raw));w,h=im.size
    px=[round(rect[0]*w),round(rect[1]*h),round(rect[2]*w),round(rect[3]*h)]
    im=im.crop(px);b=io.BytesIO();im.save(b,format='PNG')
    return b.getvalue(),[px[0]/w,px[1]/h,px[2]/w,px[3]/h]


def global_rect(local_cell, crop_rect):
    a,b,c,d=cell_rect(local_cell,8,8);x,y,z,w=crop_rect
    return [x+a*(z-x), y+b*(w-y), x+c*(z-x), y+d*(w-y)]
