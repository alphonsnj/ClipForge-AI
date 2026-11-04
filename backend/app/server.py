"""Production-oriented Uvicorn entry point with explicit proxy trust."""

import ipaddress
import os

import uvicorn

from .configuration import validate_runtime_configuration


def main() -> None:
    validate_runtime_configuration()
    trusted_proxies = [
        value.strip()
        for value in os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",")
        if value.strip()
    ]
    try:
        for value in trusted_proxies:
            ipaddress.ip_network(value, strict=False)
    except ValueError as error:
        raise RuntimeError("TRUSTED_PROXY_IPS must contain comma-separated IP addresses or CIDRs") from error

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=",".join(trusted_proxies),
        access_log=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
