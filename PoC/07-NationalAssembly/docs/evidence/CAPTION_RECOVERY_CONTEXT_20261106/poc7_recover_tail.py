import json,hashlib,subprocess,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
from app.config import get_settings
from app.db.connection import connect
from app.db.live_repository import LiveRepository,CaptionRevision
from app.db.executive_audio_repository import ExecutiveAudioRepository
from app.db.schedule_repository import SourceVersionInput
from app.db.summary_repository import SummaryRepository
from app.adapters.national_assembly.base import SourcePayload
from app.storage.raw_store import RawStore
from app.services.mistral_transcription import MistralTranscriptionClient
from app.services.mistral_budget import mistral_usage_cost_usd
s=get_settings();root=Path('/app/data/recovery/20261106-captions');store=RawStore(s.raw_data_dir)
client=MistralTranscriptionClient(s.mistral_api_key,model=s.executive_transcription_model,base_url=s.mistral_base_url,usd_per_minute=s.executive_transcription_usd_per_minute,timeout_seconds=180)
jobs=[('nov5-opening-tail','0e170e67-9235-4c4e-ab46-07545cd2c12c','DMP102243912_01_202611051500.mp4','2026-11-05T15:59:00+09:00',55)]
for name,bid,file,start,duration in jobs:
 origin=datetime.fromisoformat(start);url='https://m.webcast.go.kr/vod/_definst_/FULL/2026/bon/'+file+'/playlist.m3u8';bid=uuid.UUID(bid)
 for offset in range(0,duration,600):
  seconds=min(600,duration-offset);key=hashlib.sha256(f'{bid}:{name}:{offset}'.encode()).hexdigest()[:20];path=root/f'{name}-{offset}.mp3';cache=root/f'{name}-{offset}.response.json'
  with connect(s.database_url) as c:
   if c.execute("SELECT 1 FROM transcript_segments WHERE broadcast_id=%s AND source_segment_id LIKE %s LIMIT 1",(bid,'vod-recovery-'+key+'-%')).fetchone():print(json.dumps({'skipped':name,'offset':offset}),flush=True);continue
   usage=SummaryRepository(c).monthly_provider_usage('mistral')
  cost=mistral_usage_cost_usd(usage,input_usd_per_million=s.mistral_input_usd_per_million,output_usd_per_million=s.mistral_output_usd_per_million)
  if cost+seconds/60*s.executive_transcription_usd_per_minute>s.mistral_monthly_credit_usd:raise RuntimeError('MONTHLY_CREDIT_LIMIT')
  subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(offset),'-i',str(root/(name+'.mp3')),'-t',str(seconds),'-acodec','copy',str(path)],check=True,capture_output=True)
  if path.stat().st_size<512:raise ValueError('empty recovered audio')
  audio=store.save(SourcePayload(source_key='assembly_vod_recovery_audio',content=path.read_bytes(),content_type='audio/mpeg',retrieved_at=datetime.now(timezone.utc),source_url=url,http_status=200),parser_version='vod-gap-recovery/1.0')
  if cache.exists():
   from types import SimpleNamespace
   result=SimpleNamespace(**json.loads(cache.read_text()))
  else:
   result=client.transcribe(audio.content_path,duration_seconds=seconds)
   cache.write_text(json.dumps({'segments':result.segments,'response_payload':result.response_payload,'usage_metadata':result.usage_metadata},ensure_ascii=False))
  raw=store.save(SourcePayload(source_key='assembly_vod_recovery_transcription',content=json.dumps(result.response_payload,ensure_ascii=False).encode(),content_type='application/json',retrieved_at=datetime.now(timezone.utc),source_url=url,http_status=200),parser_version='vod-gap-recovery/1.0')
  source=SourceVersionInput(source_type='assembly_vod_recovery_transcription',source_url=url,content_hash=raw.content_hash,raw_path=raw.content_path,retrieved_at=datetime.now(timezone.utc),parser_version='vod-gap-recovery/1.0',content_type='application/json',metadata={'audio_raw_path':str(audio.content_path),'audio_content_hash':audio.content_hash,'window_start_at':(origin+timedelta(seconds=offset)).isoformat(),'window_duration_seconds':seconds,'provider':'mistral','model':s.executive_transcription_model,'reason':'MISSING_CAPTURE_INTERVAL'})
  inserted=0
  with connect(s.database_url) as c:
   repo=LiveRepository(c)
   for i,seg in enumerate(result.segments):
    if float(seg['start_seconds'])>=seconds:continue
    at=origin+timedelta(seconds=offset+min(seconds,float(seg['end_seconds'])))
    _,created=repo.append_caption_revision(bid,CaptionRevision(source_segment_id=f'vod-recovery-{key}-{i:04d}',text=seg['text'],speaker_label=None,is_final=True,received_at=at,source=source,source_payload={'transcription_source':'OFFICIAL_VOD_AUDIO_RECOVERY','audio_content_hash':audio.content_hash,'response_raw_path':str(raw.content_path),'window_start_at':(origin+timedelta(seconds=offset)).isoformat(),'audio_start_seconds':seg['start_seconds'],'audio_end_seconds':seg['end_seconds'],'source_speaker':seg['speaker']}))
    inserted+=int(created)
   ExecutiveAudioRepository(c).record_usage(provider='mistral',request_id=result.usage_metadata['request_id'],model=s.executive_transcription_model,audio_seconds=seconds,cost_usd=result.usage_metadata['cost_usd'])
  print(json.dumps({'name':name,'offset':offset,'duration':seconds,'inserted':inserted,'cost_usd':result.usage_metadata['cost_usd']}),flush=True)
