from __future__ import annotations

from dataclasses import dataclass

from core.models import AudioProcess
from core.process_service import ProcessService


@dataclass
class _FakeProc:
    pid: int
    name_value: str
    parent_pid: int | None
    store: dict[int, "_FakeProc"]

    def name(self) -> str:
        return self.name_value

    def parent(self):
        if self.parent_pid is None:
            return None
        return self.store[self.parent_pid]


class _Backend:
    def __init__(self, processes: list[AudioProcess]) -> None:
        self._processes = processes

    def enumerate_audio_processes(self) -> list[AudioProcess]:
        return self._processes


def test_resolve_capture_target_maps_browser_like_pid(monkeypatch) -> None:
    proc_store: dict[int, _FakeProc] = {}
    proc_store[500] = _FakeProc(500, "msedge.exe", None, proc_store)
    proc_store[700] = _FakeProc(700, "msedge.exe", 500, proc_store)
    proc_store[710] = _FakeProc(710, "msedge.exe", 500, proc_store)

    monkeypatch.setattr("core.process_service.psutil.pid_exists", lambda pid: pid in proc_store)
    monkeypatch.setattr("core.process_service.psutil.Process", lambda pid: proc_store[pid])

    service = ProcessService(
        _Backend([AudioProcess(pid=710, name="msedge.exe"), AudioProcess(pid=800, name="chrome.exe")])
    )

    resolved = service.resolve_capture_target(700)
    assert resolved.ok
    assert resolved.capture_pid == 710
    assert "自动改用" in resolved.hint


def test_resolve_capture_target_keeps_exact_audio_pid(monkeypatch) -> None:
    proc_store: dict[int, _FakeProc] = {}
    proc_store[321] = _FakeProc(321, "chrome.exe", None, proc_store)

    monkeypatch.setattr("core.process_service.psutil.pid_exists", lambda pid: pid in proc_store)
    monkeypatch.setattr("core.process_service.psutil.Process", lambda pid: proc_store[pid])

    service = ProcessService(_Backend([AudioProcess(pid=321, name="chrome.exe")]))
    resolved = service.resolve_capture_target(321)
    assert resolved.ok
    assert resolved.capture_pid == 321
    assert resolved.hint == ""


def test_resolve_capture_target_returns_hint_when_no_audio_session(monkeypatch) -> None:
    proc_store: dict[int, _FakeProc] = {}
    proc_store[999] = _FakeProc(999, "firefox.exe", None, proc_store)

    monkeypatch.setattr("core.process_service.psutil.pid_exists", lambda pid: pid in proc_store)
    monkeypatch.setattr("core.process_service.psutil.Process", lambda pid: proc_store[pid])

    service = ProcessService(_Backend([]))
    resolved = service.resolve_capture_target(999)
    assert resolved.ok
    assert resolved.capture_pid == 999
    assert "活跃音频会话" in resolved.hint

