"""Isolated, bounded CPU OCR. No LLM, spell checker, or external image upload.
Input/output paths belong to a per-request private temporary directory.
"""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('request', type=Path); p.add_argument('output', type=Path)
    args = p.parse_args(); request = json.loads(args.request.read_text())
    # Paddle's caches stay in the portable service data directory.
    cache = Path(request['cache_dir']); cache.mkdir(parents=True, exist_ok=True)
    os.environ['PADDLE_PDX_CACHE_HOME'] = str(cache)
    os.environ['PADDLE_PDX_MODEL_SOURCE'] = 'BOS'
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    os.environ['OMP_NUM_THREADS'] = '2'
    import cv2
    import numpy as np
    from paddleocr import TextDetection, TextRecognition
    start = time.monotonic()
    det = TextDetection(model_name='PP-OCRv5_mobile_det', device='cpu', cpu_threads=2, enable_mkldnn=False)
    rec = TextRecognition(model_name='korean_PP-OCRv5_mobile_rec', device='cpu', cpu_threads=2, enable_mkldnn=False)
    image = cv2.imread(request['image']); h, w = image.shape[:2]
    # Overlapping native-resolution tiles preserve small glyphs on large inputs.
    tile = 1280; stride = 1088
    def starts(n):
        return sorted(set(list(range(0, max(1, n-tile+1), stride)) + [max(0,n-tile)]))
    tiles = [(x,y) for y in starts(h) for x in starts(w)]
    candidates = []; limit = request.get('max_regions', 64)
    def overlaps(a,b):
        area = max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
        return area / max(1, min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1])))
    for x,y in tiles[:24]:
        result = next(iter(det.predict(image[y:y+tile,x:x+tile], limit_side_len=1280, limit_type='max', thresh=.2, box_thresh=.45, unclip_ratio=1.5)))
        for poly, score in zip(result['dt_polys'], result['dt_scores']):
            poly = np.asarray(poly, dtype=np.float32) + [x,y]
            a = [max(0,float(poly[:,0].min())),max(0,float(poly[:,1].min())),min(w,float(poly[:,0].max())),min(h,float(poly[:,1].max()))]
            if a[2]-a[0]<4 or a[3]-a[1]<4:continue
            entry = dict(rect_px=a, polygon_px=poly.tolist(), detection_score=float(score), source='paddle-detector')
            duplicate = next((i for i,c in enumerate(candidates) if overlaps(a,c['rect_px'])>.7),None)
            if duplicate is None:candidates.append(entry)
            elif (a[2]-a[0])*(a[3]-a[1]) > (candidates[duplicate]['rect_px'][2]-candidates[duplicate]['rect_px'][0])*(candidates[duplicate]['rect_px'][3]-candidates[duplicate]['rect_px'][1]):candidates[duplicate]=entry
    detected_count = len(candidates)
    # Non-OCR visual text proposals survive even when detection/recognition misses them.
    for hint in request.get('proposals', [])[:40]:
        x1,y1,x2,y2 = hint['rect']; a=[x1*w,y1*h,x2*w,y2*h]
        if any(overlaps(a,c['rect_px'])>.5 for c in candidates):continue
        candidates.append(dict(rect_px=a,polygon_px=[[a[0],a[1]],[a[2],a[1]],[a[2],a[3]],[a[0],a[3]]],detection_score=None,source='visual-proposal',proposal_id=hint['id']))
    total = len(candidates)
    # Small sign regions first. Every omitted region is counted, never called normal.
    candidates.sort(key=lambda c:(c['rect_px'][3]-c['rect_px'][1],c['rect_px'][1],c['rect_px'][0]))
    regions = candidates[:limit]; crops=[]
    for region in regions:
        pts=np.asarray(region['polygon_px'],dtype=np.float32)
        rw=max(4,round(max(np.linalg.norm(pts[0]-pts[1]),np.linalg.norm(pts[2]-pts[3]))))
        rh=max(4,round(max(np.linalg.norm(pts[0]-pts[3]),np.linalg.norm(pts[1]-pts[2]))))
        matrix=cv2.getPerspectiveTransform(pts,np.float32([[0,0],[rw-1,0],[rw-1,rh-1],[0,rh-1]]))
        crops.append(cv2.warpPerspective(image,matrix,(rw,rh),borderMode=cv2.BORDER_REPLICATE))
    outputs=list(rec.predict(crops,batch_size=8)) if crops else []
    if len(outputs)!=len(regions):raise RuntimeError('recognition_count_mismatch')
    for i,(region,result) in enumerate(zip(regions,outputs)):
        region.update(id=f'OCR{i+1:03}',text=str(result['rec_text']),recognition_score=float(result['rec_score']),
                      rect=[region['rect_px'][0]/w,region['rect_px'][1]/h,region['rect_px'][2]/w,region['rect_px'][3]/h])
    args.output.write_text(json.dumps(dict(engine='PaddleOCR',detector='PP-OCRv5_mobile_det',recognizer='korean_PP-OCRv5_mobile_rec',
        version='3.3.3',status='COMPLETED',image_size=[w,h],detected_count=detected_count,candidate_count=total,
        deferred_count=max(0,total-limit),tiles_total=len(tiles),tiles_processed=min(24,len(tiles)),
        seconds=round(time.monotonic()-start,2),regions=regions),ensure_ascii=False))

if __name__ == '__main__':main()
