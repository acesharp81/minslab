"""Compress history JSON without recompressing original PNG/PDF evidence."""
import re
from starlette.middleware.gzip import GZipMiddleware


class HistoryCompressionMiddleware(GZipMiddleware):
    async def __call__(self, scope, receive, send):
        path=scope.get('path','')
        if scope['type']=='http' and re.fullmatch(
            r'(?:/poc/image-inspection)?/api/jobs(?:/[^/]+(?:/(?:versions|report)|/runs/[^/]+/details)?)?',path
        ):
            await super().__call__(scope,receive,send)
        else:
            await self.app(scope,receive,send)
