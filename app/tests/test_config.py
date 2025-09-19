from app.core.config import settings


def test_config_defaults():
    assert settings.APP_NAME == "DAWN"
    assert isinstance(settings.REDIS_URL, str)
