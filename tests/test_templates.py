from pathlib import Path


def test_env_template_documents_required_runtime_keys():
    env_template = Path("/home/tuyentmc/Code/vibe_code/project_4/env/.env.example")

    content = env_template.read_text()

    assert "APP_ENV=dev" in content
    assert "EVENT_BUS_URL=" in content
    assert "POSTGRES_DSN=" in content
    assert "REDIS_URL=" in content
    assert "SECRET_PROVIDER=" in content
    assert "TELEGRAM_BOT_TOKEN_SECRET=" in content


def test_managed_secret_template_maps_secret_refs():
    secret_template = Path("/home/tuyentmc/Code/vibe_code/project_4/env/secrets.example.json")

    content = secret_template.read_text()

    assert '"telegram_bot_token"' in content
    assert '"provider"' in content
    assert '"reference"' in content
