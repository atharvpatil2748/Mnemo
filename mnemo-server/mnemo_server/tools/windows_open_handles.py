"""Read-only Windows Restart Manager query for processes using exact files."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

_MORE_DATA = 234
_MAX_APP_NAME = 255
_MAX_SERVICE_NAME = 63


class _UniqueProcess(ctypes.Structure):
    _fields_ = [("process_id", wintypes.DWORD), ("start_time", wintypes.FILETIME)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("process", _UniqueProcess),
        ("app_name", wintypes.WCHAR * (_MAX_APP_NAME + 1)),
        ("service_short_name", wintypes.WCHAR * (_MAX_SERVICE_NAME + 1)),
        ("application_type", wintypes.DWORD),
        ("app_status", wintypes.ULONG),
        ("terminal_session_id", wintypes.DWORD),
        ("restartable", wintypes.BOOL),
    ]


def processes_using_files(paths: tuple[Path, ...]) -> tuple[int, ...]:
    """Ask the OS for exact file users; never close or signal a process.

    Any API failure aborts decommission rather than treating absence of
    evidence as no consumers. Paths must already have been resolved and
    allowlisted by the caller.
    """
    if os.name != "nt":
        raise RuntimeError("WINDOWS_FILE_USER_PROBE_UNAVAILABLE")
    if not paths:
        raise ValueError("file-user probe requires paths")
    library = ctypes.WinDLL("Rstrtmgr")
    session = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(33)
    started = library.RmStartSession(ctypes.byref(session), 0, key)
    if started:
        raise RuntimeError(f"WINDOWS_FILE_USER_PROBE_FAILED:{started}")
    try:
        names = (wintypes.LPCWSTR * len(paths))(*(str(path) for path in paths))
        registered = library.RmRegisterResources(session, len(paths), names, 0, None, 0, None)
        if registered:
            raise RuntimeError(f"WINDOWS_FILE_USER_PROBE_FAILED:{registered}")
        needed = wintypes.UINT()
        available = wintypes.UINT()
        reasons = wintypes.DWORD()
        status = library.RmGetList(
            session,
            ctypes.byref(needed),
            ctypes.byref(available),
            None,
            ctypes.byref(reasons),
        )
        if status == 0:
            return ()
        if status != _MORE_DATA:
            raise RuntimeError(f"WINDOWS_FILE_USER_PROBE_FAILED:{status}")
        available.value = needed.value
        entries = (_ProcessInfo * available.value)()
        status = library.RmGetList(
            session,
            ctypes.byref(needed),
            ctypes.byref(available),
            entries,
            ctypes.byref(reasons),
        )
        if status:
            raise RuntimeError(f"WINDOWS_FILE_USER_PROBE_FAILED:{status}")
        return tuple(
            sorted({int(entries[index].process.process_id) for index in range(available.value)})
        )
    finally:
        library.RmEndSession(session)
