import pytest


@pytest.fixture(autouse=True)
def offline_transport(monkeypatch):
    """No user credential or provider network access in offline regression tests."""
    monkeypatch.setenv('TRANSPORT_CREDENTIALS_FILE','')
    from marine_agent import transport_api
    transport_api._cache.clear()
    yield
    transport_api._cache.clear()
