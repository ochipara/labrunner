class DatasetManifestError(Exception):
    """Base class for dataset manifest errors."""
    pass

class DatasetNotFound(DatasetManifestError):
    pass

class DatasetUnreadable(DatasetManifestError):
    pass

class ManifestMalformed(DatasetManifestError):
    pass

class DatasetVerificationError(DatasetManifestError):
    pass
