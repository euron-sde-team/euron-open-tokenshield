"""KMS sealing and S3 exports against Floci. Runs when TEST_AWS_ENDPOINT is set
(make test-matrix provides it, with the local-floci Terraform applied)."""

from __future__ import annotations

import os

import httpx
import pytest

from tests.integration.conftest import Api, World, chat
from tokenshield.core.aws import aws_client
from tokenshield.core.config import Settings
from tokenshield.core.sealing import KmsSealer
from tokenshield.core.storage import S3Storage

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_AWS_ENDPOINT"), reason="needs Floci (make test-matrix)"
    ),
]


def aws_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"aws_endpoint_url": os.environ["TEST_AWS_ENDPOINT"], "s3_force_path_style": True}
    )


async def test_kms_seal_round_trip_with_context(settings: Settings) -> None:
    s = aws_settings(settings)
    sealer = KmsSealer(aws_client(s, "kms"), s.kms_key_id)
    sealed = await sealer.seal("sk-live-secret", "provider:abc")
    assert b"sk-live-secret" not in sealed
    assert await sealer.open(sealed, "provider:abc") == "sk-live-secret"
    with pytest.raises(Exception):  # noqa: B017 botocore raises InvalidCiphertextException
        await sealer.open(sealed, "provider:other")


async def test_s3_storage_put_get_presign(settings: Settings) -> None:
    s = aws_settings(settings)
    storage = S3Storage(aws_client(s, "s3"), s.exports_bucket, aws_client(s, "s3", public=True))
    await storage.put("tests/probe.csv", b"a,b\n1,2\n", "text/csv")
    assert await storage.get("tests/probe.csv") == b"a,b\n1,2\n"
    url = await storage.download_url("tests/probe.csv", "probe.csv")
    assert url is not None
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    assert resp.status_code == 200 and resp.content == b"a,b\n1,2\n"


@pytest.mark.skipif(os.environ.get("TEST_STORAGE") != "s3", reason="matrix run with STORAGE=s3")
async def test_export_lands_in_s3_with_presigned_link(api: Api, world: World) -> None:
    await api.gateway(world.key, chat())
    export = await api.ok("POST", "/api/v1/exports", {"range": "24h"}, status=201)
    link = await api.ok("GET", f"/api/v1/exports/{export['id']}/download")
    assert link["url"].startswith(os.environ["TEST_AWS_ENDPOINT"])
    async with httpx.AsyncClient() as client:
        resp = await client.get(link["url"])
    assert resp.status_code == 200 and "request_id" in resp.text
