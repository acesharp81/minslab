import asyncio
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import app.services.runtime_settings as runtime
import app.services.collector as collector
from app.config import get_settings


def test_pause_persists_and_other_settings_survive(tmp_path, monkeypatch):
    settings=replace(get_settings(),data_dir=tmp_path)
    monkeypatch.setattr(runtime,'get_settings',lambda:settings)
    before=runtime.load_runtime_settings()
    before['notifications']['smtp_username']='retained@example.test'
    runtime.save_runtime_settings(before)
    assert runtime.update_collection_settings(False)['enabled'] is False
    assert (tmp_path/'collection.disabled').is_file()
    assert runtime.collection_enabled(tmp_path) is False
    assert runtime.load_runtime_settings()['notifications']['smtp_username']=='retained@example.test'
    assert runtime.update_collection_settings(True)['enabled'] is True
    assert not (tmp_path/'collection.disabled').exists()


def test_disabled_collector_never_opens_client_or_touches_db(tmp_path, monkeypatch):
    (tmp_path/'collection.disabled').touch()
    monkeypatch.setattr(collector,'get_settings',lambda:replace(get_settings(),data_dir=tmp_path))
    network=Mock(side_effect=AssertionError('must not contact source'))
    monkeypatch.setattr(collector,'G2BClient',network)
    assert asyncio.run(collector.run_collection(None))['status']=='disabled'
    network.assert_not_called()


def test_corrupt_settings_fail_closed(tmp_path):
    (tmp_path/'runtime_settings.json').write_text('{broken')
    assert runtime.collection_enabled(tmp_path) is False


def test_collection_api_requires_settings_authorization_and_strict_bool(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    import app.routers.settings as routes
    settings=replace(get_settings(),data_dir=tmp_path,proxy_token='control-test-token',admin_token='',admin_username='admin',admin_password='secret')
    monkeypatch.setattr(runtime,'get_settings',lambda:settings)
    monkeypatch.setattr(routes,'get_settings',lambda:settings)
    monkeypatch.setattr(main,'settings',settings)
    # Avoid application startup/production DB. A test dependency supplies a fake audit session.
    session=Mock()
    main.app.dependency_overrides[routes.get_db]=lambda:session
    try:
        client=TestClient(main.app)
        assert client.get('/api/settings/collection').status_code==401
        assert client.put('/api/settings/collection',json={'enabled':False}).status_code==401
        headers={'X-PoC08-Proxy-Token':'control-test-token'}
        assert client.put('/api/settings/collection',json={'enabled':'false'},headers=headers).status_code==422
        reply=client.put('/api/settings/collection',json={'enabled':False},headers=headers)
        assert reply.status_code==200 and reply.json()['enabled'] is False
        assert client.get('/api/settings/collection',headers=headers).json()['enabled'] is False
        assert session.commit.called
        assert client.post('/api/collect/run',headers=headers).status_code==409
    finally:main.app.dependency_overrides.clear()
