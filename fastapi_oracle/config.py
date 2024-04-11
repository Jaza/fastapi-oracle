from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "127.0.0.1"
    db_port: int = 1521
    db_user: str = "dbuser"
    db_password: str = "dbpassword"  # nosemgrep
    db_service_name: str = "dbservicename"
    db_conn_ttl: int | None = None
    db_wait_timeout_secs: int | None = None
    db_pool_min_size: int | None = None
    db_pool_max_size: int | None = None
    db_pool_increment: int | None = None
    db_pool_conn_timeout: int | None = None
    db_encoding_error_handler_name: str | None = None
    db_call_timeout_secs: int | None = None


@lru_cache()
def get_settings() -> Settings:  # pragma: no cover
    """Get settings for fastapi-oracle.

    A settings object is only created once, per FastAPI recommended practice, so that
    values are only read from potentially expensive-to-read sources once. Subsequent
    calls to this function are cached.

    Suitable for use as a FastAPI path operation with depends().
    """
    return Settings()
