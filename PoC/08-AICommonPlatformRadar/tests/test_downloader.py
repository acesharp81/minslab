from dataclasses import replace

from app.config import get_settings
from app.services import downloader
from app.services.downloader import _filename_from_response, download_attachment


class Response:
    def __init__(self, disposition: str):
        self.headers = {"content-disposition": disposition}


def test_percent_encoded_filename_drops_parameter_separator():
    response = Response("attachment;filename=%EC%A0%9C%EC%95%88%EC%84%9C.hwpx;")
    assert _filename_from_response("https://example.com/download", response) == "제안서.hwpx"


def test_rfc5987_filename_is_decoded():
    response = Response("attachment; filename*=UTF-8''%EC%A0%9C%EC%95%88%EC%84%9C.pdf")
    assert _filename_from_response("https://example.com/download", response) == "제안서.pdf"


def test_xlsx_extension_is_downloaded(monkeypatch):
    class StreamResponse:
        headers = {
            "content-disposition": "attachment; filename=cost.xlsx",
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "content-length": "4",
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_bytes():
            yield b"PK\x03\x04"

    monkeypatch.setattr(downloader.httpx, "stream", lambda *_args, **_kwargs: StreamResponse())
    settings = replace(get_settings(), download_allowed_hosts=("example.com",))
    result = download_attachment("https://example.com/download", settings)
    assert result.status == "downloaded"
    assert result.extension == "xlsx"
    assert result.original_filename == "cost.xlsx"
