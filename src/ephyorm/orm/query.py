"""
Query Builder (internal DSL)
A chainable Query class that lazily builds and executes SQL queries.
This is the core of every ORM's fluent interface.
"""

from typing import Any, Dict, List, Optional, Type, TypeVar, Tuple
from ephyorm.db.connection import PostgresConnection
from ephyorm.exceptions import ModelError, ValueValidationError,DoesNotExistError

T = TypeVar("T")


class Query:
    """
    A lazily-evaluated SQL query builder.

    Usage:
        q = Query(User).where(name='Alice').order_by('id')
        users = q.all()          # executes SELECT ... WHERE name = %s ORDER BY id
        first = q.first()        # same query + LIMIT 1
        total = q.count()        # SELECT COUNT(*) ... WHERE name = %s

    Chaining creates new copies — original query is never mutated:
        base = Query(User).where(age=25)
        limited = base.limit(10)   # new Query, base unchanged
    """

    def __init__(self, model_class: Type[T]):
        self._model = model_class
        self._select_fields: List[str] = []       # empty = SELECT *
        self._where_conditions: List[Tuple[str, str, Any]] = []  # (col, op, val)
        self._order_by: List[Tuple[str, str]] = []  # (field, 'ASC'|'DESC')
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None

    # ─────────────────────────────────────────────────────────────
    # Chainable builders (return new copies — immutable)
    # ─────────────────────────────────────────────────────────────

    def select(self, *fields: str) -> "Query":
        """Specify columns to select. Default is *."""
        new_query = self._copy()
        new_query._select_fields = list(fields)
        return new_query

    def where(self, **conditions: Any) -> "Query":
        """Add equality WHERE conditions. Returns a new Query."""
        new_query = self._copy()
        for col, val in conditions.items():
            if not col.replace("_", "").isalnum():
                raise ValueValidationError(f"Invalid column name: {col}")
            new_query._where_conditions.append((col, "=", val))
        return new_query

    def order_by(self, *fields: str) -> "Query":
        """Add ORDER BY clauses (ascending)."""
        new_query = self._copy()
        for f in fields:
            if not f.replace("_", "").isalnum():
                raise ValueValidationError(f"Invalid column name: {f}")
            new_query._order_by.append((f, "ASC"))
        return new_query

    def order_by_desc(self, *fields: str) -> "Query":
        """Add ORDER BY ... DESC clauses."""
        new_query = self._copy()
        for f in fields:
            if not f.replace("_", "").isalnum():
                raise ValueValidationError(f"Invalid column name: {f}")
            new_query._order_by.append((f, "DESC"))
        return new_query

    def limit(self, n: int) -> "Query":
        """Set LIMIT."""
        new_query = self._copy()
        new_query._limit = n
        return new_query

    def offset(self, n: int) -> "Query":
        """Set OFFSET."""
        new_query = self._copy()
        new_query._offset = n
        return new_query

    # ─────────────────────────────────────────────────────────────
    # Execution methods (build SQL + execute)
    # ─────────────────────────────────────────────────────────────

    def all(self) -> List[T]:
        """Execute query and return all matching model instances."""
        sql, params = self._build_select()
        return self._execute(sql, params)

    def first(self) -> Optional[T]:
        """Execute query and return first match, or None."""
        # Build with LIMIT 1, ignoring any existing limit
        sql, params = self._build_select(limit=1)
        rows = self._execute(sql, params)
        return rows[0] if rows else None

    def get(self) -> T:
        """
        Execute query and return exactly one result.
        Raises ModelError if no row or multiple rows found.
        """
        sql, params = self._build_select(limit=2)
        rows = self._execute(sql, params)
        if not rows:
            raise ModelError(f"{self._model.__name__} matching query does not exist")
        if len(rows) > 1:
            raise ModelError(
                f"Expected 1 {self._model.__name__}, got {len(rows)}"
            )
        return rows[0]

    def count(self) -> int:
        """Execute SELECT COUNT(*) with same WHERE clause."""
        sql, params = self._build_count()
        with PostgresConnection(self._model._get_dsn()) as conn:
            rows = conn.execute(sql, params)
            return rows[0]["count"]

    # ─────────────────────────────────────────────────────────────
    # SQL generation (internal)
    # ─────────────────────────────────────────────────────────────

    def _build_select(self, limit: Optional[int] = None) -> Tuple[str, Tuple[Any, ...]]:
        """Build SELECT SQL and parameters."""
        table = self._model._get_table_name()

        # SELECT clause
        if self._select_fields:
            fields_sql = ", ".join(self._select_fields)
        else:
            fields_sql = "*"

        sql = f"SELECT {fields_sql} FROM {table}"
        params: List[Any] = []

        # WHERE clause
        if self._where_conditions:
            conditions_sql = []
            for col, op, val in self._where_conditions:
                conditions_sql.append(f"{col} {op} %s")
                params.append(val)
            sql += " WHERE " + " AND ".join(conditions_sql)

        # ORDER BY
        if self._order_by:
            order_sql = ", ".join(f"{f} {d}" for f, d in self._order_by)
            sql += f" ORDER BY {order_sql}"

        # LIMIT (use passed limit if provided, else self._limit)
        effective_limit = limit if limit is not None and limit > 0 else self._limit
        if effective_limit is not None and effective_limit > 0:
            sql += f" LIMIT {effective_limit}"

        # OFFSET
        if self._offset is not None and self._offset > 0:
            sql += f" OFFSET {self._offset}"

        return sql, tuple(params)

    def _build_count(self) -> Tuple[str, Tuple[Any, ...]]:
        """Build SELECT COUNT(*) SQL (ignores SELECT fields and ORDER BY)."""
        table = self._model._get_table_name()
        sql = f"SELECT COUNT(*) as count FROM {table}"
        params: List[Any] = []

        if self._where_conditions:
            conditions_sql = []
            for col, op, val in self._where_conditions:
                conditions_sql.append(f"{col} {op} %s")
                params.append(val)
            sql += " WHERE " + " AND ".join(conditions_sql)

        return sql, tuple(params)

    def _execute(self, sql: str, params: Tuple[Any, ...]) -> List[T]:
        """Execute SQL and return model instances."""
        with PostgresConnection(self._model._get_dsn()) as conn:
            rows = conn.execute(sql, params)
            return [self._model._from_row(dict(row)) for row in rows]

    def _copy(self) -> "Query":
        """Create a deep copy of this query for immutable chaining."""
        new = Query(self._model)
        new._select_fields = self._select_fields.copy()
        new._where_conditions = self._where_conditions.copy()
        new._order_by = self._order_by.copy()
        new._limit = self._limit
        new._offset = self._offset
        return new

    # ─────────────────────────────────────────────────────────────
    # Representation (for debugging)
    # ─────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        sql, params = self._build_select()
        return f"<Query [{self._model.__name__}] {sql} params={params}>"
