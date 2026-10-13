"""Acquire original V-World buildings and adapt PoC 10 candidates to original 3D bundles.

Only a unique LH land polygon and matching district/block names can associate
observed buildings with a candidate. That association remains REVIEW.
Missing geometry is a visibly labelled, deterministic illustration. Unknown
locations get an isolated scene at (0,0), never a claimed geographic location.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from pathlib import Path
import sys
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.regiontools import geo

CACHE = ROOT / ".cache" / "home10-3d"
SCENE = ROOT / "data" / "home10" / "scene.json"
SCHEMATIC_NOTE = "가상 아파트 모형: 계획 규모에 따라 배치한 예시 동수·층수·평면이며 실제 설계가 아닙니다."
POLICY = "POL_2025_0907"

def read_json(path):
    return json.loads(Path(path).read_text())

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    temp.replace(path)

def fetch_json(url):
    with urlopen(url, timeout=45) as response:
        return json.load(response)

def feature_key(feature):
    return hashlib.sha256(json.dumps(feature["geometry"], sort_keys=True).encode()).hexdigest()[:20]

def ring_open(ring):
    return ring[:-1] if ring[0] == ring[-1] else ring

def meters_point(center, x, y):
    return [round(center[0]+x/(111320*math.cos(math.radians(center[1]))), 7), round(center[1]+y/111320, 7)]

def rectangle(center, width, depth):
    return [meters_point(center, x, y) for x,y in [(-width/2,-depth/2),(width/2,-depth/2),(width/2,depth/2),(-width/2,depth/2)]]

def footprint(center, width, depth):
    # Apartment slab with a central lift/stair core: same polygon input as original dongs.
    return [meters_point(center,x,y) for x,y in [(-width/2,-depth/2),(width/2,-depth/2),(width/2,depth/3),
        (width/6,depth/3),(width/6,depth/2),(-width/6,depth/2),(-width/6,depth/3),(-width/2,depth/3)]]

def bounds(ring):
    return [min(p[0] for p in ring),min(p[1] for p in ring),max(p[0] for p in ring),max(p[1] for p in ring)]

def land_at(point, lands):
    hits = []
    for feature in lands:
        for polygon in geo.polygons_of(feature["geometry"]):
            geom = {"type":"Polygon","coordinates":polygon}
            if geo.point_in_geometry(point,geom):
                hits.append((feature,geom))
    return hits[0] if len(hits)==1 else (None,None)

def requested_cells(center, shape):
    ring = shape["coordinates"][0] if shape else rectangle(center,500,500)
    west,south,east,north = bounds(ring)
    # Include surrounding original buildings for context; no blanket regional download.
    dx,dy = 150/(111320*math.cos(math.radians(center[1]))),150/111320
    return {(x,y) for x in range(math.floor((west-dx)*100),math.floor((east+dx)*100)+1)
                  for y in range(math.floor((south-dy)*100),math.floor((north+dy)*100)+1)}

def acquire_cell(cell, api, refresh):
    path = CACHE / "cells" / f"{cell[0]}_{cell[1]}.json"
    if path.exists() and not refresh:
        return cell, read_json(path)
    try:
        result=fetch_json(f"{api}/api/v1/buildings?cell={cell[0]},{cell[1]}")
        if result.get("type")!="FeatureCollection":
            raise ValueError("invalid building response")
        write_json(path,result)
        return cell,result
    except Exception as exc:
        return cell,{"type":"FeatureCollection","features":[],"acquisitionError":f"HTTP {exc.code}" if isinstance(exc,HTTPError) else type(exc).__name__}

def synthetic_dongs(center, units, shape=None):
    # HOME scales illustrative mass with source plan size. Here: 4 units/floor,
    # approximately 24 floors/tower; cap display density, never source facts.
    desired=max(3,min(16,math.ceil(units/96))) if isinstance(units,(int,float)) and units>0 else 4
    columns=math.ceil(math.sqrt(desired)); rows=math.ceil(desired/columns)
    outline=ring_open(shape["coordinates"][0]) if shape else rectangle(center,columns*54+24,rows*45+24)
    geom=shape or {"type":"Polygon","coordinates":[outline+[outline[0]]]}
    w,s,e,n=bounds(outline)
    mid=[(w+e)/2,(s+n)/2]
    width=(e-w)*111320*math.cos(math.radians(center[1])); depth=(n-s)*111320
    choices=[]
    for scale in (1,.75,.5,.32):
        choices=[]
        step_x,step_y=48*scale,38*scale
        for yi in range(max(1,int(depth/step_y))):
            for xi in range(max(1,int(width/step_x))):
                c=meters_point(mid,(xi-(max(1,int(width/step_x))-1)/2)*step_x,(yi-(max(1,int(depth/step_y))-1)/2)*step_y)
                poly=footprint(c,32*scale,18*scale)
                if all(geo.point_in_geometry(p,geom) for p in poly):
                    choices.append((sum((p-q)**2 for p,q in zip(c,center)),poly))
        if len(choices)>=desired:
            break
    choices.sort(key=lambda row:row[0])
    chosen=choices[:desired]
    if not chosen:
        # Extremely narrow land: a tiny symbol at the evidenced interior point.
        for scale in (.2,.05,.01):
            poly=footprint(center,32*scale,18*scale)
            if all(geo.point_in_geometry(p,geom) for p in poly):
                chosen=[(0,poly)];break
    dongs=[]
    for i,(_,poly) in enumerate(chosen):
        floors=[20,24,27,22,25,18][i%6]
        dongs.append({"no":f"가상 {i+1}","floorsAbove":floors,"heightM":round(floors*2.85,2),
                      "tier":"schematic","poly":[poly],"heightBasis":"ILLUSTRATIVE_ASSUMPTION"})
    return outline,dongs

def building_identity_matches(name, rows):
    # Old apartments inside a redevelopment site are not the planned candidate.
    # Require its district AND block in the building name, beyond containment.
    compact=lambda value: re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())
    name=str(name or "").lower()
    for row in rows:
        district,block=compact(row.get("district")),compact(row.get("block"))
        pattern=r"[\s-]*".join(re.escape(c) for c in district+block)+r"(?![0-9a-z-])"
        if len(district)>=4 and block and re.search(pattern,name):
            return True
    return False

def observed_dongs(features, shape, rows):
    if not shape:return []
    dongs=[]
    for feature in features:
        p=feature.get("properties") or {}
        floor=p.get("f")
        if p.get("u")!="공동주택" or not floor or floor<5:continue
        if not building_identity_matches(p.get("n"),rows):continue
        rings=[ring_open(poly[0]) for poly in geo.polygons_of(feature["geometry"]) if poly and len(poly[0])>=4]
        if not rings:continue
        if not all(geo.point_in_geometry(geo.ring_centroid(ring),shape) for ring in rings):continue
        dongs.append({"no":p.get("n") or f"관측 {len(dongs)+1}","floorsAbove":floor,
            "heightM":p.get("h") or p["eh"],"heightBasis":p.get("src"),
            "tier":"building","poly":rings,"featureKey":feature_key(feature)})
    return dongs

def representative(rows):
    priority={"lh_construction":0,"lh_progress":1,"lh_sale":2,"lh_rent":3}
    return sorted(rows,key=lambda p:(priority.get(p["sourceId"],4),p["id"]))[0]

def site_record(key,rows,center,shape,land,features,preview=False):
    p=representative(rows)
    dongs=[] if preview else observed_dongs(features,shape,rows)
    model="OBSERVED_BUILDINGS" if dongs else "SCHEMATIC"
    if not dongs: outline,dongs=synthetic_dongs(center,p["plannedUnits"],shape)
    else: outline=ring_open(shape["coordinates"][0])
    label=" ".join(v for v in (p.get("district"),p.get("block")) if v) or p["name"]
    note=("공식 건물 형상과 LH 용지·지구명·블록명의 대조 결과이며 사업 동일성은 검토 중입니다." if model=="OBSERVED_BUILDINGS" else SCHEMATIC_NOTE)
    if preview:note="위치 미확보 · 배경지도 없는 가상 배치입니다. "+note
    else:note+=" 위치는 LH 블록 라벨점 연결 검토입니다."
    if len(rows)>1:note+=f" 같은 블록의 원천 후보 {len(rows)}건을 하나의 모형으로 표시합니다. 계획 호수는 대표 원천 값이며 합산하지 않습니다."
    result={"id":key,"label":label,"name":p["name"],"zoneId":"home",
        "sponsorClass":"public","kind":"공동주택 · "+("공식 건물 형상" if model=="OBSERVED_BUILDINGS" else "가상 모형"),
        "status":"건설 단계" if p["stageCode"]=="04" else "계획","units":p["plannedUnits"],
        "outline":{"tier":"official" if shape else "schematic","poly":outline,
                   "how":"LH 공동주택용지 내 라벨점 공간 대조(검토)" if shape else "가상 배치 범위 · 실제 사업 경계 아님"},
        "dongs":dongs,"dongCount":len(dongs),"homeModelKind":model,
        "homeLocationMode":"UNLOCATED_PREVIEW" if preview else "LH_LABEL_REVIEW",
        "candidateIds":[x["id"] for x in rows],"candidateNames":[x["name"] for x in rows],
        "primaryCandidateId":p["id"],"region":p["region"],"municipality":p["municipality"],
        "center":center,"note":note,"sources":["home10","vworld-buildings"] if model=="OBSERVED_BUILDINGS" else ["home10","illustration"],
        "geometryEvidenceUrl":p.get("locationEvidenceUrl"),"landName":land["properties"]["name"] if land else None}
    if p["progressPct"] is not None:
        result["progress"]={"rate":p["progressPct"],"asOf":p["progressDate"] or p["baseDate"] or "",
            "history":[],"start":p["startActualDate"],"end":p["completionPlanDate"],"source":p["sourceName"]}
    result["moveIn"]=p["moveInStartDate"] or None
    result["builder"]=p["contractor"] or None
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api",default="http://127.0.0.1:18120/poc/housing-board")
    parser.add_argument("--refresh",action="store_true")
    args=parser.parse_args()
    data=read_json(ROOT/"data/home10/converted.json")
    projects=data["projects"]
    if not all(p["policyId"]==POLICY for p in projects):raise ValueError("unexpected policy")
    geometry=fetch_json("http://127.0.0.1:18100/poc/home/api/policy-geo/geometry")
    write_json(CACHE/"home-geometry.json",geometry)
    groups=defaultdict(list); unlocated=[]
    for p in projects:
        if p["locationRole"]=="LH_PUBLIC_BLOCK_LABEL_POINT" and p["longitude"] is not None and p["latitude"] is not None:
            groups[p["locationAnchorId"]].append(p)
        else:unlocated.append(p)
    jobs={};all_cells=set()
    for key,rows in groups.items():
        p=rows[0];center=[p["longitude"],p["latitude"]]
        land,shape=land_at(center,geometry["housing_lands"]["features"])
        cells=requested_cells(center,shape);all_cells.update(cells)
        jobs[key]=(rows,center,land,shape,cells)
    print(f"Collecting {len(all_cells)} V-World cells for {len(groups)} evidenced blocks",flush=True)
    cells={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(acquire_cell,c,args.api.rstrip("/"),args.refresh) for c in sorted(all_cells)]
        for i,future in enumerate(as_completed(futures),1):
            cell,body=future.result();cells[cell]=body
            if i%10==0 or i==len(futures):print(f"Cells {i}/{len(futures)}; failures {sum('acquisitionError' in x for x in cells.values())}",flush=True)
    sites=[];context={};claimed=set()
    for key,(rows,center,land,shape,needed) in jobs.items():
        features={feature_key(f):f for cell in needed for f in cells[cell]["features"]}
        site=site_record(key,rows,center,shape,land,list(features.values()));sites.append(site)
        claimed.update(d["featureKey"] for d in site["dongs"] if d.get("featureKey"))
        radius=max(350, max(math.dist(center,p)*111320 for p in site["outline"]["poly"])+120)
        for k,f in features.items():
            c=geo.geometry_centroid(f["geometry"])
            dx=(c[0]-center[0])*111320*math.cos(math.radians(center[1]));dy=(c[1]-center[1])*111320
            if math.hypot(dx,dy)<radius:
                context[k]={**f,"properties":{**f["properties"],"homeRegion":rows[0]["region"]}}
    previews=[site_record("preview:"+p["id"],[p],[0.,0.],None,None,[],True) for p in unlocated]
    background=[f for k,f in context.items() if k not in claimed]
    kinds=Counter(s["homeModelKind"] for s in sites)
    now=datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary={"candidates":len(projects),"locatedCandidates":sum(len(s["candidateIds"]) for s in sites),
        "sites":len(sites),"officialLandMatches":sum(s["outline"]["tier"]=="official" for s in sites),
        "observedSites":kinds["OBSERVED_BUILDINGS"],"schematicSites":kinds["SCHEMATIC"],
        "observedDongs":sum(len(s["dongs"]) for s in sites if s["homeModelKind"]=="OBSERVED_BUILDINGS"),
        "schematicDongs":sum(len(s["dongs"]) for s in sites if s["homeModelKind"]=="SCHEMATIC"),
        "unlocatedPreviews":len(previews),"contextBuildings":len(background),
        "requestedCells":len(cells),"failedCells":sum("acquisitionError" in x for x in cells.values()),
        "truncatedCells":sum(bool(x.get("meta",{}).get("truncated")) for x in cells.values())}
    scene={"format":"poc12-home10-scene/1","readFinishedAt":now,"candidateSnapshotAt":data["readFinishedAt"],
        "summary":summary,"sites":sites,"previews":previews,
        "buildings":{"type":"FeatureCollection","meta":{"basis":now[:10],"factor":{},"source":"V-World LT_C_BLDGINFO"},"features":background},
        "acquisition":[{"cell":list(c),"count":len(b["features"]),"error":b.get("acquisitionError"),"truncated":b.get("meta",{}).get("truncated",False)} for c,b in sorted(cells.items())],
        "illustrationAssumptions":{"unitsPerFloor":4,"referenceFloors":24,"displayTowerRange":[3,16],
           "illustrativeFloors":[20,24,27,22,25,18],"floorHeightM":2.85,
           "note":SCHEMATIC_NOTE}}
    write_json(SCENE,scene)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    print(f"scene -> {SCENE}",flush=True)

if __name__=="__main__": main()
