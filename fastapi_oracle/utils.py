from collections.abc import AsyncIterable, Mapping
from typing import Any, AsyncGenerator, Generator

from loguru import logger
from oracledb import AsyncCursor, AsyncLOB, DbObject

from fastapi_oracle.constants import DEFAULT_MAX_ROWS, DEFAULT_READ_CLOB_MAX_CHUNKS
from fastapi_oracle.errors import (
    CursorRecordCharacterEncodingError,
    ReadClobMaxChunksExceededError,
    RecordAttributeCharacterEncodingError,
)


def cursor_rows_as_dicts(cursor: AsyncCursor):
    """Make the specified cursor return its rows as dicts instead of tuples.

    This should be called after cursor.execute() and before cursor.fetchall().

    Thanks to: https://github.com/oracle/python-cx_Oracle/blob/main/samples/query.py
    """
    columns = [col[0] for col in cursor.description]
    cursor.rowfactory = lambda *args: dict(zip(columns, args))


async def _fetch_cursor_record(cursor: AsyncCursor) -> Any:
    try:
        return await cursor.fetchone()
    except UnicodeDecodeError as ex:
        raise CursorRecordCharacterEncodingError(
            "Character encoding error in cursor record, decoding to utf-8 failed, "
            f"error: {ex}, value: {ex.object!r}"
        )


async def cursor_rows_as_gen(
    cursor: AsyncCursor, max_rows: int = DEFAULT_MAX_ROWS
) -> AsyncGenerator[Any, None]:
    """Loop through the specified cursor's results in a generator."""
    i = 0

    while (row := await _fetch_cursor_record(cursor)) is not None:
        if i >= max_rows:
            logger.warning(
                "Max rows exceeded while looping through cursor results "
                f"(max_rows={max_rows})"
            )
            break

        yield row
        i += 1


def coll_records_as_dicts(coll: DbObject) -> Generator[dict[str, Any], None, None]:
    """Make the specified collection of records into simple dicts."""
    for record in coll.aslist():
        item: dict[str, Any] = {}

        for type_attr in coll.type.element_type.attributes:
            attr_name = type_attr.name

            try:
                attr_value = getattr(record, type_attr.name, None)
            except UnicodeDecodeError as ex:
                raise RecordAttributeCharacterEncodingError(
                    "Character encoding error in record attribute, decoding to utf-8 "
                    f"failed, error: {ex}, attribute: {attr_name}, value: {ex.object!r}"
                )

            item[f"{attr_name}"] = attr_value

        yield item


def row_keys_to_lower(row: Mapping[str, Any]) -> dict[str, Any]:
    """Make the keys lowercase for the specified row."""
    return {k.lower(): v for k, v in row.items()}


async def result_keys_to_lower(
    result: AsyncIterable[Mapping[str, Any]]
) -> AsyncGenerator[dict[str, Any], None]:
    """Make the keys lowercase for each row in the specified results."""
    async for row in result:
        yield row_keys_to_lower(row)


async def read_clob(
    clob: AsyncLOB, field_name: str | None = None, max_chunks: int | None = None
) -> str:
    """Read a clob stream in chunks."""
    chunk_size = await clob.getchunksize()
    i = 0
    offset = 1
    content = ""
    data: Any = None
    _max_chunks = max_chunks or DEFAULT_READ_CLOB_MAX_CHUNKS

    while ((not i) or data) and i < _max_chunks:
        data = await clob.read(offset, chunk_size)

        if data:
            _data = f"{data}"
            content = f"{content}{_data}"
            offset += len(_data)

        i += 1

    if i >= _max_chunks:
        _field_name = field_name or "clob"
        raise ReadClobMaxChunksExceededError(
            f"Exceeded {_max_chunks} max chunks (chunk size {chunk_size} bytes) while "
            f"reading {_field_name}"
        )

    return content
