"""Size limits. One definition for every way files get into a family: import, uploads, autosave, publish."""

from protean import config
from protean.core.errors import TOO_LARGE, AppError


def check_limits(file_count: int, total_bytes: int) -> None:
    """Raises TOO_LARGE when a family has too many files or too many bytes."""
    if file_count > config.MAX_FILES:
        raise AppError(413, TOO_LARGE, f"Too many files (limit {config.MAX_FILES}).")
    if total_bytes > config.MAX_UNZIPPED_BYTES:
        mb = config.MAX_UNZIPPED_BYTES // 1_000_000
        raise AppError(413, TOO_LARGE, f"The family is larger than {mb} MB.")
