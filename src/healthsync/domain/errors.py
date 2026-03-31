# backend/src/healthsync/domain/errors.py

from typing import Optional


class DomainError(Exception):
    """
    Base class for all domain-level exceptions.
    Allows consistent error handling across services.
    """
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(DomainError):
    """
    Raised when a requested resource does not exist.
    Example:
        Patient not found
        Visit not found
    """
    pass


class ValidationError(DomainError):
    """
    Raised when input data violates business/domain rules.
    Example:
        Device does not belong to patient
        Visit already ended
    """
    pass


class PermissionDeniedError(DomainError):
    """
    Raised when a user does not have permission
    to perform an action at the domain level.
    (Different from authentication failure)
    """
    pass
