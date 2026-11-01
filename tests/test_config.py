from pathlib import Path

from app.config import Settings


def test_settings_loads_dotenv_without_overriding_environment(monkeypatch, tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AZURE_OPENAI_ENDPOINT=https://example.openai.azure.com/\n"
        "AZURE_OPENAI_API_KEY=secret-value\n"
        "AZURE_OPENAI_DEPLOYMENT=gpt-6.1-sol\n"
        "AI_DEV_TEAM_MAX_CONCURRENCY=2\n",
        encoding="utf-8",
    )
    for key in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT",
                "AI_DEV_TEAM_MAX_CONCURRENCY"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings.from_env(env_file)
    assert settings.azure_openai_endpoint == "https://example.openai.azure.com/"
    assert settings.azure_openai_deployment == "gpt-6.1-sol"
    assert settings.max_concurrency == 2
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "environment-deployment")
    assert Settings.from_env(env_file).azure_openai_deployment == "environment-deployment"
