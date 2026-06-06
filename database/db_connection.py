from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

try:
    import oracledb
except ImportError as import_error:  # pragma: no cover - depends on local setup
    oracledb = None
    _ORACLEDB_IMPORT_ERROR = import_error
else:
    _ORACLEDB_IMPORT_ERROR = None


class DatabaseConnectionError(RuntimeError):
    """Raised when the Oracle database connection cannot be opened."""


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise DatabaseConnectionError(f"{name} must be an integer.") from exc


def get_connection():
    """
    Open an Oracle connection for the SkillSwap application.

    Environment variables can override the local defaults:
    SKILLSWAP_DB_USER, SKILLSWAP_DB_PASSWORD, SKILLSWAP_DB_HOST,
    SKILLSWAP_DB_PORT, SKILLSWAP_DB_SID, SKILLSWAP_DB_SERVICE_NAME.
    """
    if oracledb is None:
        raise DatabaseConnectionError(
            "The 'oracledb' package is not installed. Install it with "
            "'pip install oracledb' and try again."
        ) from _ORACLEDB_IMPORT_ERROR

    user = os.getenv("SKILLSWAP_DB_USER", "system")
    password = os.getenv("SKILLSWAP_DB_PASSWORD", "Dawar@1407")
    host = os.getenv("SKILLSWAP_DB_HOST", "localhost")
    port = _env_int("SKILLSWAP_DB_PORT", 1521)
    service_name = os.getenv("SKILLSWAP_DB_SERVICE_NAME")
    sid = os.getenv("SKILLSWAP_DB_SID", "orcl")

    connection_args = {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
    }

    if service_name:
        connection_args["service_name"] = service_name
    else:
        connection_args["sid"] = sid

    try:
        return oracledb.connect(**connection_args)
    except Exception as exc:  # pragma: no cover - depends on Oracle runtime
        raise DatabaseConnectionError(f"Could not connect to Oracle: {exc}") from exc


@contextmanager
def connection_scope() -> Iterator:
    """Yield an Oracle connection and always close it."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
