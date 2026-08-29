from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from iceberg.persistence.schema import SCHEMA_SQL


class SQLiteDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.transaction_depth = 0
        self.connection.executescript(SCHEMA_SQL)
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            if self.transaction_depth == 0:
                self.connection.execute("BEGIN")
            self.transaction_depth += 1
            yield self.connection
        except Exception:
            if self.transaction_depth == 1:
                self.connection.rollback()
            raise
        else:
            if self.transaction_depth == 1:
                self.connection.commit()
        finally:
            self.transaction_depth = max(0, self.transaction_depth - 1)

    def close(self) -> None:
        self.connection.close()
