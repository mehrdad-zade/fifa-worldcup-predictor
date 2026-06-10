import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from config.settings import settings


def _ensure_dir() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    _ensure_dir()
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_sql(sql: str, params: tuple = ()) -> None:
    with get_connection() as conn:
        conn.execute(sql, params)


def executemany_sql(sql: str, rows: list[tuple]) -> None:
    with get_connection() as conn:
        conn.executemany(sql, rows)


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    _ensure_dir()
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()
    return df


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall()
