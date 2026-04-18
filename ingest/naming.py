from __future__ import annotations

import secrets

from .device_info import size_bucket


BRAND_PREFIX = "Humyn_SSD"


def generate_assigned_name(total_bytes: int) -> str:
    size = size_bucket(total_bytes)
    unique = secrets.token_hex(3).upper()
    return f"{BRAND_PREFIX}_{size}_{unique}"
