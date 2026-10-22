"""User-requested descriptive iH labels; preserve program IDs and membership."""
import json
from backend.db import engine_for
from backend.service import HomeService
from backend.program_profile import save,profiles


def main():
    service=HomeService(engine_for());folder=service.data_dir/'incheon-labels-20261020';folder.mkdir(exist_ok=True)
    before=service.program_links();details=profiles(service);results=[]
    for p in before:
        if not p['name'].startswith('iH '):continue
        name='인천도시공사(iH) '+p['name'][3:]
        result=save(service,p['id'],details.get(p['id'],{}).get('revision_no',0),dict(name=name),
                    '담당자 대행 · 사용자 인천 프로그램·사업 지역명 정비 지시',
                    'iH 약칭을 인천도시공사(iH)로 명시. 프로그램 ID·유형·정책 연결·사업 구성·물량 보존',mapping_revision_no=p['revision_no'])
        if result.get('conflict'):raise ValueError('프로그램 이름 판본 충돌')
        results.append(dict(id=p['id'],before=p['name'],after=name))
    after=service.program_links()
    signature=lambda rows:sorted((r['id'],r['policy_id'],r['status'],r['project_count']) for r in rows)
    assert signature(before)==signature(after)
    target=folder/('program-labels-applied.json' if results else 'program-labels-idempotence.json')
    target.write_text(json.dumps(dict(changed=results,program_memberships_unchanged=True),ensure_ascii=False,indent=2))
    print(json.dumps(dict(changed=results,program_memberships_unchanged=True),ensure_ascii=False))


if __name__=='__main__':main()
