from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mnemo.config import EmbeddingConfig
from mnemo.embeddings.ollama import OllamaEmbedder


@pytest.fixture
def mock_config():
    return EmbeddingConfig(
        provider="ollama",
        model="nomic-embed-text",
        dimensions=768,
        api_base="http://127.0.0.1:11434"
    )


@pytest.fixture
def embedder(mock_config):
    embedder = OllamaEmbedder(config=mock_config)
    # Bypass initialize() for most tests that don't test startup lifecycle
    embedder._discovered_dimensions = mock_config.dimensions
    return embedder


@pytest.mark.anyio
async def test_embed_success(embedder, mock_config):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1] * mock_config.dimensions}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        vector = await embedder.embed("Hello world")

        assert len(vector) == mock_config.dimensions
        assert vector[0] == 0.1
        mock_post.assert_called_once()





@pytest.mark.anyio
async def test_embed_malformed_response(embedder):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "no embedding here"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="Malformed response"):
            await embedder.embed("Hello world")


@pytest.mark.anyio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_embed_retry_transient_error(mock_sleep, embedder, mock_config):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"embedding": [0.2] * mock_config.dimensions}
        mock_response_success.raise_for_status = MagicMock()

        # Fail twice with ConnectError, then succeed
        mock_post.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.ConnectError("Connection refused"),
            mock_response_success
        ]

        vector = await embedder.embed("Hello world")
        
        assert len(vector) == mock_config.dimensions
        assert vector[0] == 0.2
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.anyio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_embed_retry_exhausted(mock_sleep, embedder, mock_config):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(RuntimeError, match="Ollama connection error"):
            await embedder.embed("Hello world")
            
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.anyio
async def test_embed_deterministic_error(embedder):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "model not found"
        
        error = httpx.HTTPStatusError(
            "404 Client Error", request=MagicMock(), response=mock_response
        )
        mock_post.side_effect = error

        with pytest.raises(ValueError, match="Ollama provider error 404"):
            await embedder.embed("Hello world")
            
        # Should not retry deterministic errors
        assert mock_post.call_count == 1


@pytest.mark.anyio
async def test_embed_batch_success(embedder, mock_config):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.5] * mock_config.dimensions}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        texts = ("text1", "text2", "text3")
        batch = await embedder.embed_batch(texts)

        assert batch.model_name == mock_config.model
        assert batch.dimensions == mock_config.dimensions
        assert len(batch.vectors) == 3
        assert mock_post.call_count == 3


@pytest.mark.anyio
async def test_health_check_success(embedder, mock_config):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": [{"name": mock_config.model}]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        status = await embedder.health_check()
        assert status.healthy is True
        assert status.component == "OllamaEmbedder"


@pytest.mark.anyio
async def test_health_check_model_not_found(embedder, mock_config):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": [{"name": "different-model:latest"}]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        status = await embedder.health_check()
        assert status.healthy is False
        assert "not found" in status.detail


@pytest.mark.anyio
async def test_health_check_server_error(embedder):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Server down")

        status = await embedder.health_check()
        assert status.healthy is False
        assert "Server down" in status.detail


@pytest.mark.anyio
async def test_initialize_success(mock_config):
    embedder = OllamaEmbedder(config=mock_config)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:

        # Health check success
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"models": [{"name": mock_config.model}]}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        # Probe success
        mock_post_response = MagicMock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {"embedding": [0.1] * mock_config.dimensions}
        mock_post_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_post_response

        await embedder.initialize()
        assert embedder.dimensions == mock_config.dimensions


@pytest.mark.anyio
async def test_initialize_dimension_mismatch(mock_config):
    embedder = OllamaEmbedder(config=mock_config)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:

        # Health check success
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"models": [{"name": mock_config.model}]}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        # Probe success but wrong dimensions
        mock_post_response = MagicMock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {"embedding": [0.1] * (mock_config.dimensions - 1)}
        mock_post_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_post_response

        with pytest.raises(ValueError, match="Dimension mismatch"):
            await embedder.initialize()


@pytest.mark.anyio
async def test_initialize_health_failure(mock_config):
    embedder = OllamaEmbedder(config=mock_config)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"models": [{"name": "different-model"}]}
        mock_get_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_get_response

        with pytest.raises(RuntimeError, match="Ollama initialization failed"):
            await embedder.initialize()
