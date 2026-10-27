import pytest
from app.services.partitioned_consolidation import partitions,prompt,normalize
from app.services.topic_structure import consolidation_input,apply_consolidation


def items(n=369):
 return [{'id':str(i),'parent':'예산','issue':f'사업 {i} 예산 심사','evidence':[{'role':'ANSWER','quote':f'사업 {i} 원문'}]} for i in range(n)]


def test_large_meeting_partitions_cover_every_issue_once():
 data=items();parts=partitions(data)
 assert len(parts)==8 and max(map(len,parts))==48
 assert [n for part in parts for n in part]==list(range(369))
 for part in parts:
  p=prompt(data,part)
  assert all(data[n]['evidence'][0]['quote'] in p for n in part)
  assert len(p.encode())<100000


def test_cross_partition_canonical_links_preserve_all_evidence():
 facets=[{'parent':'예산','issue':'지역 버스 운행 예산 점검','role':'ANSWER','quote':'첫 번째 원문'},
         {'parent':'교통','issue':'지역 버스 운행 예산 심사','role':'QUESTION','quote':'두 번째 원문'}]
 data=consolidation_input(facets)
 first=normalize(data,[0],{'groups':[{'parent':'지역 교통 예산','canonical':0,'members':[0]}]})
 second=normalize(data,[1],{'groups':[{'parent':'지역 교통 예산','canonical':0,'members':[1]}]})
 result=apply_consolidation(facets,{'assignments':{**first['assignments'],**second['assignments']}})
 assert len({x['issue'] for x in result})==1
 assert [x['quote'] for x in result]==['첫 번째 원문','두 번째 원문']


@pytest.mark.parametrize('canonical,members',[(1,[0]),(0,[0,0]),(0,[1]),(0,[0,2]),(0,[True]),(-1,[0]),(0,[])])
def test_invalid_cross_partition_membership_or_cycles_are_rejected(canonical,members):
 with pytest.raises(ValueError):normalize(items(2),[0],{'groups':[{'parent':'예산','canonical':canonical,'members':members}]})


def test_catalogue_only_members_do_not_change_other_partitions():
 raw={'groups':[{'parent':'예산','canonical':0,'members':[0,1,1]}]}
 result=normalize(items(2),[0],raw)
 assert set(result['assignments'])=={'0'}
 assert result['raw_partition_response']==raw


def test_fixed_member_schema_requires_every_target_and_bounds_canonical():
 from app.services.partitioned_consolidation import schema
 contract=schema(items(100),[48,49])['properties']['assignments']
 assert contract['required']==['48','49']
 assert contract['properties']['48']['properties']['canonical']['maximum']==48
 raw={'assignments':{'48':{'parent':'예산','canonical':0},'49':{'parent':'예산','canonical':49}}}
 assert set(normalize(items(100),[48,49],raw)['assignments'])=={'48','49'}
 del raw['assignments']['49']
 with pytest.raises(ValueError,match='INCOMPLETE_PARTITION'):normalize(items(100),[48,49],raw)
