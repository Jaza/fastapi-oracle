import re
from typing import NamedTuple

from oracledb import AsyncConnection, AsyncConnectionPool, AsyncCursor


class DbPoolAndConn(NamedTuple):
    pool: AsyncConnectionPool
    conn: AsyncConnection


class DbPoolConnAndCursor(NamedTuple):
    pool: AsyncConnectionPool
    conn: AsyncConnection
    cursor: AsyncCursor


class DbPoolKey(NamedTuple):
    db_host: str
    db_port: int
    db_user: str
    db_service_name: str


class DbPoolAndCreatedTime(NamedTuple):
    pool: AsyncConnectionPool
    created_time: float


DEFAULT_MAX_ROWS = 10_000

# Thanks to: https://stackoverflow.com/a/1176023/2066849
CAMEL_TO_SNAKE_REGEX = re.compile(r"(?<!^)(?=[A-Z])")

PACKAGE_STATE_INVALIDATED_REGEX = re.compile(
    r'existing state of package body "[^"]+" has been invalidated'
)
