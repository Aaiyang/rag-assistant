"""Windows handle-relative, non-reparsing reads for Skill Registry files.

NtCreateFile resolves each single child name against an opened directory handle.
All reparse points are inspected without following them. Handles deny sharing
for writes/deletion until the loader has read and frozen the source bytes.
"""

from __future__ import annotations

import ctypes
import stat
import struct
from ctypes import wintypes
from pathlib import Path


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_UnicodeString)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", ctypes.c_void_p),
        ("SecurityQualityOfService", ctypes.c_void_p),
    ]


class _IoStatusValue(ctypes.Union):
    _fields_ = [("Status", wintypes.LONG), ("Pointer", ctypes.c_void_p)]


class _IoStatusBlock(ctypes.Structure):
    _fields_ = [("Result", _IoStatusValue), ("Information", ctypes.c_size_t)]


class _FileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD),
        ("creation_time", wintypes.FILETIME),
        ("access_time", wintypes.FILETIME),
        ("write_time", wintypes.FILETIME),
        ("volume_serial", wintypes.DWORD),
        ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("index_high", wintypes.DWORD),
        ("index_low", wintypes.DWORD),
    ]


_READ_ATTRIBUTES = 0x80
_SYNCHRONIZE = 0x100000
_SHARE_READ = 1
_OPEN_REPARSE_POINT = 0x200000
_SYNCHRONOUS_IO_NONALERT = 0x20
_DIRECTORY = 0x10
_REPARSE_POINT = 0x400
_NO_MORE_FILES = 0x80000006


class WindowsFiles:
    def __init__(self) -> None:
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._nt = ctypes.WinDLL("ntdll")
        self._kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        self._kernel.CreateFileW.restype = wintypes.HANDLE
        self._kernel.GetFileInformationByHandle.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_FileInformation),
        ]
        self._kernel.GetFileInformationByHandle.restype = wintypes.BOOL
        self._kernel.GetFileType.argtypes = [wintypes.HANDLE]
        self._kernel.GetFileType.restype = wintypes.DWORD
        self._kernel.ReadFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        self._kernel.ReadFile.restype = wintypes.BOOL
        self._kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel.CloseHandle.restype = wintypes.BOOL
        self._kernel.GetCurrentProcess.argtypes = []
        self._kernel.GetCurrentProcess.restype = wintypes.HANDLE
        self._kernel.DuplicateHandle.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._kernel.DuplicateHandle.restype = wintypes.BOOL
        self._nt.NtCreateFile.argtypes = [
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.DWORD,
            ctypes.POINTER(_ObjectAttributes),
            ctypes.POINTER(_IoStatusBlock),
            ctypes.c_void_p,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
        ]
        self._nt.NtCreateFile.restype = wintypes.LONG
        self._nt.NtQueryDirectoryFile.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_IoStatusBlock),
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.c_int,
            ctypes.c_ubyte,
            ctypes.c_void_p,
            ctypes.c_ubyte,
        ]
        self._nt.NtQueryDirectoryFile.restype = wintypes.LONG
        self._nt.RtlNtStatusToDosError.argtypes = [wintypes.LONG]
        self._nt.RtlNtStatusToDosError.restype = wintypes.ULONG

    def require_support(self) -> None:
        # Required entry points are bound during construction; no fallback.
        pass

    def _check_status(self, status: int) -> None:
        if status < 0:
            raise ctypes.WinError(self._nt.RtlNtStatusToDosError(status))

    def open_root(self, path: Path) -> int:
        name = str(path)
        if not name.startswith("\\\\?\\"):
            name = (
                "\\\\?\\UNC\\" + name[2:]
                if name.startswith("\\\\")
                else "\\\\?\\" + name
            )
        handle = self._kernel.CreateFileW(
            name,
            1 | _READ_ATTRIBUTES | _SYNCHRONIZE,
            _SHARE_READ,
            None,
            3,
            0x02000000 | 0x00200000,
            None,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        )
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)

    def _open_at(self, parent: int, name: str, *, directory: bool | None) -> int:
        if not name or name in {".", ".."} or any(c in name for c in "/\\:\x00"):
            raise OSError("only a single relative file name is allowed")
        length = len(name.encode("utf-16-le"))
        if length > 65532:
            raise OSError("file name exceeds UNICODE_STRING bounds")
        buffer = ctypes.create_unicode_buffer(name)
        unicode_name = _UnicodeString(
            length, length + 2, ctypes.cast(buffer, wintypes.LPWSTR)
        )
        attributes = _ObjectAttributes(
            Length=ctypes.sizeof(_ObjectAttributes),
            RootDirectory=parent,
            ObjectName=ctypes.pointer(unicode_name),
            Attributes=0x40,  # CASE_INSENSITIVE
        )
        handle = wintypes.HANDLE()
        status_block = _IoStatusBlock()
        options = _OPEN_REPARSE_POINT | _SYNCHRONOUS_IO_NONALERT
        if directory is not None:
            options |= 1 if directory else 0x40  # DIRECTORY_FILE / NON_DIRECTORY_FILE
        status = self._nt.NtCreateFile(
            ctypes.byref(handle),
            1 | _READ_ATTRIBUTES | _SYNCHRONIZE,
            ctypes.byref(attributes),
            ctypes.byref(status_block),
            None,
            0,
            _SHARE_READ,
            1,
            options,
            None,
            0,  # FILE_OPEN: never create or truncate
        )
        self._check_status(status)
        if handle.value is None:
            raise OSError("NtCreateFile returned an empty handle")
        return handle.value

    def open_directory_at(self, parent: int, name: str) -> int:
        return self._open_at(parent, name, directory=True)

    def open_file_at(self, parent: int, name: str) -> int:
        return self._open_at(parent, name, directory=False)

    def _information(self, handle: int) -> _FileInformation:
        info = _FileInformation()
        if not self._kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info

    def stat_mode_at(self, parent: int, name: str) -> int:
        handle = self._open_at(parent, name, directory=None)
        try:
            return self.mode(handle)
        finally:
            self.close(handle)

    def mode(self, handle: int) -> int:
        attributes = self._information(handle).attributes
        if attributes & _REPARSE_POINT:
            return stat.S_IFLNK
        if self._kernel.GetFileType(handle) != 1:  # FILE_TYPE_DISK
            raise OSError("skill source must be a disk file or directory")
        return stat.S_IFDIR if attributes & _DIRECTORY else stat.S_IFREG

    def size(self, handle: int) -> int:
        info = self._information(handle)
        return (info.size_high << 32) | info.size_low

    def listdir(self, handle: int) -> list[str]:
        names: list[str] = []
        buffer = ctypes.create_string_buffer(65536)
        first = True
        while True:
            block = _IoStatusBlock()
            status = self._nt.NtQueryDirectoryFile(
                handle,
                None,
                None,
                None,
                ctypes.byref(block),
                buffer,
                len(buffer),
                12,
                False,
                None,
                first,  # FileNamesInformation
            )
            first = False
            if status & 0xFFFFFFFF == _NO_MORE_FILES:
                return names
            self._check_status(status)
            data = buffer.raw[: block.Information]
            if not data:
                raise OSError("directory enumeration returned no entries")
            offset = 0
            while True:
                if offset + 12 > len(data):
                    raise OSError("invalid directory enumeration header")
                next_offset, _, name_length = struct.unpack_from("<III", data, offset)
                end = offset + 12 + name_length
                if name_length % 2 or end > len(data):
                    raise OSError("invalid directory enumeration name")
                name = data[offset + 12 : end].decode("utf-16-le")
                if name not in {".", ".."}:
                    names.append(name)
                if not next_offset:
                    break
                if next_offset < 12 + name_length or offset + next_offset >= len(data):
                    raise OSError("invalid directory enumeration offset")
                offset += next_offset

    def read(self, handle: int, count: int) -> bytes:
        buffer = ctypes.create_string_buffer(count)
        read_count = wintypes.DWORD()
        if not self._kernel.ReadFile(
            handle, buffer, count, ctypes.byref(read_count), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[: read_count.value]

    def dup(self, handle: int) -> int:
        process = self._kernel.GetCurrentProcess()
        duplicate = wintypes.HANDLE()
        if not self._kernel.DuplicateHandle(
            process,
            handle,
            process,
            ctypes.byref(duplicate),
            0,
            False,
            2,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if duplicate.value is None:
            raise OSError("DuplicateHandle returned an empty handle")
        return duplicate.value

    def close(self, handle: int) -> None:
        if not self._kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())
