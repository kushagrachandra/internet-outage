from __future__ import annotations

import logging
import signal
import time
from datetime import datetime

import pymysql.connections

from outage_monitor.checks import (
    DNS_RESOLVERS,
    check_dns_via_resolver,
    ping_host,
)
from outage_monitor.config import MySQLConfig, load_mysql_config
from outage_monitor.db import (
    apply_outage_edges,
    close_open_outages_at_restart,
    connect,
    insert_connectivity_sample,
    persist_with_retry,
)

INTERVAL_SEC = 15

logger = logging.getLogger(__name__)


def _local_naive() -> datetime:
    """System local timezone wall time as naive datetime for MySQL DATETIME columns."""
    return datetime.now().astimezone().replace(tzinfo=None)
_shutdown = False


def _handle_signal(signum: int, _frame: object | None) -> None:
    global _shutdown
    _shutdown = True
    logger.info("Received signal %s, shutting down after current cycle", signum)


def run_once(
    conn: pymysql.connections.Connection,
    cfg: MySQLConfig,
    *,
    prev_internet_ok: bool | None,
    checked_at: datetime,
) -> tuple[bool, pymysql.connections.Connection]:
    dns_google = check_dns_via_resolver(DNS_RESOLVERS[0][1])
    dns_cloudflare = check_dns_via_resolver(DNS_RESOLVERS[1][1])
    dns_opendns = check_dns_via_resolver(DNS_RESOLVERS[2][1])

    ping_1 = ping_host("192.168.1.1")
    ping_0 = ping_host("192.168.0.1")

    internet_ok = dns_google.ok or dns_cloudflare.ok or dns_opendns.ok

    def _persist(c: pymysql.connections.Connection) -> None:
        insert_connectivity_sample(
            c,
            checked_at=checked_at,
            dns_google_ok=dns_google.ok,
            dns_cloudflare_ok=dns_cloudflare.ok,
            dns_opendns_ok=dns_opendns.ok,
            dns_google_ms=dns_google.latency_ms,
            dns_cloudflare_ms=dns_cloudflare.latency_ms,
            dns_opendns_ms=dns_opendns.latency_ms,
            ping_192_168_1_1_ok=ping_1.ok,
            ping_192_168_0_1_ok=ping_0.ok,
            ping_192_168_1_1_ms=ping_1.latency_ms,
            ping_192_168_0_1_ms=ping_0.latency_ms,
            internet_ok=internet_ok,
        )
        apply_outage_edges(
            c,
            prev_internet_ok=prev_internet_ok,
            internet_ok=internet_ok,
            checked_at=checked_at,
        )

    conn = persist_with_retry(conn, cfg, _persist)

    logger.info(
        "sample internet_ok=%s dns=%s/%s/%s lan_1_1=%s lan_0_1=%s",
        internet_ok,
        dns_google.ok,
        dns_cloudflare.ok,
        dns_opendns.ok,
        ping_1.ok,
        ping_0.ok,
    )
    return internet_ok, conn


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for h in logging.root.handlers:
        fmt = getattr(h, "formatter", None)
        if fmt is not None:
            fmt.converter = time.localtime

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    cfg = load_mysql_config()
    conn = connect(cfg)
    close_open_outages_at_restart(conn, ended_at=_local_naive())

    prev_internet_ok: bool | None = None
    logger.info("Monitor started, interval=%ss", INTERVAL_SEC)

    while not _shutdown:
        checked_at = _local_naive()
        try:
            prev_internet_ok, conn = run_once(
                conn,
                cfg,
                prev_internet_ok=prev_internet_ok,
                checked_at=checked_at,
            )
        except Exception:
            logger.exception("Cycle failed")
        for _ in range(INTERVAL_SEC * 10):
            if _shutdown:
                break
            time.sleep(0.1)

    conn.close()
    logger.info("Monitor stopped")
