from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WebhookOutcomeCode(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    INVALID_SIGNATURE = "invalid_signature"
    STALE = "stale"
    MALFORMED = "malformed"
    PROVIDER_DISABLED = "provider_disabled"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    UNSUPPORTED_CURRENCY = "unsupported_currency"
    CONTENT_CONFLICT = "content_conflict"
    DOMAIN_REJECTED = "domain_rejected"
    RETRYABLE_FAILURE = "retryable_failure"
    INTERNAL_FAILURE = "internal_failure"


@dataclass(frozen=True)
class WebhookHttpOutcome:
    code: WebhookOutcomeCode
    http_status: int
    retryable: bool
    accepted: bool


_OUTCOMES = {
    WebhookOutcomeCode.ACCEPTED:
        WebhookHttpOutcome(
            WebhookOutcomeCode.ACCEPTED,
            200,
            False,
            True,
        ),

    WebhookOutcomeCode.DUPLICATE:
        WebhookHttpOutcome(
            WebhookOutcomeCode.DUPLICATE,
            200,
            False,
            True,
        ),

    WebhookOutcomeCode.INVALID_SIGNATURE:
        WebhookHttpOutcome(
            WebhookOutcomeCode.INVALID_SIGNATURE,
            401,
            False,
            False,
        ),

    WebhookOutcomeCode.STALE:
        WebhookHttpOutcome(
            WebhookOutcomeCode.STALE,
            400,
            False,
            False,
        ),

    WebhookOutcomeCode.MALFORMED:
        WebhookHttpOutcome(
            WebhookOutcomeCode.MALFORMED,
            400,
            False,
            False,
        ),

    WebhookOutcomeCode.PROVIDER_DISABLED:
        WebhookHttpOutcome(
            WebhookOutcomeCode.PROVIDER_DISABLED,
            409,
            False,
            False,
        ),

    WebhookOutcomeCode.UNSUPPORTED_CAPABILITY:
        WebhookHttpOutcome(
            WebhookOutcomeCode.UNSUPPORTED_CAPABILITY,
            422,
            False,
            False,
        ),

    WebhookOutcomeCode.UNSUPPORTED_CURRENCY:
        WebhookHttpOutcome(
            WebhookOutcomeCode.UNSUPPORTED_CURRENCY,
            422,
            False,
            False,
        ),

    WebhookOutcomeCode.CONTENT_CONFLICT:
        WebhookHttpOutcome(
            WebhookOutcomeCode.CONTENT_CONFLICT,
            409,
            False,
            False,
        ),

    WebhookOutcomeCode.DOMAIN_REJECTED:
        WebhookHttpOutcome(
            WebhookOutcomeCode.DOMAIN_REJECTED,
            422,
            False,
            False,
        ),

    WebhookOutcomeCode.RETRYABLE_FAILURE:
        WebhookHttpOutcome(
            WebhookOutcomeCode.RETRYABLE_FAILURE,
            503,
            True,
            False,
        ),

    WebhookOutcomeCode.INTERNAL_FAILURE:
        WebhookHttpOutcome(
            WebhookOutcomeCode.INTERNAL_FAILURE,
            500,
            True,
            False,
        ),
}


def webhook_http_outcome(
    code: WebhookOutcomeCode,
) -> WebhookHttpOutcome:
    return _OUTCOMES[code]
