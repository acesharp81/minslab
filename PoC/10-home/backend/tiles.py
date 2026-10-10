"""Fixed official tile origin. API credentials stay on the server."""
import os
import time
from functools import lru_cache

import httpx


@lru_cache(maxsize=256)
def _fetch(z,x,y,hour):
    key=os.environ.get("POC10_VWORLD_API_KEY","").strip()
    if not key:
        raise ValueError("배경지도 키 설정을 확인하세요")
    try:
        with httpx.Client(timeout=12,follow_redirects=False) as client:
            response=client.get(f"https://api.vworld.kr/req/wmts/1.0.0/{key}/Base/{z}/{y}/{x}.png",
                                headers={"Referer":"https://www.minslab.kr/poc/home/"})
        if response.status_code!=200 or not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("공식 배경지도 응답을 확인하지 못했습니다")
        return response.content
    except httpx.HTTPError:
        raise ValueError("공식 배경지도 연결 실패") from None


def tile(z,x,y):
    if not 7<=z<=18 or not 0<=x<2**z or not 0<=y<2**z:
        raise ValueError("배경지도 좌표 범위 오류")
    return _fetch(z,x,y,int(time.time()//3600))
