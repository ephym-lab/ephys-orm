"""
Field Descriptors

Special objects that control attribute access, enabling validation,
type conversion, and schema introspection.
"""

from typing import Any, Optional, List, Type
from datetime import datetime
from src.ephyorm.exceptions import ValueValidationError


class Field:
    """
    Base descriptor for model fields.

    Usage:
        class User(Model):
            name = StringField(max_length=100)
            age = IntegerField(null=True)
            is_active = BooleanField(default=True)
    """

    def __init__(
        self,
        null: bool = False,
        default: Any = None,
        max_length: Optional[int] = None,
        choices: Optional[List[Any]] = None,
    ):
        self.null = null
        self.default = default
        self.max_length = max_length
        self.choices = choices
        self.name: Optional[str] = None  # set by __set_name__

    def __set_name__(self, owner: Type, name: str) -> None:
        """
        Called when the descriptor is assigned as a class attribute.
        Stores the field name so we know which key to use in instance.__dict__.
        """
        self.name = name

    def __get__(self, instance: Any, owner: Type) -> Any:
        """
        Called when accessing instance.field_name.
        Returns the value from instance.__dict__, or default if not set.
        """
        if instance is None:
            # Accessing via class: User.name → returns the descriptor itself
            return self
        # Return from __dict__, or default if missing
        return instance.__dict__.get(self.name, self.default)

    def __set__(self, instance: Any, value: Any) -> None:
        """
        Called when assigning instance.field_name = value.
        Validates, converts, then stores in instance.__dict__.
        """
        # Apply default if value is None and field has a default
        if value is None and self.default is not None:
            value = self.default

        # Check null constraint
        if value is None and not self.null:
            raise ValueValidationError(
                f"Field '{self.name}' cannot be null"
            )

        # Skip validation/conversion for None (already checked null above)
        if value is not None:
            self.validate(value)
            value = self.to_db(value)

        instance.__dict__[self.name] = value

    def validate(self, value: Any) -> None:
        """Override in subclasses. Raise ValueValidationError if invalid."""
        if self.choices is not None and value not in self.choices:
            raise ValueValidationError(
                f"Field '{self.name}': value {value!r} not in choices {self.choices}"
            )

    def to_db(self, value: Any) -> Any:
        """Convert Python value to SQL-compatible value. Override in subclasses."""
        return value

    def from_db(self, value: Any) -> Any:
        """Convert SQL value back to Python. Override in subclasses."""
        return value


class IntegerField(Field):
    """Field for integer values."""

    def __init__(self, min_value: Optional[int] = None, max_value: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, value: Any) -> None:
        super().validate(value)
        if not isinstance(value, int):
            raise ValueValidationError(
                f"Field '{self.name}': expected int, got {type(value).__name__}"
            )
        if self.min_value is not None and value < self.min_value:
            raise ValueValidationError(
                f"Field '{self.name}': value {value} < min {self.min_value}"
            )
        if self.max_value is not None and value > self.max_value:
            raise ValueValidationError(
                f"Field '{self.name}': value {value} > max {self.max_value}"
            )

    def to_db(self, value: Any) -> Any:
        return int(value)

    def from_db(self, value: Any) -> Any:
        return int(value) if value is not None else None


class StringField(Field):
    """Field for string values."""

    def validate(self, value: Any) -> None:
        super().validate(value)
        if not isinstance(value, str):
            raise ValueValidationError(
                f"Field '{self.name}': expected str, got {type(value).__name__}"
            )
        if self.max_length is not None and len(value) > self.max_length:
            raise ValueValidationError(
                f"Field '{self.name}': length {len(value)} > max {self.max_length}"
            )

    def to_db(self, value: Any) -> Any:
        return str(value)

    def from_db(self, value: Any) -> Any:
        return str(value) if value is not None else None


class BooleanField(Field):
    """Field for boolean values."""

    def validate(self, value: Any) -> None:
        super().validate(value)
        if not isinstance(value, bool):
            raise ValueValidationError(
                f"Field '{self.name}': expected bool, got {type(value).__name__}"
            )

    def to_db(self, value: Any) -> Any:
        # PostgreSQL accepts True/False directly
        return bool(value)

    def from_db(self, value: Any) -> Any:
        if value is None:
            return None
        # PostgreSQL returns True/False or 't'/'f' for some drivers
        if isinstance(value, bool):
            return value
        return value in (1, 't', 'true', 'True', 'TRUE')


class DateTimeField(Field):
    """Field for datetime values."""

    def validate(self, value: Any) -> None:
        super().validate(value)
        if not isinstance(value, datetime):
            raise ValueValidationError(
                f"Field '{self.name}': expected datetime, got {type(value).__name__}"
            )

    def to_db(self, value: Any) -> Any:
        # PostgreSQL accepts ISO format strings
        return value.isoformat() if isinstance(value, datetime) else value

    def from_db(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # PostgreSQL returns strings like '2024-01-15 10:30:00'
            return datetime.fromisoformat(value.replace(' ', 'T'))
        return value
