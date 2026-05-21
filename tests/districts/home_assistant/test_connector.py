import asyncio
import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from districts.home_assistant.connector import HAConfig, HARestClient, HAWebSocketClient, HAConnector


@pytest.fixture
def config():
    return HAConfig(host="192.168.1.100", port=8123, token="test_token_123", use_ssl=False, rate_limit=10)


class TestHAConfig:
    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("HASS_URL", "http://hass.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "env_token")
        cfg = HAConfig()
        assert cfg.host == "hass.local"
        assert cfg.port == 8123
        assert cfg.token == "env_token"

    def test_base_url_http(self):
        cfg = HAConfig(host="hass.local", port=8123, token="t")
        assert cfg.base_url == "http://hass.local:8123"

    def test_base_url_https(self):
        cfg = HAConfig(host="hass.local", port=8123, token="t", use_ssl=True)
        assert cfg.base_url == "https://hass.local:8123"


class TestHARestClient:
    def _make_mock_client(self):
        client = MagicMock()
        client.request = AsyncMock()
        return client

    def _make_mock_resp(self, json_data):
        resp = MagicMock()
        resp.json.return_value = json_data
        return resp

    @pytest.mark.asyncio
    async def test_get_states(self, config):
        mock_resp = self._make_mock_resp([{"entity_id": "light.test", "state": "on"}])
        mock_client = self._make_mock_client()
        mock_client.request.return_value = mock_resp

        client = HARestClient(config)
        client._client = mock_client

        states = await client.get_states()
        assert states == [{"entity_id": "light.test", "state": "on"}]
        mock_client.request.assert_called_once_with("GET", "/api/states")

    @pytest.mark.asyncio
    async def test_get_state(self, config):
        mock_resp = self._make_mock_resp({"entity_id": "light.test", "state": "on"})
        mock_client = self._make_mock_client()
        mock_client.request.return_value = mock_resp

        client = HARestClient(config)
        client._client = mock_client

        result = await client.get_state("light.test")
        assert result["entity_id"] == "light.test"
        mock_client.request.assert_called_once_with("GET", "/api/states/light.test")

    @pytest.mark.asyncio
    async def test_call_service(self, config):
        mock_resp = self._make_mock_resp([{"entity_id": "light.test", "state": "on"}])
        mock_client = self._make_mock_client()
        mock_client.request.return_value = mock_resp

        client = HARestClient(config)
        client._client = mock_client

        await client.call_service("light", "turn_on", {"entity_id": "light.test"})
        mock_client.request.assert_called_once_with("POST", "/api/services/light/turn_on", json={"entity_id": "light.test"})

    @pytest.mark.asyncio
    async def test_rate_limiting(self, config):
        mock_resp = self._make_mock_resp([{"entity_id": "light.test", "state": "on"}])
        mock_client = self._make_mock_client()
        mock_client.request.return_value = mock_resp

        client = HARestClient(config)
        client._client = mock_client

        tasks = [client.get_states() for _ in range(5)]
        await asyncio.gather(*tasks)
        assert mock_client.request.call_count == 5


class TestHAWebSocketClient:
    @pytest.mark.asyncio
    async def test_connect_fails_no_token(self):
        cfg = HAConfig(host="hass.local", port=8123, token="")
        ws = HAWebSocketClient(cfg)
        result = await ws.connect()
        assert result is False


class TestHAConnector:
    @pytest.mark.asyncio
    async def test_health(self, config):
        connector = HAConnector(config)
        with patch.object(connector.rest, "get_config", return_value={"version": "2024.1"}):
            result = await connector.health()
            assert "rest" in result
            assert "ws" in result
