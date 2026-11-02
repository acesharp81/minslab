"""Public-share helpers accept HTTP without exposing credential query errors."""
import importlib.util
from pathlib import Path

import pytest
import requests


def load_script(name):
    path = Path(__file__).resolve().parents[1] / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_architecture_fetch_rejects_local_file_scheme(tmp_path):
    module = load_script('generate_architecture_html')
    file = tmp_path / 'private.json'
    file.write_text('{"private": true}')
    with pytest.raises(requests.exceptions.InvalidSchema):
        module.fetch(tmp_path.as_uri(), file.name)


def test_architecture_fetch_checks_response_status(monkeypatch):
    module = load_script('generate_architecture_html')

    class FailedResponse:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): raise requests.HTTPError('upstream unavailable')
        def json(self): pytest.fail('must not accept an HTTP error as snapshot data')

    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: FailedResponse())
    with pytest.raises(requests.HTTPError):
        module.fetch('https://example.com/api', 'sources')


def test_official_statistics_request_does_not_expose_key_in_error(monkeypatch):
    module = load_script('export_policy907_verification_20261021')
    monkeypatch.setenv('POC10_MOLIT_STAT_API_KEY', 'example')

    def failed_get(url, *, params, timeout):
        assert url.startswith('https://stat.molit.go.kr/')
        assert params['key'] == 'example'
        assert timeout == 30
        raise requests.HTTPError('https://stat.molit.go.kr/?key=example')

    monkeypatch.setattr(requests, 'get', failed_get)
    with pytest.raises(RuntimeError) as caught:
        module.type_months()
    assert 'HTTPError' in str(caught.value)
    assert 'example' not in str(caught.value)
    assert caught.value.__suppress_context__
