"""User-facing error types. The API layer (Phase 9) maps these to HTTP responses."""


class DataValidationError(Exception):
    """Raised when uploaded data cannot be processed. Message is safe to show users."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "details": self.details}
