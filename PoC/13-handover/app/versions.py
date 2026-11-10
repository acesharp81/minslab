"""Content-only version ordering. File names, mtimes and upload order are never clocks."""
import re
from datetime import date, datetime

VERSION_POLICY = 'content-versions-v1'
LABELS = {
 'reported_at':['내용 기준일','자료 기준일','실적 기준일','보고 기준일','기준일','보고일'],
 'issued_at':['최종 수정일시','수정일시','작성일시'],
 'report_id':['보고서 관리번호','문서관리번호','보고서관리번호'],
 'revision_no':['수정차수','개정차수','문서버전'],
 'document_state':['문서상태','문서 상태'],
 'work_code':['사업관리번호','연계관리번호'],
 'stage':['보고단계'], 'progress':['전체 진행률','사업 진행률'],
 'start_date':['계획 시작일'], 'completed_at':['실제 완료일']}


def iso_date(value, timestamp=False):
    m=re.fullmatch(r'(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*[.일]?(?:\s+(\d{1,2}):(\d{2}))?',value.strip())
    if not m:return None
    try:
        y,month,day=map(int,m.group(1,2,3));result=date(y,month,day).isoformat()
        if timestamp:
            if m.group(4) is None:return None
            result=datetime(y,month,day,int(m.group(4)),int(m.group(5))).isoformat(timespec='minutes')
        return result
    except ValueError:return None


def metadata(blocks, evidence):
    values={};refs=[];problems=[]
    for key,labels in LABELS.items():
        names='|'.join(re.escape(v) for v in labels)
        pattern=re.compile(r'^\s*[□○\-]?\s*(?:\((?:'+names+r')\)\s*[:：]?|(?:'+names+r')\s*[:：|])\s*(.+?)\s*$')
        matches=[]
        for block in blocks:
            # Coordinates are parser annotations, not document metadata.
            normalized=re.sub(r'(^|\|\s*)[A-Z]+\d*:\s*',r'\1',block['text'])
            # PDF may wrap a resource record across lines within one labelled block.
            if key=='reported_at' and re.match(r'^\s*(?:[○□-]\s*)?(?:\(예산 현황\)|예산 현황[:：]|예산코드[:：]|관계자ID[:：])',normalized):continue
            lines=normalized.splitlines()
            # A budget/contact record has its own date, not the report's version date.
            for line in [segment for row in lines if not (key=='reported_at' and re.search(r'(?:예산코드|관계자ID)\s*[:：]',row)) for segment in re.split(r'\s*\|\s*(?=[^|:：]+[:：])',row)]:
                m=pattern.match(line)
                if not m:continue
                raw=m.group(1).strip();v=raw
                if key in {'reported_at','start_date','completed_at','issued_at'}:v=iso_date(raw,key=='issued_at')
                elif key=='revision_no':
                    n=re.fullmatch(r'(?:제\s*|v)?(\d{1,4})(?:\s*차|판)?',raw,re.I);v=int(n.group(1)) if n else None
                elif key=='progress':
                    n=re.fullmatch(r'(\d{1,3})\s*%',raw);v=int(n.group(1)) if n and int(n.group(1))<=100 else None
                elif key in {'report_id','work_code'}:v=raw if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{1,79}',raw) else None
                elif key=='document_state':v=raw if raw in {'확정','승인','초안','검토중','검토 중','폐기','대체됨','참고본'} else None
                elif key=='stage':v=raw.removesuffix('보고') if raw.removesuffix('보고') in {'계획','착수','중간','완료'} else None
                if v is None:problems.append(key+' 형식 확인 필요')
                matches.append((v,block))
        distinct={v for v,b in matches}
        values[key]=next(iter(distinct)) if len(distinct)==1 and None not in distinct else None
        if len(distinct)>1:problems.append(key+' 본문 값 상충')
        if values[key] is not None:
            for _,block in matches:refs.append(evidence(block,block['text']))
    return {**values,'metadata_evidence':refs,'metadata_problems':sorted(set(problems))}


def eligible(event):
    return event.get('document_state') not in {'초안','검토중','검토 중','폐기','대체됨','참고본'}


def signature(event):
    return tuple(sorted((k,v.get('value','')) for k,v in event['fields'].items()))+(('progress',event.get('progress')),)


def newest(events):
    if not events:return None,'현재 기준으로 사용할 진행보고가 없습니다.'
    if any(not e.get('reported_at') or e.get('metadata_problems') for e in events):
        return None,'기준일 누락 또는 본문 메타정보 상충으로 최신본 자동 선택을 보류했습니다.'
    latest_day=max(e['reported_at'] for e in events)
    same=[e for e in events if e['reported_at']==latest_day]
    if len(same)==1:return same[0],'본문 기준일이 가장 최신인 보고서를 선택했습니다.'
    if len({e.get('report_id') for e in same})==1 and same[0].get('report_id') and all(e.get('revision_no') is not None and e.get('issued_at') for e in same):
        if any(a['revision_no']>b['revision_no'] and a['issued_at']<b['issued_at'] for a in same for b in same):
            return None,'수정차수와 수정일시의 순서가 서로 달라 선택을 보류했습니다.'
    if len({signature(e) for e in same})==1:
        return min(same,key=lambda e:e['document_id']),'동일 기준일의 내용이 일치하는 사본을 하나의 최신 정보로 취급했습니다.'
    ids={e.get('report_id') for e in same}
    if len(ids)!=1 or None in ids:return None,'같은 기준일의 상충 자료에 동일 보고서 관리번호가 없어 선택을 보류했습니다.'
    if all(e.get('revision_no') is not None for e in same):
        if all(e.get('issued_at') for e in same):
            if any(a['revision_no']>b['revision_no'] and a['issued_at']<b['issued_at'] for a in same for b in same):
                return None,'수정차수와 수정일시의 순서가 서로 달라 선택을 보류했습니다.'
        rev=max(e['revision_no'] for e in same);same=[e for e in same if e['revision_no']==rev]
        reason='동일 보고서·기준일에서 본문 수정차수가 가장 높은 판을 선택했습니다.'
        if len(same)==1:return same[0],reason
    if all(e.get('issued_at') for e in same):
        time=max(e['issued_at'] for e in same);same=[e for e in same if e['issued_at']==time]
        if len(same)==1:return same[0],'동일 보고서·기준일에서 본문 수정일시가 가장 늦은 판을 선택했습니다.'
    if len({signature(e) for e in same})==1:return min(same,key=lambda e:e['document_id']),'동일 판의 내용 일치 사본입니다.'
    return None,'동일 기준일·수정차수의 내용이 상충하여 최신본 자동 선택을 보류했습니다.'


def ordered(events):
    return sorted(events,key=lambda e:(e.get('reported_at') or '',e.get('revision_no') or 0,e.get('issued_at') or '',e['document_id']))
