class ExperimentSpecError(Exception):
    """Base class for experiment specification errors."""
    pass

class SpecValidationError(ExperimentSpecError):
    """Raised when the experiment specification violates the schema."""
    pass
