from __future__ import annotations

import os
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

# iputils-ping reply line (English): time=0.123 ms
# Summary line: rtt min/avg/max/mdev = 0.1/0.2/0.3/0.0 ms
# Stats footer: time 0ms (no '=')
_PING_MS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"time=([\d.,]+)\s*ms", re.IGNORECASE),
    re.compile(
        r"rtt min/avg/max/mdev\s*=\s*[\d.]+\/([\d.]+)\/[\d.]+\/[\d.]+\s*ms",
        re.IGNORECASE,
    ),
    re.compile(r"time\s+(\d+)\s*ms", re.IGNORECASE),
)


def _parse_ping_latency_ms(text: str) -> int | None:
    for pat in _PING_MS_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        raw = m.group(1).replace(",", ".")
        try:
            return int(round(float(raw)))
        except ValueError:
            continue
    return None


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
    # Force C locale so reply lines stay "time=... ms" (gettext can rename the label).
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    env["LC_MESSAGES"] = "C"
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=float(wait_s) + 2.0,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return PingResult(ok=False, latency_ms=None)
    if proc.returncode != 0:
        return PingResult(ok=False, latency_ms=None)
    combined = (proc.stdout or "") + (proc.stderr or "")
    ms = _parse_ping_latency_ms(combined)
    if ms is None:
        # Rare formats / very old ping: approximate RTT from subprocess duration
        wall_ms = int((time.perf_counter() - t0) * 1000)
        ms = max(1, wall_ms) if wall_ms > 0 else 1
    return PingResult(ok=True, latency_ms=ms)
