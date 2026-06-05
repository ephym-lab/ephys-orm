class EphyormError(Exception):
    """Base exception for ephyorm."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class ModelError(EphyormError):
    """Exception for model operations."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class DoesNotExistError(ModelError):
    """Exception for when a record does not exist."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class DBError(EphyormError):
    """Exception for database operations."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class RuntimeConfigError(EphyormError):
    """Exception for runtime configuration errors."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class ValueValidationError(EphyormError):
    """Exception for invalid values."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class QueryError(EphyormError):
    """Exception for query builder errors."""
    def __init__(self, message: str) -> None:
        super().__init__(message)

class ExecutionError(EphyormError):
    """Exception for query execution errors."""
    def __init__(self, message: str) -> None:
        super().__init__(message)