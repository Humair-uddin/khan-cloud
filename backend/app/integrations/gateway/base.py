from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GatewayNatRule:
    mapping_id: UUID
    public_ip: str
    protocol: str
    public_port: int
    private_ip: str
    private_port: int

    @property
    def ownership_tag(self) -> str:
        return f"khan-cloud:port-mapping:{self.mapping_id}"


@dataclass(frozen=True, slots=True)
class GatewayApplyResult:
    changed: bool
    external_id: str | None = None
    message: str = ""


class GatewayAdapter(Protocol):
    def ensure_port_mapping(
        self,
        rule: GatewayNatRule,
    ) -> GatewayApplyResult:
        ...

    def remove_port_mapping(
        self,
        rule: GatewayNatRule,
    ) -> GatewayApplyResult:
        ...
