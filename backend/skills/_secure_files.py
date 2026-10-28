"""Platform-specific file primitives for the single Skill Registry loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class SecureFiles(Protocol):
    def require_support(self) -> None: ...
    def open_root(self, path: Path) -> int: ...
    def open_directory_at(self, parent: int, name: str) -> int: ...
    def open_file_at(self, parent: int, name: str) -> int: ...
    def stat_mode_at(self, parent: int, name: str) -> int: ...
    def mode(self, handle: int) -> int: ...
    def size(self, handle: int) -> int: ...
    def listdir(self, handle: int) -> list[str]: ...
    def read(self, handle: int, count: int) -> bytes: ...
    def dup(self, handle: int) -> int: ...
    def close(self, handle: int) -> None: ...


class PosixFiles:
    def require_support(self) -> None:
        if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
            raise OSError("skill registry requires O_DIRECTORY and O_NOFOLLOW support")

    @staticmethod
    def _flags(*, directory: bool) -> int:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW")
        return flags | (
            getattr(os, "O_DIRECTORY") if directory else getattr(os, "O_NONBLOCK", 0)
        )

    def open_root(self, path: Path) -> int:
        return os.open(path, self._flags(directory=True))

    def open_directory_at(self, parent: int, name: str) -> int:
        return os.open(name, self._flags(directory=True), dir_fd=parent)

    def open_file_at(self, parent: int, name: str) -> int:
        return os.open(name, self._flags(directory=False), dir_fd=parent)

    def stat_mode_at(self, parent: int, name: str) -> int:
        return os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode

    def mode(self, handle: int) -> int:
        return os.fstat(handle).st_mode

    def size(self, handle: int) -> int:
        return os.fstat(handle).st_size

    def listdir(self, handle: int) -> list[str]:
        return os.listdir(handle)

    def read(self, handle: int, count: int) -> bytes:
        return os.read(handle, count)

    def dup(self, handle: int) -> int:
        return os.dup(handle)

    def close(self, handle: int) -> None:
        os.close(handle)


def secure_files() -> SecureFiles:
    # Select by platform, never fall back to path-based reads after an error.
    if os.name == "nt":
        from backend.skills._windows_files import WindowsFiles

        return WindowsFiles()
    return PosixFiles()
