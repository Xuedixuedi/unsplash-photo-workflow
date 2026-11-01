"""Project errors. Messages are safe to print after redaction."""


class UpwError(Exception):
    """Expected failure the CLI can report without a traceback."""


class RateLimitError(UpwError):
    """The Unsplash hourly budget is exhausted and the wait is too long to sleep."""

    def __init__(self, message: str, retry_at: float | None = None) -> None:
        super().__init__(message)
        self.retry_at = retry_at
