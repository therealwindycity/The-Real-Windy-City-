"""The legality gate. Every network fetch in the engine goes through here.

- robots.txt is honored (Disallow + Crawl-delay) for our real, identifying UA.
- per-host minimum delay; honest User-Agent with contact info.
- a refusal raises `Blocked`, which the ingest layer converts into a drafted
  statutory records request — the legal route to the same public records.

There is intentionally no user-agent spoofing, no stealth plugin, no CAPTCHA
solving and no login/paywall handling. See LEGAL.md.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field


class Blocked(Exception):
    """robots.txt (or an explicit 401/403/451) says no."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"{reason}: {url}")
        self.url, self.reason = url, reason


class FetchError(Exception):
    pass


@dataclass
class Response:
    url: str
    status: int
    content_type: str
    body: bytes
    headers: dict = field(default_factory=dict)

    def text(self) -> str:
        charset = "utf-8"
        ct = self.content_type or ""
        if "charset=" in ct:
            charset = ct.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        return self.body.decode(charset, errors="replace")


class Gate:
    def __init__(self, identity: dict, respect_robots: bool = True):
        self.ua = identity.get("user_agent", "WindyCityReaper/1.0")
        self.contact = identity.get("contact", "")
        self.delay = float(identity.get("delay_seconds_per_host", 3))
        self.timeout = float(identity.get("timeout_seconds", 30))
        # respect_robots=False exists ONLY for unit tests against local fixtures.
        self.respect_robots = respect_robots
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last: dict[str, float] = {}

    # ------------------------------------------------------------ robots
    @staticmethod
    def _origin(url: str) -> str:
        p = urllib.parse.urlsplit(url)
        return f"{p.scheme or 'https'}://{p.netloc}"

    def _parser(self, url: str):
        origin = self._origin(url)
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(origin + "/robots.txt", headers=self._headers())
                with urllib.request.urlopen(req, timeout=min(self.timeout, 15)) as r:
                    rp.parse(r.read().decode("utf-8", errors="replace").splitlines())
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    rp.parse(["User-agent: *", "Disallow: /"])  # RFC 9309: treat as full disallow
                else:
                    rp.parse([])  # 404 etc. = no rules
            except Exception:
                rp.parse([])  # unreachable robots: permitted, but we stay slow
            self._robots[origin] = rp
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        try:
            return self._parser(url).can_fetch(self.ua, url)
        except Exception:
            return True

    def _wait(self, url: str):
        origin = self._origin(url)
        delay = self.delay
        rp = self._robots.get(origin)
        if rp is not None:
            try:
                cd = rp.crawl_delay(self.ua)
                if cd:
                    delay = max(delay, float(cd))
            except Exception:
                pass
        gap = time.monotonic() - self._last.get(origin, 0.0)
        if gap < delay:
            time.sleep(delay - gap)
        self._last[origin] = time.monotonic()

    def _headers(self) -> dict:
        h = {"User-Agent": self.ua, "Accept": "*/*"}
        if self.contact:
            h["From"] = self.contact
        return h

    # ------------------------------------------------------------ fetch
    def get(self, url: str, params: dict | None = None, accept: str | None = None) -> Response:
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        if not self.allowed(url):
            raise Blocked(url, "robots.txt disallow")
        self._wait(url)
        headers = self._headers()
        if accept:
            headers["Accept"] = accept
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Response(url=r.geturl(), status=r.status,
                                content_type=r.headers.get("Content-Type", ""),
                                body=r.read(), headers=dict(r.headers))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 451):
                raise Blocked(url, f"HTTP {e.code}") from e
            raise FetchError(f"HTTP {e.code} for {url}") from e
        except Exception as e:  # DNS, TLS, timeout
            raise FetchError(f"{type(e).__name__}: {e} ({url})") from e
