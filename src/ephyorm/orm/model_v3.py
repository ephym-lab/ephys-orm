"""
Model with Field Descriptors
"""

from typing import Any, Dict, List, Optional, Type, TypeVar, Iterator
from src.ephyorm.db.connection import PostgresConnection
from src.ephyorm.exceptions import ValueValidationError, RuntimeConfigError
from src.ephyorm.orm.fields import Field

T = TypeVar("T", bound="Model")


class ModelMeta(type):
    """
    Metaclass that collects Field descriptors into _meta.fields.
    Runs when a Model subclass is defined.
    """

    def __new__(mcs, name: str, bases: tuple, namespace: dict):
        cls = super().__new__(mcs, name, bases, namespace)

        # Collect fields from class attributes
        fields: Dict[str, Field] = {}
        for base in bases:
            if hasattr(base, '_meta') and hasattr(base._meta, 'fields'):
                fields.update(base._meta.fields)

        for key, value in namespace.items():
            if isinstance(value, Field):
                fields[key] = value

        # Simple _meta container
        class Meta:
            pass
        meta = Meta()
        meta.fields = fields
        meta.table_name = getattr(cls, '__table__', None) or name.lower() + 's'
        meta.primary_key = getattr(cls, '__primary_key__', 'id')
        cls._meta = meta

        return cls


class Model(metaclass=ModelMeta):
    """
    Base ORM Model class with Field descriptor support.

    Usage:
        class User(Model):
            id = IntegerField(null=False)
            name = StringField(max_length=100)
            email = StringField(max_length=100)
            is_active = BooleanField(default=True)

        user = User(name="Alice", email="alice@example.com")
        user.save()
    """

    __table__: str = ""
    __primary_key__: str = "id"

    def __init__(self, **kwargs: Any):
        pk_col = self._get_primary_key()

        # Set all non-pk fields to None first (triggers descriptor __set__)
        # Skip pk — the database generates it via SERIAL
        for name, field in self._meta.fields.items():
            if name == pk_col:
                continue  # DB generates pk, don't trigger validation
            if name not in kwargs:
                setattr(self, name, None)

        # Set provided values (triggers __set__ for validation/conversion)
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def _get_table_name(cls) -> str:
        return cls._meta.table_name

    @classmethod
    def _get_primary_key(cls) -> str:
        return cls._meta.primary_key

    @classmethod
    def _get_fields(cls) -> Dict[str, Field]:
        """Return all Field descriptors for this model."""
        return cls._meta.fields

    @classmethod
    def _from_row(cls: Type[T], row: Dict[str, Any]) -> T:
        """Create a model instance from a database row, applying from_db()."""
        data = {}
        for name, field in cls._get_fields().items():
            if name in row:
                data[name] = field.from_db(row[name])
            else:
                data[name] = field.default
        return cls(**data)

    def _get_field_data(self) -> Dict[str, Any]:
        """
        Return field values for SQL operations.
        Only includes fields defined as descriptors, not arbitrary __dict__ entries.
        """
        fields = {}
        pk_col = self._get_primary_key()
        for name, field in self._get_fields().items():
            # Skip primary key if not set (SERIAL will generate it)
            if name == pk_col and name not in self.__dict__:
                continue
            value = self.__dict__.get(name, field.default)
            if value is not None:
                fields[name] = value
        return fields

    # ─────────────────────────────────────────────────────────────
    # READ operations (using Query builder)
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def get(cls: Type[T], pk: Any) -> Optional[T]:
        from src.ephyorm.orm.query import Query
        return Query(cls).where(**{cls._get_primary_key(): pk}).first()

    @classmethod
    def all(cls: Type[T]) -> List[T]:
        from src.ephyorm.orm.query import Query
        return Query(cls).all()

    @classmethod
    def filter(cls: Type[T], **kwargs: Any) -> List[T]:
        from src.ephyorm.orm.query import Query
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
        fields = self._get_field_data()

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
        fields = self._get_field_data()

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
        fields = {k: v for k, v in self.__dict__.items() if k != pk_col and not k.startswith('_')}
        field_str = ", ".join(f"{k}={v!r}" for k, v in fields.items())
        if field_str:
            return f"<{self.__class__.__name__} {pk_col}={pk_display} {field_str}>"
        return f"<{self.__class__.__name__} {pk_col}={pk_display}>"
