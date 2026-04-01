from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

import pymysql

from outage_monitor.config import MySQLConfig

logger = logging.getLogger(__name__)

# Common "connection lost" / network issues — safe to reopen and retry once.
_TRANSIENT_MYSQL_CODES = frozenset(
    {
        2002,  # CR_CONNECTION_ERROR
        2003,  # CR_CONN_HOST_ERROR
        2006,  # CR_SERVER_GONE_ERROR
        2013,  # CR_SERVER_LOST
    }
)


def _is_transient_mysql(exc: Exception) -> bool:
    if isinstance(exc, pymysql.err.InterfaceError):
        return True
    if isinstance(exc, (pymysql.err.OperationalError, pymysql.err.InternalError)):
        code = exc.args[0] if exc.args else None
        return code in _TRANSIENT_MYSQL_CODES
    return False


def ensure_connected(
    conn: pymysql.connections.Connection,
    cfg: MySQLConfig,
) -> pymysql.connections.Connection:
    """Keep using the same handle when healthy; replace it if ping/reconnect fails."""
    try:
        conn.ping(reconnect=True)
        return conn
    except pymysql.err.Error:
        logger.warning("MySQL ping failed, opening a new connection", exc_info=True)
        try:
            conn.close()
        except Exception:
            pass
        return connect(cfg)


def persist_with_retry(
    conn: pymysql.connections.Connection,
    cfg: MySQLConfig,
    fn: Callable[[pymysql.connections.Connection], None],
) -> pymysql.connections.Connection:
    """Run a DB callback; on transient disconnect, reconnect once and retry."""
    for attempt in range(2):
        try:
            conn = ensure_connected(conn, cfg)
            fn(conn)
            return conn
        except (
            pymysql.err.OperationalError,
            pymysql.err.InternalError,
            pymysql.err.InterfaceError,
        ) as e:
            if attempt == 0 and _is_transient_mysql(e):
                logger.warning("MySQL transient error, reconnecting and retrying: %s", e)
                try:
                    conn.close()
                except Exception:
                    pass
                conn = connect(cfg)
                continue
            raise
    raise RuntimeError("persist_with_retry: unreachable")


def close_open_outages_at_restart(
    conn: pymysql.connections.Connection,
    *,
    ended_at: datetime,
) -> None:
    """End any still-open outage rows so restarts do not leave duplicate open events."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE outage_events SET ended_at = %s WHERE ended_at IS NULL",
            (ended_at,),
        )
    conn.commit()


def connect(cfg: MySQLConfig) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def insert_connectivity_sample(
    conn: pymysql.connections.Connection,
    *,
    checked_at: datetime,
    dns_google_ok: bool,
    dns_cloudflare_ok: bool,
    dns_opendns_ok: bool,
    dns_google_ms: int | None,
    dns_cloudflare_ms: int | None,
    dns_opendns_ms: int | None,
    ping_192_168_1_1_ok: bool,
    ping_192_168_0_1_ok: bool,
    ping_192_168_1_1_ms: int | None,
    ping_192_168_0_1_ms: int | None,
    internet_ok: bool,
) -> None:
    sql = """
        INSERT INTO connectivity_samples (
            checked_at,
            dns_google_ok, dns_cloudflare_ok, dns_opendns_ok,
            dns_google_ms, dns_cloudflare_ms, dns_opendns_ms,
            ping_192_168_1_1_ok, ping_192_168_0_1_ok,
            ping_192_168_1_1_ms, ping_192_168_0_1_ms,
            internet_ok
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """
    args = (
        checked_at,
        int(dns_google_ok),
        int(dns_cloudflare_ok),
        int(dns_opendns_ok),
        dns_google_ms,
        dns_cloudflare_ms,
        dns_opendns_ms,
        int(ping_192_168_1_1_ok),
        int(ping_192_168_0_1_ok),
        ping_192_168_1_1_ms,
        ping_192_168_0_1_ms,
        int(internet_ok),
    )
    with conn.cursor() as cur:
        cur.execute(sql, args)
    conn.commit()


def apply_outage_edges(
    conn: pymysql.connections.Connection,
    *,
    prev_internet_ok: bool | None,
    internet_ok: bool,
    checked_at: datetime,
) -> None:
    if prev_internet_ok is None:
        if not internet_ok:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outage_events (started_at, ended_at, is_internet_outage, notes)
                    VALUES (%s, NULL, 1, %s)
                    """,
                    (
                        checked_at,
                        "All DNS resolution checks failed (initial sample)",
                    ),
                )
            conn.commit()
        return

    if prev_internet_ok == internet_ok:
        return

    with conn.cursor() as cur:
        if not internet_ok:
            cur.execute(
                """
                INSERT INTO outage_events (started_at, ended_at, is_internet_outage, notes)
                VALUES (%s, NULL, 1, %s)
                """,
                (
                    checked_at,
                    "All DNS resolution checks failed",
                ),
            )
        else:
            cur.execute(
                """
                UPDATE outage_events
                SET ended_at = %s
                WHERE ended_at IS NULL AND is_internet_outage = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (checked_at,),
            )
    conn.commit()
