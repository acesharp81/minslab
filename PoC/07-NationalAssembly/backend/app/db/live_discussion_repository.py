from __future__ import annotations
from typing import Any
from uuid import uuid4
from psycopg.types.json import Jsonb
from ..services.live_discussion_classification import PROFILE, digest, project_classification


class LiveDiscussionRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def latest(self, broadcast_id: Any) -> dict[str, Any]:
        row=self.connection.execute('SELECT state FROM live_discussion_classifications WHERE broadcast_id=%s AND profile=%s ORDER BY created_at DESC LIMIT 1',(broadcast_id,PROFILE)).fetchone()
        return row[0] if row else {'groups':{},'assignments':{}}

    def save(self, broadcast_id: Any, state: dict[str, Any], request: dict[str, Any], response: dict[str, Any], client: Any, metadata: dict[str, Any]) -> None:
        self.connection.execute('INSERT INTO live_discussion_classifications (id,broadcast_id,profile,input_hash,state,request_snapshot,response,provider,model,usage_metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
            (uuid4(),broadcast_id,PROFILE,digest(request),Jsonb(state),Jsonb(request),Jsonb(response),client.provider,client.model,Jsonb(metadata)))

    def attach(self, turns: list[dict[str, Any]]) -> None:
        for bid in {u.get('broadcast_id') for u in turns if u.get('broadcast_id')}:
            project_classification([u for u in turns if u.get('broadcast_id')==bid],self.latest(bid))
