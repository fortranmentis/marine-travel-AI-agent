import pytest


@pytest.fixture(autouse=True)
def offline_transport(monkeypatch, tmp_path):
    """No user credential or provider network access in offline regression tests."""
    monkeypatch.setenv('TRANSPORT_CREDENTIALS_FILE','')
    monkeypatch.setenv('RUNS_DB_PATH',str(tmp_path/'runs.sqlite3'))
    from marine_agent import transport_api
    transport_api._cache.clear()
    yield
    transport_api._cache.clear()
