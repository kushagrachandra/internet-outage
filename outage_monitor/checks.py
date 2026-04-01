from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass

import dns.exception
import dns.resolver

DNS_QUERY_NAME = "google.com"

# (label, resolver IP) — Google, Cloudflare, OpenDNS
DNS_RESOLVERS: tuple[tuple[str, str], ...] = (
    ("google", "8.8.8.8"),
    ("cloudflare", "1.1.1.1"),
    ("opendns", "208.67.222.222"),
)

LAN_PING_HOSTS: tuple[str, ...] = ("192.168.1.1", "192.168.0.1")

_PING_TIME_RE = re.compile(r"time=([\d.]+)\s*ms", re.IGNORECASE)


@dataclass(frozen=True)
class DnsResult:
    ok: bool
    latency_ms: int | None


@dataclass(frozen=True)
class PingResult:
    ok: bool
    latency_ms: int | None


def check_dns_via_resolver(resolver_ip: str, timeout_s: float = 2.0) -> DnsResult:
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [resolver_ip]
    resolver.port = 53
    resolver.timeout = timeout_s
    resolver.lifetime = timeout_s + 1.0
    t0 = time.perf_counter()
    try:
        resolver.resolve(DNS_QUERY_NAME, "A")
    except (
        dns.exception.DNSException,
        OSError,
        TimeoutError,
    ):
        return DnsResult(ok=False, latency_ms=None)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return DnsResult(ok=True, latency_ms=elapsed_ms)


def ping_host(host: str, wait_s: int = 2) -> PingResult:
    # Ubuntu iputils-ping: -c 1, -W wait seconds for reply
    cmd = ["ping", "-c", "1", "-W", str(wait_s), host]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=float(wait_s) + 2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return PingResult(ok=False, latency_ms=None)
    if proc.returncode != 0:
        return PingResult(ok=False, latency_ms=None)
    combined = (proc.stdout or "") + (proc.stderr or "")
    m = _PING_TIME_RE.search(combined)
    if not m:
        return PingResult(ok=True, latency_ms=None)
    try:
        ms = int(round(float(m.group(1))))
    except ValueError:
        return PingResult(ok=True, latency_ms=None)
    return PingResult(ok=True, latency_ms=ms)
