"""HMAC signature generation and verification for webhooks."""

import hashlib
import hmac
import time
from typing import Literal


SIGNATURE_VERSION = "v1"
TIMESTAMP_TOLERANCE_SECONDS = 300  # 5 minutes


def generate_signature(
    payload: str | bytes,
    secret: str,
    timestamp: int | None = None,
    algorithm: Literal["sha256", "sha512"] = "sha256",
) -> tuple[str, int]:
    """
    Generate HMAC signature for webhook payload.

    Returns:
        Tuple of (signature_header, timestamp)
    """
    if timestamp is None:
        timestamp = int(time.time())

    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    # Create signed payload: timestamp.payload
    signed_payload = f"{timestamp}.".encode("utf-8") + payload

    # Generate HMAC
    hash_func = hashlib.sha256 if algorithm == "sha256" else hashlib.sha512
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hash_func).hexdigest()

    # Format: v1,t=timestamp,s=signature
    header = f"{SIGNATURE_VERSION},t={timestamp},s={signature}"
    return header, timestamp


def verify_signature(
    payload: str | bytes,
    signature_header: str,
    secret: str,
    algorithm: Literal["sha256", "sha512"] = "sha256",
    tolerance_seconds: int = TIMESTAMP_TOLERANCE_SECONDS,
) -> tuple[bool, str | None]:
    """
    Verify HMAC signature from webhook payload.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Parse header
        parts = signature_header.split(",")
        if len(parts) != 3:
            return False, "Invalid signature format"

        version = parts[0]
        if version != SIGNATURE_VERSION:
            return False, f"Unsupported signature version: {version}"

        timestamp_part = parts[1]
        sig_part = parts[2]

        if not timestamp_part.startswith("t=") or not sig_part.startswith("s="):
            return False, "Invalid signature format"

        timestamp = int(timestamp_part[2:])
        provided_signature = sig_part[2:]

        # Check timestamp tolerance
        current_time = int(time.time())
        if abs(current_time - timestamp) > tolerance_seconds:
            return False, "Signature timestamp expired"

        # Generate expected signature
        expected_header, _ = generate_signature(payload, secret, timestamp, algorithm)
        expected_signature = expected_header.split(",s=")[1]

        # Constant-time comparison
        if hmac.compare_digest(provided_signature, expected_signature):
            return True, None
        return False, "Signature mismatch"

    except (ValueError, IndexError) as e:
        return False, f"Signature parsing error: {e}"


def generate_signing_secret(length: int = 32) -> str:
    """Generate a cryptographically secure signing secret."""
    import secrets

    return f"whsec_{secrets.token_hex(length)}"
