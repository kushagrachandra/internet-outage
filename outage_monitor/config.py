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
    # required = ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    # missing = [k for k in required if not os.environ.get(k)]
    # if missing:
    #     raise RuntimeError(
    #         "Missing required environment variables: " + ", ".join(missing)
    #     )
    host = "192.168.1.250"
    port = 3306
    user = "asus"
    password = "hello@123"
    database = "internet_outage"
    return MySQLConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
