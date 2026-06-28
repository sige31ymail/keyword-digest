"""標準ライブラリのみの薄い HTTP ヘルパー（PocketDigest の軽量方針に倣う）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def _send_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    method: str,
    timeout: int,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # 4xx/5xx
        body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(exc.code, body) from exc


def post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout: int = 120,
) -> dict:
    return _send_json(url, payload, headers, "POST", timeout)


def patch_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout: int = 60,
) -> dict:
    return _send_json(url, payload, headers, "PATCH", timeout)


def get_json(url: str, headers: dict[str, str], timeout: int = 60):
    req = urllib.request.Request(url, method="GET")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(exc.code, body) from exc
