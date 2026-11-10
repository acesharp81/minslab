"""Revalidate immutable evidence bytes without bypassing route authentication."""
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response


def revalidated_file(path, request, *, private=True, media_type=None):
    # The caller must authenticate and check access before entering this helper.
    try:
        stat = path.stat()
    except FileNotFoundError:
        raise HTTPException(404, '파일을 찾을 수 없습니다.')
    headers = {'Cache-Control': ('private, ' if private else 'public, ') + 'no-cache'}
    if private:
        headers['Vary'] = 'Cookie, X-Inspection-Admin'
    response = FileResponse(path, stat_result=stat, media_type=media_type, headers=headers)
    # Weak validation is appropriate for GET (including gzip content negotiation).
    etag = response.headers['etag']
    response.headers['etag'] = 'W/' + etag
    supplied = request.headers.get('if-none-match', '')
    if any(tag.strip().removeprefix('W/') in (etag, '*') for tag in supplied.split(',')):
        return Response(status_code=304, headers={key: response.headers[key] for key in
                        ('cache-control', 'etag', 'last-modified', 'vary') if key in response.headers})
    return response
