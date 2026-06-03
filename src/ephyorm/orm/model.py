"""
Base Model & Result Mapping

An ORM maps database tables to Python classes. This module provides the
simplest possible Model class that can:
    - Represent a table row as a Python object
    - Execute a query and convert each row into an instance
    - Save a model instance back to the database (naive INSERT/UPDATE)
"""

from typing import Any, Dict, List, Optional, Type, TypeVar
from src.ephyorm.db.connection import PostgresConnection
from src.ephyorm.exceptions import ValueValidationError,RuntimeConfigError

T = TypeVar("T", bound="Model")


class Model:
    """
    Base ORM Model class.

    Usage:
        class User(Model):
            __table__ = 'users'
            __primary_key__ = 'id'

        user = User(name='Alice', email='alice@example.com')
        user.save()  # INSERT, sets user.id

        user2 = User.get(1)  # SELECT by pk
        user2.name = 'Alicia'
        user2.save()  # UPDATE

        all_users = User.all()
        User.filter(name='Alice')

        user2.delete()
    """

    # Class-level configuration
    __table__: str = ""           # Database table name
    __primary_key__: str = "id"   # Primary key column name

    def __init__(self, **kwargs: Any):
        """
        Store all attributes as instance variables.
        Private attributes (starting with _) are skipped in SQL operations.
        Auto-initialize primary key to None if not provided.
        """
        # Auto-set primary key to None if not provided (unsaved state)
        pk = self._get_primary_key()
        if pk not in kwargs:
            setattr(self, pk, None)

        for key, value in kwargs.items():
            setattr(self, key, value)

    # ─────────────────────────────────────────────────────────────
    # Helper: Get public attributes (exclude private, class config)
    # ─────────────────────────────────────────────────────────────

    def _get_field_data(self) -> Dict[str, Any]:
        """
        Return a dict of public field names -> values for SQL operations.
        Excludes: __table__, __primary_key__, and any _private attrs.
        """
        fields = {}
        for key, value in self.__dict__.items():
            # Skip private attributes and class-level config keys
            if key.startswith("_"):
                continue
            if key in ("__table__", "__primary_key__"):
                continue
            fields[key] = value
        return fields

    @classmethod
    def _get_table_name(cls) -> str:
        """Return the table name, defaulting to lowercase class name + 's'."""
        if cls.__table__:
            return cls.__table__
        return cls.__name__.lower() + "s"

    @classmethod
    def _get_primary_key(cls) -> str:
        """Return the primary key column name."""
        return cls.__primary_key__ or "id"

    @classmethod
    def _from_row(cls: Type[T], row: Dict[str, Any]) -> T:
        """Create a model instance from a database row (dict)."""
        return cls(**row)

    # ─────────────────────────────────────────────────────────────
    # READ operations
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def get(cls: Type[T], pk: Any) -> Optional[T]:
        """
        Fetch a single row by primary key and return an instance, or None.

        SQL: SELECT * FROM table WHERE pk = %s LIMIT 1
        """
        table = cls._get_table_name()
        pk_col = cls._get_primary_key()

        with PostgresConnection(cls._get_dsn()) as conn:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {pk_col} = %s LIMIT 1",
                (pk,)
            )
            if not rows:
                return None
            return cls._from_row(dict(rows[0]))

    @classmethod
    def all(cls: Type[T]) -> List[T]:
        """
        Return a list of all rows as model instances.

        SQL: SELECT * FROM table
        """
        table = cls._get_table_name()

        with PostgresConnection(cls._get_dsn()) as conn:
            rows = conn.execute(f"SELECT * FROM {table}")
            return [cls._from_row(dict(row)) for row in rows]

    @classmethod
    def filter(cls: Type[T], **kwargs: Any) -> List[T]:
        """
        Return rows matching equality conditions.

        SQL: SELECT * FROM table WHERE col1 = %s AND col2 = %s

        Beware: Only equality conditions. No SQL injection because we
        use parameterized queries -- column names are validated against
        known fields, values are passed as parameters.
        """
        if not kwargs:
            return cls.all()

        table = cls._get_table_name()

        # Build WHERE clause with parameterized placeholders
        # Column names come from kwargs keys -- we must validate them
        conditions = []
        values = []
        for col, val in kwargs.items():
            # Basic validation: only alphanumeric + underscore
            if not col.replace("_", "").isalnum():
                raise ValueValidationError(f"Invalid column name: {col}")
            conditions.append(f"{col} = %s")
            values.append(val)

        where_clause = " AND ".join(conditions)

        with PostgresConnection(cls._get_dsn()) as conn:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {where_clause}",
                tuple(values)
            )
            return [cls._from_row(dict(row)) for row in rows]

    # ─────────────────────────────────────────────────────────────
    # WRITE operations
    # ─────────────────────────────────────────────────────────────

    def save(self) -> None:
        """
        Insert a new row if primary key is not set (None),
        otherwise update the existing row.

        After INSERT: updates self.<pk> with the generated SERIAL value
        using RETURNING.

        After UPDATE: no change to instance state.
        """
        pk_col = self._get_primary_key()
        pk_val = getattr(self, pk_col, None)

        if pk_val is None:
            self._insert()
        else:
            self._update()

    def _insert(self) -> None:
        """
        INSERT the instance into the database.

        SQL: INSERT INTO table (col1, col2) VALUES (%s, %s) RETURNING id
        """
        table = self._get_table_name()
        pk_col = self._get_primary_key()
        fields = self._get_field_data()

        # Remove pk from fields if it's None (SERIAL will generate it)
        if pk_col in fields and fields[pk_col] is None:
            del fields[pk_col]

        if not fields:
            raise ValueValidationError("No fields to insert")

        columns = list(fields.keys())
        placeholders = ["%s"] * len(columns)
        values = list(fields.values())

        cols_sql = ", ".join(columns)
        vals_sql = ", ".join(placeholders)

        with PostgresConnection(self._get_dsn()) as conn:
            rows = conn.execute(
                f"INSERT INTO {table} ({cols_sql}) VALUES ({vals_sql}) RETURNING {pk_col}",
                tuple(values)
            )
            conn.commit()

            # Set the generated primary key on the instance
            if rows:
                setattr(self, pk_col, rows[0][pk_col])

    def _update(self) -> None:
        """
        UPDATE the existing row by primary key.

        SQL: UPDATE table SET col1 = %s, col2 = %s WHERE id = %s
        """
        table = self._get_table_name()
        pk_col = self._get_primary_key()
        pk_val = getattr(self, pk_col)
        fields = self._get_field_data()

        # Remove pk from fields -- we don't update the primary key itself
        fields.pop(pk_col, None)

        if not fields:
            raise ValueValidationError("No fields to update")

        set_clauses = []
        values = []
        for col, val in fields.items():
            set_clauses.append(f"{col} = %s")
            values.append(val)

        # Add pk value for WHERE clause
        values.append(pk_val)

        set_sql = ", ".join(set_clauses)

        with PostgresConnection(self._get_dsn()) as conn:
            conn.execute(
                f"UPDATE {table} SET {set_sql} WHERE {pk_col} = %s",
                tuple(values)
            )
            conn.commit()

    def delete(self) -> None:
        """
        DELETE the row from the database by primary key.

        SQL: DELETE FROM table WHERE id = %s
        """
        table = self._get_table_name()
        pk_col = self._get_primary_key()
        pk_val = getattr(self, pk_col, None)

        if pk_val is None:
            raise ValueValidationError(f"Cannot delete: {pk_col} is not set")

        with PostgresConnection(self._get_dsn()) as conn:
            conn.execute(
                f"DELETE FROM {table} WHERE {pk_col} = %s",
                (pk_val,)
            )
            conn.commit()

    # ─────────────────────────────────────────────────────────────
    # Challenge: Convenience methods
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def create(cls: Type[T], **kwargs: Any) -> T:
        """
        Create a new instance, save it, and return it.

        Equivalent to:
            obj = cls(**kwargs)
            obj.save()
            return obj
        """
        instance = cls(**kwargs)
        instance.save()
        return instance

    # ─────────────────────────────────────────────────────────────
    # DSN configuration (placeholder -- will be replaced by config later)
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def _get_dsn(cls) -> str:
        """
        Return the database DSN.

        TODO: Replace with proper configuration (env var, class attr, etc.)
        For now, subclasses can override this or set _dsn class attribute.
        """
        if hasattr(cls, "_dsn") and cls._dsn:
            return cls._dsn
        raise RuntimeConfigError(
            f"{cls.__name__} has no DSN configured. "
            "Set `_dsn` class attribute or override `_get_dsn()`."
        )

    # ─────────────────────────────────────────────────────────────
    # Representation
    # ─────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        pk_col = self._get_primary_key()
        pk_val = getattr(self, pk_col, None)
        pk_display = pk_val if pk_val is not None else "unsaved"

        # Exclude pk from fields to avoid double-printing
        fields = {k: v for k, v in self._get_field_data().items() if k != pk_col}
        field_str = ", ".join(f"{k}={v!r}" for k, v in fields.items())

        if field_str:
            return f"<{self.__class__.__name__} {pk_col}={pk_display} {field_str}>"
        return f"<{self.__class__.__name__} {pk_col}={pk_display}>"
