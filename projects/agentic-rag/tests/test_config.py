import pytest

from app.config import Settings


def test_openai_compatible_provider_requires_models_and_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings(provider="openai_compatible").validate()


def test_demo_provider_needs_no_external_credentials() -> None:
    Settings(provider="demo").validate()
