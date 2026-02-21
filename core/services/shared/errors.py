class ServiceError(Exception):
    """Base class for service-layer errors."""


class ValidationError(ServiceError):
    """Raised when input payload is invalid."""


class ExternalDependencyError(ServiceError):
    """Raised when external dependency (LLM/vector/IO) fails."""


class PermissionDeniedError(ServiceError):
    """Raised when actor is not allowed to access resource."""

