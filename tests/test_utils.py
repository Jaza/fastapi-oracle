from unittest.mock import AsyncMock, MagicMock

import pytest

from fastapi_oracle.errors import (
    CursorRecordCharacterEncodingError,
    ReadClobMaxChunksExceededError,
    RecordAttributeCharacterEncodingError,
)
from fastapi_oracle.utils import (
    coll_records_as_dicts,
    cursor_rows_as_dicts,
    cursor_rows_as_gen,
    read_clob,
    result_keys_to_lower,
)


@pytest.mark.pureunit
def test_cursor_rows_as_dicts():
    cursor = MagicMock()
    cursor.description = [["do"], ["re"], ["mi"]]
    cursor_rows_as_dicts(cursor)
    row_as_dict = cursor.rowfactory(111, 222, 333)
    assert row_as_dict == {"do": 111, "re": 222, "mi": 333}


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_cursor_rows_as_gen():
    things_to_fetch = [42, 43, 44, None]
    cursor = AsyncMock()
    cursor.fetchone.side_effect = things_to_fetch
    result = [row async for row in cursor_rows_as_gen(cursor)]
    assert result == things_to_fetch[:-1]


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_cursor_rows_as_gen_no_rows():
    cursor = AsyncMock()
    cursor.fetchone.side_effect = [None]
    result = [row async for row in cursor_rows_as_gen(cursor)]
    assert result == []


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_cursor_rows_as_gen_more_than_max_rows():
    things_to_fetch = [42, 43, 44, None]
    max_rows = 2
    cursor = AsyncMock()
    cursor.fetchone.side_effect = things_to_fetch
    result = [row async for row in cursor_rows_as_gen(cursor, max_rows=max_rows)]
    assert result == things_to_fetch[:max_rows]


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_cursor_rows_as_gen_with_dodgy_windows_1252_encoding():
    value = "SEÑOR SMITH".encode("windows-1252")
    cursor = AsyncMock()
    cursor.fetchone.side_effect = lambda: value.decode("utf-8")

    with pytest.raises(CursorRecordCharacterEncodingError) as exc_info:
        [row async for row in cursor_rows_as_gen(cursor)]

    assert str(exc_info.value) == (
        "Character encoding error in cursor record, decoding to utf-8 failed, "
        "error: 'utf-8' codec can't decode byte 0xd1 in position 2: invalid "
        "continuation byte, value: b'SE\\xd1OR SMITH'"
    )


@pytest.mark.pureunit
def test_coll_records_as_dicts():
    record1 = MagicMock()
    record1.do = 111
    record2 = MagicMock()
    record2.re = 222
    record2.mi = 333

    type_attr1 = MagicMock()
    type_attr1.name = "do"
    type_attr2 = MagicMock()
    type_attr2.name = "re"
    type_attr3 = MagicMock()
    type_attr3.name = "mi"

    coll = MagicMock()
    coll.aslist.return_value = [record1, record2]
    coll.type.element_type.attributes = [type_attr1, type_attr2, type_attr3]

    dicts = [x for x in coll_records_as_dicts(coll)]

    assert dicts[0]["do"] == 111
    assert dicts[1]["re"] == 222
    assert dicts[1]["mi"] == 333


class DodgyTestRecord:
    def __init__(self, value):
        self.dodgy_field = value

    @property
    def dodgy_field(self):
        return self._dodgy_field.decode("utf-8")

    @dodgy_field.setter
    def dodgy_field(self, value):
        self._dodgy_field = value


@pytest.mark.pureunit
def test_coll_records_as_dicts_with_dodgy_windows_1252_encoding():
    value = "SEÑOR SMITH".encode("windows-1252")
    attr_name = "dodgy_field"
    record1 = DodgyTestRecord(value)
    type_attr1 = MagicMock()
    type_attr1.name = attr_name
    coll = MagicMock()
    coll.aslist.return_value = [record1]
    coll.type.element_type.attributes = [type_attr1]

    with pytest.raises(RecordAttributeCharacterEncodingError) as exc_info:
        [x for x in coll_records_as_dicts(coll)]

    assert str(exc_info.value) == (
        "Character encoding error in record attribute, decoding to utf-8 failed, "
        "error: 'utf-8' codec can't decode byte 0xd1 in position 2: invalid "
        "continuation byte, attribute: dodgy_field, value: b'SE\\xd1OR SMITH'"
    )


async def result_keys_to_lower_test_gen():
    for row in [
        {"DO": 111, "RE": 222, "MI": 333},
        {"DO": 444, "RE": 555, "MI": 666},
    ]:
        yield row


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_result_keys_to_lower():
    result = result_keys_to_lower_test_gen()
    assert [x async for x in result_keys_to_lower(result)] == [
        {"do": 111, "re": 222, "mi": 333},
        {"do": 444, "re": 555, "mi": 666},
    ]


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_cursor_rows_as_gen_and_result_keys_to_lower():
    things_to_fetch = [
        {"DO": 111, "RE": 222, "MI": 333},
        {"DO": 444, "RE": 555, "MI": 666},
        None,
    ]
    cursor = AsyncMock()
    cursor.fetchone.side_effect = things_to_fetch
    result = (
        row2
        async for row2 in result_keys_to_lower(
            row1 async for row1 in cursor_rows_as_gen(cursor)
        )
    )
    assert [x async for x in result] == [
        {"do": 111, "re": 222, "mi": 333},
        {"do": 444, "re": 555, "mi": 666},
    ]


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_read_clob():
    clob = AsyncMock()
    clob.getchunksize.return_value = 20
    clob.read.side_effect = [
        "hello world sup my n",
        "ame is jiggy wiggy s",
        "lim shady",
        "",
    ]

    content = await read_clob(clob)

    assert content == "hello world sup my name is jiggy wiggy slim shady"


@pytest.mark.asyncio
@pytest.mark.pureunit
async def test_read_clob_max_chunks_exceeded():
    clob = AsyncMock()
    clob.getchunksize.return_value = 20
    clob.read.side_effect = [
        "hello world sup my n",
        "ame is jiggy wiggy s",
        "lim shady",
        "",
    ]

    with pytest.raises(ReadClobMaxChunksExceededError) as exc_info:
        await read_clob(
            clob, field_name="out_content in package_foo.prBar", max_chunks=2
        )

    assert str(exc_info.value) == (
        "Exceeded 2 max chunks (chunk size 20 bytes) while reading out_content in "
        "package_foo.prBar"
    )
