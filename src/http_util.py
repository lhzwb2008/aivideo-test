"""HTTP 下载：优先直连，失败再试代理（避免代理未开时 Connection refused）。"""

from __future__ import annotations

import os
import urllib.error
import urllib.request


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def proxy_url() -> str:
    return (
        _env("STOCK_HTTP_PROXY")
        or _env("PIXABAY_HTTP_PROXY")
        or _env("PEXELS_HTTP_PROXY")
        or _env("HTTPS_PROXY")
        or _env("https_proxy")
        or _env("YOUTUBE_HTTP_PROXY")
    )


def _direct_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open(req: urllib.request.Request, *, timeout: float, use_proxy: bool) -> bytes:
    if use_proxy:
        proxy = proxy_url()
        if not proxy:
            raise urllib.error.URLError("no proxy configured")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        opener = _direct_opener()
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 120,
    referer: str = "",
) -> bytes:
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) aivideo-test/1.0",
        "Accept": "*/*",
    }
    if referer:
        hdrs["Referer"] = referer
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        return _open(req, timeout=timeout, use_proxy=False)
    except (urllib.error.URLError, TimeoutError, OSError):
        if proxy_url():
            return _open(req, timeout=timeout, use_proxy=True)
        raise
