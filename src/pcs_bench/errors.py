"""pcs-bench error types."""


class PcsBenchError(Exception):
    """Base error for pcs-bench."""


class ConfigError(PcsBenchError):
    """Configuration is invalid or missing."""


class SuiteNotFoundError(PcsBenchError):
    """Requested benchmark suite does not exist."""


class CaseNotFoundError(PcsBenchError):
    """Requested benchmark case does not exist."""


class AdapterUnavailableError(PcsBenchError):
    """External repo CLI is not available."""


class ValidationError(PcsBenchError):
    """Schema or case validation failed."""


class ThresholdViolationError(PcsBenchError):
    """CI threshold was not met."""

    def __init__(
        self,
        metric: str,
        score: float,
        threshold: float,
        failed_cases: list[str],
        *,
        message: str | None = None,
    ):
        self.metric = metric
        self.score = score
        self.threshold = threshold
        self.failed_cases = failed_cases
        self.message = message or (
            f"{metric} below threshold: score={score:.2f}, threshold={threshold:.2f}"
        )
        super().__init__(self.message)


class ReportNotFoundError(PcsBenchError):
    """Benchmark report file not found."""
