from affiliate_agent.secrets import SecretStore


def test_env_secret_store_returns_seeded_secret_values():
    store = SecretStore("env", {"projects/demo/secrets/telegram-token": "telegram-secret"})

    assert store.read("projects/demo/secrets/telegram-token") == "telegram-secret"


def test_managed_secret_store_returns_provider_reference_stub():
    store = SecretStore("gcp-secret-manager")

    assert (
        store.read("projects/demo/secrets/telegram-token")
        == "gcp-secret-manager://projects/demo/secrets/telegram-token"
    )
