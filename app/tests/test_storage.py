from __future__ import annotations

import pytest

from app.core import storage
from app.core.config import settings


def test_bucket_name_requires_setting(monkeypatch):
    monkeypatch.setattr(storage, "_s3", None)
    monkeypatch.setattr(settings, "S3_BUCKET", None, raising=False)
    with pytest.raises(RuntimeError):
        storage.bucket_name()

    monkeypatch.setattr(settings, "S3_BUCKET", "demo-bucket", raising=False)
    assert storage.bucket_name() == "demo-bucket"


def test_s3_client_uses_optional_settings(monkeypatch):
    created_kwargs: dict[str, str] = {}

    class DummyClient:
        pass

    def fake_client(service: str, **kwargs):
        assert service == "s3"
        created_kwargs.update(kwargs)
        return DummyClient()

    monkeypatch.setattr(storage, "_s3", None)
    monkeypatch.setattr("app.core.storage.boto3.client", fake_client)
    monkeypatch.setattr(settings, "AWS_REGION", "us-test-1", raising=False)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "abc", raising=False)
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "xyz", raising=False)
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "http://localhost:9000", raising=False)

    client = storage.s3()
    assert isinstance(client, DummyClient)
    assert created_kwargs["region_name"] == "us-test-1"
    assert created_kwargs["aws_access_key_id"] == "abc"
    assert created_kwargs["aws_secret_access_key"] == "xyz"
    assert created_kwargs["endpoint_url"] == "http://localhost:9000"
