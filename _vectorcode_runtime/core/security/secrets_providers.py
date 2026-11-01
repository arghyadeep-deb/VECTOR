"""Pluggable secret provider backends for VECTOR.

Extends secrets_manager.py with optional Vault and AWS Secrets Manager providers.
Each provider implements the SecretProvider protocol.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger


@dataclass
class SecretValue:
    value: str
    source: str
    metadata: dict[str, Any] | None = None


class SecretProvider(Protocol):
    name: str

    def get(self, name: str) -> SecretValue | None:
        ...

    def set(self, name: str, value: str) -> bool:
        ...

    def list(self) -> list[str]:
        ...

    def health(self) -> bool:
        ...


class EnvProvider:
    name = "env"

    def get(self, name: str) -> SecretValue | None:
        val = os.environ.get(name, "").strip()
        if val:
            return SecretValue(value=val, source="env")
        return None

    def set(self, name: str, value: str) -> bool:
        os.environ[name] = value
        return True

    def list(self) -> list[str]:
        return [k for k in os.environ if any(s in k.upper() for s in ("KEY", "SECRET", "TOKEN", "PASS"))]

    def health(self) -> bool:
        return True


class KeyringProvider:
    name = "keyring"

    def __init__(self, service: str = "VECTOR"):
        self._service = service

    def get(self, name: str) -> SecretValue | None:
        try:
            import keyring as _kr
            val = (_kr.get_password(self._service, name) or "").strip()
            if val:
                return SecretValue(value=val, source="keyring")
        except Exception as exc:
            logger.debug("[VECTOR][secrets] keyring get failed for {}: {}", name, exc)
        return None

    def set(self, name: str, value: str) -> bool:
        try:
            import keyring as _kr
            _kr.set_password(self._service, name, value)
            return True
        except Exception as exc:
            logger.debug("[VECTOR][secrets] keyring set failed for {}: {}", name, exc)
            return False

    def list(self) -> list[str]:
        return []  # keyring has no standard list API

    def health(self) -> bool:
        try:
            import keyring as _kr
            _kr.get_password(self._service, "probe")
            return True
        except Exception as exc:
            logger.debug("[VECTOR][secrets] keyring health check failed: {}", exc)
            return False


try:
    import hvac


    class VaultProvider:
        name = "vault"

        def __init__(self, url: str | None = None, token: str | None = None,
                     mount_point: str = "secret", path_prefix: str = "vector/"):
            self._url = url or os.environ.get("VAULT_ADDR", "")
            self._token = token or os.environ.get("VAULT_TOKEN", "")
            self._mount_point = mount_point
            self._path_prefix = path_prefix.strip("/")
            self._client: hvac.Client | None = None

        def _connect(self) -> hvac.Client | None:
            if not self._url or not self._token:
                return None
            if self._client is not None:
                return self._client
            try:
                c = hvac.Client(url=self._url, token=self._token)
                if c.is_authenticated():
                    self._client = c
                    return c
            except Exception as exc:
                logger.debug("[VECTOR][secrets] vault connection failed: {}", exc)
            return None

        def get(self, name: str) -> SecretValue | None:
            client = self._connect()
            if client is None:
                return None
            try:
                path = f"{self._path_prefix}/{name}"
                resp = client.secrets.kv.v2.read_secret_version(
                    path=path, mount_point=self._mount_point,
                )
                data = resp.get("data", {}).get("data", {})
                val = data.get("value") or data.get(name) or ""
                if val:
                    return SecretValue(value=str(val), source="vault",
                                       metadata={"path": path})
            except Exception as exc:
                logger.debug("[VECTOR][secrets] vault get failed for {}: {}", name, exc)
            return None

        def set(self, name: str, value: str) -> bool:
            client = self._connect()
            if client is None:
                return False
            try:
                path = f"{self._path_prefix}/{name}"
                client.secrets.kv.v2.create_or_update_secret(
                    path=path, secret={"value": value, name: value},
                    mount_point=self._mount_point,
                )
                return True
            except Exception as exc:
                logger.debug("[VECTOR][secrets] vault set failed for {}: {}", name, exc)
                return False

        def list(self) -> list[str]:
            client = self._connect()
            if client is None:
                return []
            try:
                resp = client.secrets.kv.v2.list_secrets(
                    path=self._path_prefix, mount_point=self._mount_point,
                )
                keys = resp.get("data", {}).get("keys", [])
                return [k.rstrip("/") for k in keys]
            except Exception as exc:
                logger.debug("[VECTOR][secrets] vault list failed: {}", exc)
                return []

        def health(self) -> bool:
            return self._connect() is not None


except ImportError:
    VaultProvider = None  # type: ignore


try:
    import boto3
    from botocore.exceptions import ClientError


    class AWSSecretsManagerProvider:
        name = "aws"

        def __init__(self, region: str | None = None,
                     prefix: str = "vector/"):
            self._region = region or os.environ.get("AWS_REGION", "us-east-1")
            self._prefix = prefix.rstrip("/")
            self._client = None

        def _connect(self):
            if self._client is not None:
                return self._client
            try:
                self._client = boto3.client(
                    "secretsmanager", region_name=self._region,
                )
                return self._client
            except Exception as exc:
                logger.debug("[VECTOR][secrets] aws client creation failed: {}", exc)
                return None

        def get(self, name: str) -> SecretValue | None:
            client = self._connect()
            if client is None:
                return None
            try:
                resp = client.get_secret_value(SecretId=f"{self._prefix}/{name}")
                val = resp.get("SecretString", "")
                if val:
                    return SecretValue(value=val, source="aws",
                                       metadata={"version": resp.get("VersionId")})
            except ClientError as exc:
                logger.debug("[VECTOR][secrets] aws get failed for {}: {}", name, exc)
            return None

        def set(self, name: str, value: str) -> bool:
            client = self._connect()
            if client is None:
                return False
            try:
                client.create_secret(
                    Name=f"{self._prefix}/{name}",
                    SecretString=value,
                )
                return True
            except ClientError:
                try:
                    client.put_secret_value(
                        SecretId=f"{self._prefix}/{name}",
                        SecretString=value,
                    )
                    return True
                except Exception as exc:
                    logger.debug("[VECTOR][secrets] aws put failed for {}: {}", name, exc)
                    return False
            except Exception as exc:
                logger.debug("[VECTOR][secrets] aws create failed for {}: {}", name, exc)
                return False

        def list(self) -> list[str]:
            client = self._connect()
            if client is None:
                return []
            try:
                names = []
                paginator = client.get_paginator("list_secrets")
                for page in paginator.paginate(Filters=[{"Key": "name", "Values": [self._prefix]}], MaxResults=100):
                    for secret in page.get("SecretList", []):
                        name = secret.get("Name", "")
                        if name.startswith(self._prefix):
                            names.append(name[len(self._prefix) + 1:])
                return names
            except Exception as exc:
                logger.debug("[VECTOR][secrets] aws list failed: {}", exc)
                return []

        def health(self) -> bool:
            return self._connect() is not None


except ImportError:
    AWSSecretsManagerProvider = None  # type: ignore


_providers: dict[str, SecretProvider] = {}


def get_provider(name: str = "env") -> SecretProvider | None:
    if name in _providers:
        return _providers[name]
    provider: SecretProvider | None = None
    if name == "env":
        provider = EnvProvider()
    elif name == "keyring":
        provider = KeyringProvider()
    elif name == "vault" and VaultProvider is not None:
        provider = VaultProvider()
    elif name == "aws" and AWSSecretsManagerProvider is not None:
        provider = AWSSecretsManagerProvider()
    if provider is not None:
        _providers[name] = provider
    return provider


def resolve_secret(name: str, providers: list[str] | None = None) -> SecretValue | None:
    chain = providers or ["env", "keyring", "vault", "aws"]
    for pname in chain:
        provider = get_provider(pname)
        if provider is not None and provider.health():
            val = provider.get(name)
            if val is not None:
                return val
    return None


def available_providers() -> list[str]:
    result = ["env", "keyring"]
    if VaultProvider is not None:
        result.append("vault")
    if AWSSecretsManagerProvider is not None:
        result.append("aws")
    return result


if __name__ == "__main__":
    print(f"Available providers: {available_providers()}")
    for name in available_providers():
        p = get_provider(name)
        if p:
            print(f"  {p.name}: health={p.health()}")
    print("OK secrets_providers.py")
