import time
from functools import wraps
from re import Pattern
from typing import AsyncGenerator, Awaitable, Callable, ParamSpec, TypeVar

from fastapi import Depends
from loguru import logger
from oracledb import (
    DB_TYPE_VARCHAR,
    SPOOL_ATTRVAL_TIMEDWAIT,
    AsyncConnectionPool,
    DatabaseError,
    InterfaceError,
    create_pool_async,
    makedsn,
)

from fastapi_oracle import pools
from fastapi_oracle.config import Settings, get_settings
from fastapi_oracle.constants import (
    CAMEL_TO_SNAKE_REGEX,
    DbPoolAndConn,
    DbPoolAndCreatedTime,
    DbPoolConnAndCursor,
    DbPoolKey,
)
from fastapi_oracle.errors import IntermittentDatabaseError


P = ParamSpec("P")
T = TypeVar("T")


async def close_db_pool(pool: AsyncConnectionPool):  # pragma: no cover
    """Close the DB connection pool."""
    try:
        await pool.close()
    except (DatabaseError, InterfaceError) as ex:
        if "while trying to destroy the Session Pool" in f"{ex}":
            logger.warning(
                '"error occurred while trying to destroy the Session Pool" '
                "was raised, when releasing the database connection pool - "
                "this can happen when there are still busy connections - "
                "suppressing this error, hopefully consuming code can then "
                "continue gracefully"
            )
        elif "invalid OCI handle" in f"{ex}":
            logger.warning(
                '"invalid OCI handle" was raised, when releasing the database '
                "connection pool - this can happen when the pool has already been "
                "closed - assuming that that's what happened in this case, therefore "
                "suppressing this error, so that consuming code can continue "
                "gracefully"
            )
        elif "not connected" in f"{ex}":
            logger.warning(
                '"not connected" was raised, when releasing the database '
                "connection pool - this can happen on release when the pool "
                "has already been closed - assuming that that's what happened "
                "in this case, therefore suppressing this error, so that "
                "consuming code can continue gracefully"
            )
        elif "connection pool cannot be closed because connections are busy" in f"{ex}":
            logger.warning(
                '"connection pool cannot be closed because connections are busy" '
                "was raised, when releasing the database connection pool - "
                "this can happen when there are still busy connections - "
                "suppressing this error, hopefully consuming code can then "
                "continue gracefully"
            )
        else:
            raise ex


async def get_or_create_db_pool(
    settings: Settings,
) -> AsyncConnectionPool:  # pragma: no cover
    """Get or create the DB connection pool."""
    pool_key = DbPoolKey(
        settings.db_host,
        settings.db_port,
        settings.db_user,
        settings.db_service_name,
    )

    if pools.DB_POOLS.get(pool_key) is not None:
        ttl = settings.db_conn_ttl
        pool, created_time = pools.DB_POOLS[pool_key]

        if ttl is not None and time.monotonic() - created_time >= ttl:
            logger.info(
                "Closing the existing database connection pool because it is older "
                f"than {ttl} seconds"
            )
            await close_db_pool(pool)
        else:
            return pool

    dsn = makedsn(
        host=settings.db_host,
        port=settings.db_port,
        sid=settings.db_service_name,
    )
    create_pool_kwargs = {}

    if settings.db_wait_timeout_secs is not None:
        create_pool_kwargs["getmode"] = SPOOL_ATTRVAL_TIMEDWAIT
        create_pool_kwargs["wait_timeout"] = settings.db_wait_timeout_secs * 1000

    if settings.db_pool_min_size is not None:
        create_pool_kwargs["min"] = settings.db_pool_min_size
    if settings.db_pool_max_size is not None:
        create_pool_kwargs["max"] = settings.db_pool_max_size
    if settings.db_pool_increment is not None:
        create_pool_kwargs["increment"] = settings.db_pool_increment
    if settings.db_pool_conn_timeout is not None:
        create_pool_kwargs["timeout"] = settings.db_pool_conn_timeout

    pool = create_pool_async(
        user=settings.db_user,
        password=settings.db_password,
        dsn=dsn,
        **create_pool_kwargs,
    )
    pools.DB_POOLS[pool_key] = DbPoolAndCreatedTime(
        pool=pool, created_time=time.monotonic()
    )

    return pools.DB_POOLS[pool_key].pool


async def get_db_pool(
    settings: Settings = Depends(get_settings),
) -> tuple[AsyncConnectionPool, Settings]:  # pragma: no cover
    """Get the DB connection pool.

    Creates a new singleton connection pool if one doesn't yet exist, otherwise returns
    the existing singleton connection pool.

    Suitable for use as a FastAPI path operation with depends().
    """
    return (await get_or_create_db_pool(settings), settings)


async def get_db_conn(
    pool_and_settings: tuple[AsyncConnectionPool, Settings] = Depends(get_db_pool),
) -> AsyncGenerator[DbPoolAndConn, None]:  # pragma: no cover
    """Get a DB connection.

    Suitable for use as a FastAPI path operation with depends().
    """
    pool, settings = pool_and_settings

    try:
        async with pool.acquire() as conn:  # type: ignore
            if settings.db_encoding_error_handler_name is not None:

                def output_type_handler(
                    cursor, name, default_type, size, precision, scale
                ):
                    if default_type == DB_TYPE_VARCHAR:
                        return cursor.var(
                            default_type,
                            size,
                            arraysize=cursor.arraysize,
                            encoding_errors=settings.db_encoding_error_handler_name,
                        )

                conn.outputtypehandler = output_type_handler

            if settings.db_call_timeout_secs:
                conn.call_timeout = settings.db_call_timeout_secs * 1000

            yield DbPoolAndConn(pool=pool, conn=conn, settings=settings)
    except (DatabaseError, RuntimeError) as ex:
        if "not connected" in f"{ex}":
            logger.warning(
                '"not connected" was raised, either when acquiring or when releasing '
                "the database connection pool - this can happen on release when the "
                "pool has already been closed - assuming that that's what happened in "
                "this case, therefore suppressing this error, so that consuming code "
                "can continue gracefully"
            )
        elif "handler is closed" in f"{ex}":
            logger.warning(
                '"handler is closed" was raised, either when acquiring or when '
                "releasing the database connection pool - this can happen on release "
                "when the pool has already been closed - assuming that that's what "
                "happened in this case, therefore suppressing this error, so that "
                "consuming code can continue gracefully"
            )
        else:
            raise ex


async def get_db_cursor(
    pool_and_conn: DbPoolAndConn = Depends(get_db_conn),
) -> AsyncGenerator[DbPoolConnAndCursor, None]:  # pragma: no cover
    """Get a DB cursor.

    Suitable for use as a FastAPI path operation with depends().

    This is more convenient to use than get_db_pool() or get_db_conn(), it calls those
    for you, so you can without further ado get a cursor ready to chuck a query at.
    """
    pool, conn, settings = pool_and_conn
    async with conn.cursor() as cursor:
        yield DbPoolConnAndCursor(
            pool=pool, conn=conn, cursor=cursor, settings=settings
        )


async def close_db_pools():  # pragma: no cover
    """Close the DB connection pools.

    This shouldn't need to be called manually in most cases, it's registered as a
    FastAPI shutdown function, so it will get called when the Python process ends.
    """
    for pool, _ in pools.DB_POOLS.values():
        await close_db_pool(pool)

    pools.DB_POOLS = {}


def handle_db_errors(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Decorator to handle errors raised or returned by an Oracle DB call.

    Usage:

    @handle_db_errors
    async def _get_foos(db: DbPoolConnAndCursor) -> list[Foo]:
        result = await list_foos_query(db)
        return [x async for x in map_list_foos_result_to_foos(result)]
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        from fastapi_oracle.errors import (
            INTERMITTENT_DATABASE_ERROR_CLASSES,
            INTERMITTENT_DATABASE_ERROR_STRING_MAP,
        )

        try:
            return await func(*args, **kwargs)
        except tuple(INTERMITTENT_DATABASE_ERROR_CLASSES) as exc:
            logger.warning(
                "Database call returned an error_code indicating "
                f"{CAMEL_TO_SNAKE_REGEX.sub('_', exc.__class__.__name__).lower()}, "
                "will close database connection pool, the call will have to be retried "
                "later"
            )
            await close_db_pools()
            raise IntermittentDatabaseError(
                "An intermittent database error occurred, please try this call again "
                "soon"
            )
        except DatabaseError as exc:
            exc_str = f"{exc}".lower()

            for k, v in INTERMITTENT_DATABASE_ERROR_STRING_MAP.items():
                if (isinstance(v, Pattern) and v.search(exc_str) is not None) or (
                    isinstance(v, str) and v in exc_str
                ):
                    logger.warning(
                        f"Database call threw an exception indicating {k}, will close "
                        "database connection pool, the call will have to be retried "
                        "later"
                    )
                    await close_db_pools()
                    raise IntermittentDatabaseError(
                        "An intermittent database error occurred, please try this call "
                        "again soon"
                    )

            raise exc

    return wrapper
