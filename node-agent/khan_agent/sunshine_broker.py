from __future__ import annotations

import time
from typing import Any

import httpx


class SunshineBrokerError(RuntimeError):
    pass


def _normalize_clients(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                found.append(item)
        return found

    if isinstance(payload, dict):
        for key in ("clients", "named_certs", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        found.append(item)
        if not found and any(
            key in payload
            for key in ("uuid", "name", "clientName")
        ):
            found.append(payload)

    return found


def _auth(
    *,
    username: str,
    password: str,
) -> tuple[str, str]:
    if not username or not password:
        raise SunshineBrokerError(
            "Sunshine API credentials are not configured "
            "on this gaming node."
        )
    return username, password


def pair_client(
    *,
    pin: str,
    client_name: str,
    api_url: str,
    username: str,
    password: str,
    verify_tls: bool,
) -> dict[str, Any]:
    if len(pin) != 4 or not pin.isdigit():
        raise SunshineBrokerError(
            "Moonlight pairing PIN must contain exactly four digits."
        )

    if not client_name or len(client_name) > 100:
        raise SunshineBrokerError(
            "Invalid Sunshine client name."
        )

    with httpx.Client(
        base_url=api_url.rstrip("/"),
        auth=_auth(
            username=username,
            password=password,
        ),
        verify=verify_tls,
        timeout=10.0,
    ) as client:
        response = client.post(
            "/api/pin",
            json={
                "pin": pin,
                "name": client_name,
            },
        )

        if response.is_error:
            raise SunshineBrokerError(
                "Sunshine rejected the Moonlight pairing request."
            )

        # Pairing is expected to materialize immediately, but tolerate
        # a short delay before Sunshine exposes the client record.
        for _ in range(10):
            listed = client.get("/api/clients/list")

            if not listed.is_error:
                try:
                    records = _normalize_clients(
                        listed.json()
                    )
                except ValueError:
                    records = []

                for record in records:
                    name = str(
                        record.get("name")
                        or record.get("clientName")
                        or ""
                    )
                    client_uuid = str(
                        record.get("uuid")
                        or record.get("id")
                        or ""
                    )

                    if (
                        name == client_name
                        and client_uuid
                    ):
                        return {
                            "sunshine_client_uuid":
                                client_uuid,
                            "client_name": client_name,
                            "paired": True,
                        }

            time.sleep(0.25)

    raise SunshineBrokerError(
        "Sunshine accepted the PIN but the paired client "
        "identity could not be verified."
    )


def unpair_client(
    *,
    client_uuid: str,
    api_url: str,
    username: str,
    password: str,
    verify_tls: bool,
) -> dict[str, Any]:
    if not client_uuid:
        raise SunshineBrokerError(
            "Sunshine client UUID is required for revocation."
        )

    with httpx.Client(
        base_url=api_url.rstrip("/"),
        auth=_auth(
            username=username,
            password=password,
        ),
        verify=verify_tls,
        timeout=10.0,
    ) as client:
        response = client.post(
            "/api/clients/unpair",
            json={"uuid": client_uuid},
        )

        # Compatibility with older Sunshine builds.
        if response.status_code == 404:
            response = client.post(
                "/api/unpair",
                json={"uuid": client_uuid},
            )

        if response.is_error:
            raise SunshineBrokerError(
                "Sunshine failed to revoke the paired client."
            )

    return {
        "sunshine_client_uuid": client_uuid,
        "revoked": True,
    }
