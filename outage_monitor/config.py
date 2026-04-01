import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def load_mysql_config() -> MySQLConfig:
    required = ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ["MYSQL_USER"]
    password = os.environ["MYSQL_PASSWORD"]
    database = os.environ["MYSQL_DATABASE"]
    return MySQLConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
