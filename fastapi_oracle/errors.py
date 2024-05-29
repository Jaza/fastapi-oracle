from re import Pattern
from typing import Type

from fastapi_oracle.constants import PACKAGE_STATE_INVALIDATED_REGEX


class IntermittentDatabaseError(Exception):
    """Intermittent database error occurred, user should retry again later."""


class PackageStateInvalidatedError(Exception):
    """Package state invalidated in PL/SQL."""


class ProgramUnitNotFoundError(Exception):
    """Program unit not found in PL/SQL."""


class RecordAttributeCharacterEncodingError(Exception):
    """Character encoding error in record attribute."""


class CursorRecordCharacterEncodingError(Exception):
    """Character encoding error in cursor record."""


class ReadClobMaxChunksExceededError(Exception):
    """Max chunks exceeded while reading clob."""


# This list acts as a registry. Anything that wants more error classes treated as
# intermittent database errors, adds to this list on app startup. So the entries that
# are literally defined here, should only be considered the base set of entries, not the
# complete set of entries. This list should also, therefore, be imported at the
# function / method level, not at the module level, to be on the safe side that the
# complete set of entries is getting imported.
INTERMITTENT_DATABASE_ERROR_CLASSES: list[Type[Exception]] = [
    PackageStateInvalidatedError,
    ProgramUnitNotFoundError,
]

# This dict acts as a registry. Anything that wants more error strings treated as
# intermittent database errors, adds to this dict on app startup. So the mappings that
# are literally defined here, should only be considered the base set of mappings, not
# the complete set of mappings. This dict should also, therefore, be imported at the
# function / method level, not at the module level, to be on the safe side that the
# complete set of mappings is getting imported.
INTERMITTENT_DATABASE_ERROR_STRING_MAP: dict[str, str | Pattern] = {
    "program_unit_not_found_error": "could not find program unit being called",
    "package_state_discarded_error": "existing state of packages has been discarded",
    "package_state_invalidated_error": PACKAGE_STATE_INVALIDATED_REGEX,
    "no_listener_error": "no listener",
    "not_connected_error": "not connected",
    "connection_was_closed_error": "connection was closed",
    "service_unknown_to_listener_error": (
        "listener does not currently know of service requested in connect descriptor"
    ),
}
