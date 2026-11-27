"""Archive checks: size limits and safe unpacking of a downloaded zip or an uploaded folder."""

import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from protean.core.errors import GITHUB_ERROR, INVALID_FAMILY, INVALID_REQUEST, AppError
from protean.core.patterns import REPO_PATTERN
from protean.family.validation.limits import check_limits

CHUNK = 64 * 1024


def target(folder: Path, name: str) -> Path | None:
    """Where an entry goes, or None to skip it. Drops the top folder; refuses escapes."""
    # GitHub wraps everything in <owner>-<repo>-<sha>/; a browser upload starts with the folder name
    parts = PurePosixPath(name).parts[1:]
    if not parts:
        return None
    if "\\" in name or PurePosixPath(name).is_absolute() or ".." in parts:
        raise AppError(422, INVALID_FAMILY, f"Refused an unsafe path: {name}")
    return folder.joinpath(*parts)


def folder_name(names: list[str]) -> str:
    """The name of the uploaded folder: the first part of every file's relative path."""
    parts = [PurePosixPath(n).parts for n in names]
    if not parts or any(len(p) < 2 for p in parts):
        raise AppError(422, INVALID_REQUEST, "Choose a family folder, not loose files.")
    tops = {p[0] for p in parts}
    if len(tops) != 1:
        raise AppError(422, INVALID_REQUEST, "Choose one folder at a time.")
    (top,) = tops
    if not re.fullmatch(REPO_PATTERN, top) or set(top) <= {"."}:
        raise AppError(
            422,
            INVALID_REQUEST,
            f"The folder name “{top}” can’t be used for a family. Use only letters, digits, "
            "dots, hyphens and underscores, and rename the folder.",
        )
    return top


def extract(zip_path: Path, folder: Path) -> int:
    """Unpack into `folder`, enforcing the limits on the bytes actually written. Returns the file count."""
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise AppError(502, GITHUB_ERROR, "GitHub sent a broken archive.") from exc
    files, total = 0, 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                raise AppError(
                    422,
                    INVALID_FAMILY,
                    f"The archive contains a symlink: {info.filename}",
                )
            dest = target(folder, info.filename)
            if dest is None:
                continue
            files += 1
            check_limits(files, total + info.file_size)  # Before writing
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, dest.open("wb") as out:
                while chunk := src.read(CHUNK):  # count real bytes, headers can lie
                    total += len(chunk)
                    check_limits(files, total)  # While writing
                    out.write(chunk)
    return files


def store_files(
    folder: Path,
    files: list[tuple[str, BinaryIO]],
    already: tuple[int, int] = (0, 0),
) -> int:
    """Write an uploaded folder, given as (relative path, content), into `folder`.

    The same rules as `extract`: the top folder is dropped, paths cannot escape, `.git` is
    skipped, and the limits apply to the bytes actually written, on top of `already` (the file
    count and bytes the rest of the family has). Returns the file count.
    """
    count, total = already
    written = 0
    for name, content in files:
        dest = target(folder, name)
        if dest is None or ".git" in PurePosixPath(name).parts:
            continue
        count += 1
        written += 1
        check_limits(count, total)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as out:
            while chunk := content.read(CHUNK):
                total += len(chunk)
                check_limits(count, total)
                out.write(chunk)
    return written
