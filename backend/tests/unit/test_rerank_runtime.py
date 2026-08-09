from app.config import Settings
from app.rerank import RemoteRerankProvider
from app.runtime import _rerank_provider


def test_runtime_passes_dedicated_timeout_to_remote_rerank() -> None:
    provider = _rerank_provider(
        Settings(
            _env_file=None,
            rerank_provider="remote",
            rerank_api_key="test-key",
            rerank_timeout_seconds=11.25,
        )
    )

    assert isinstance(provider, RemoteRerankProvider)
    assert provider.timeout_seconds == 11.25
