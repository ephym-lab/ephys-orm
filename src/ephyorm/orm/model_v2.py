"""
Base Model & Result Mapping
Updated for Query Builder integration
"""

from typing import Any, Dict, List, Optional, Type, TypeVar
from ephyorm.db.connection import PostgresConnection
from ephyorm.exceptions import ValueValidationError, RuntimeConfigError

T = TypeVar("T", bound="Model")


class Model:
    """
    Base ORM Model class.
    """

    __table__: str = ""
    __primary_key__: str = "id"

    def __init__(self, **kwargs: Any):
        pk = self._get_primary_key()
        if pk not in kwargs:
            setattr(self, pk, None)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def _get_field_data(self, exclude_none_pk: bool = True) -> Dict[str, Any]:
        fields = {}
        pk_col = self._get_primary_key()
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue
            if key in ("__table__", "__primary_key__"):
                continue
            if exclude_none_pk and key == pk_col and value is None:
                continue
            fields[key] = value
        return fields

    @classmethod
    def _get_table_name(cls) -> str:
        if cls.__table__:
            return cls.__table__
        return cls.__name__.lower() + "s"

    @classmethod
    def _get_primary_key(cls) -> str:
        return cls.__primary_key__ or "id"

    @classmethod
    def _from_row(cls: Type[T], row: Dict[str, Any]) -> T:
        return cls(**row)

    # ─────────────────────────────────────────────────────────────
    # READ operations (using Query builder)
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def get(cls: Type[T], pk: Any) -> Optional[T]:
        from ephyorm.orm.query import Query
        return Query(cls).where(**{cls._get_primary_key(): pk}).first()

    @classmethod
    def all(cls: Type[T]) -> List[T]:
        from ephyorm.orm.query import Query
        return Query(cls).all()

    @classmethod
    def filter(cls: Type[T], **kwargs: Any) -> List[T]:
        from ephyorm.orm.query import Query
        return Query(cls).where(**kwargs).all()

    # ─────────────────────────────────────────────────────────────
    # WRITE operations
    # ─────────────────────────────────────────────────────────────

    def save(self) -> None:
        pk_col = self._get_primary_key()
        pk_val = getattr(self, pk_col, None)
        if pk_val is None:
            self._insert()
        else:
            self._update()

    def _insert(self) -> None:
        table = self._get_table_name()
        pk_col = self._get_primary_key()
        fields = self._get_field_data(exclude_none_pk=True)

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
            if rows:
                setattr(self, pk_col, rows[0][pk_col])

    def _update(self) -> None:
        table = self._get_table_name()
        pk_col = self._get_primary_key()
        pk_val = getattr(self, pk_col)
        fields = self._get_field_data(exclude_none_pk=False)

        # Forbid changing the primary key
        if pk_col in fields and fields[pk_col] != pk_val:
            raise ValueValidationError(
                f"Cannot update primary key '{pk_col}'. "
                f"Current: {pk_val}, attempted: {fields[pk_col]}"
            )

        fields.pop(pk_col, None)

        if not fields:
            raise ValueValidationError("No fields to update")

        set_clauses = []
        values = []
        for col, val in fields.items():
            set_clauses.append(f"{col} = %s")
            values.append(val)
        values.append(pk_val)

        set_sql = ", ".join(set_clauses)

        with PostgresConnection(self._get_dsn()) as conn:
            conn.execute(
                f"UPDATE {table} SET {set_sql} WHERE {pk_col} = %s",
                tuple(values)
            )
            conn.commit()

    def delete(self) -> None:
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

    @classmethod
    def create(cls: Type[T], **kwargs: Any) -> T:
        instance = cls(**kwargs)
        instance.save()
        return instance

    @classmethod
    def _get_dsn(cls) -> str:
        if hasattr(cls, "_dsn") and cls._dsn:
            return cls._dsn
        raise RuntimeConfigError(
            f"{cls.__name__} has no DSN configured. "
            "Set `_dsn` class attribute or override `_get_dsn()`."
        )

    def __repr__(self) -> str:
        pk_col = self._get_primary_key()
        pk_val = getattr(self, pk_col, None)
        pk_display = pk_val if pk_val is not None else "unsaved"
        fields = {k: v for k, v in self._get_field_data(exclude_none_pk=False).items() if k != pk_col}
        field_str = ", ".join(f"{k}={v!r}" for k, v in fields.items())
        if field_str:
            return f"<{self.__class__.__name__} {pk_col}={pk_display} {field_str}>"
        return f"<{self.__class__.__name__} {pk_col}={pk_display}>"
