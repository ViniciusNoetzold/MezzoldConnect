from __future__ import annotations

import socket


def has_internet(timeout: float = 3.0) -> bool:
    targets = (("www.whatsapp.com", 443), ("graph.facebook.com", 443))
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False
