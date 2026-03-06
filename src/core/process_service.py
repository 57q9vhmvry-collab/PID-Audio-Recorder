from __future__ import annotations

from dataclasses import dataclass

import psutil

from .models import AudioProcess, CaptureBackend


@dataclass(slots=True)
class PidValidationResult:
    ok: bool
    pid: int | None = None
    process_name: str = ""
    message: str = ""


@dataclass(slots=True)
class CaptureTargetResolution:
    ok: bool
    capture_pid: int | None = None
    process_name: str = ""
    message: str = ""
    hint: str = ""


class ProcessService:
    def __init__(self, backend: CaptureBackend) -> None:
        self.backend = backend

    def list_audio_processes(self, keyword: str = "") -> list[AudioProcess]:
        processes = self.backend.enumerate_audio_processes()
        normalized = keyword.strip().lower()
        dedup: dict[int, AudioProcess] = {}
        for item in processes:
            dedup[item.pid] = item

        values = list(dedup.values())
        if normalized:
            values = [
                item
                for item in values
                if normalized in item.name.lower()
                or normalized in item.window_title.lower()
                or normalized in str(item.pid)
            ]

        return sorted(values, key=lambda x: (x.name.lower(), x.pid))

    @staticmethod
    def parse_pid(raw_value: str) -> int:
        value = raw_value.strip()
        if not value:
            raise ValueError("请输入 PID")
        pid = int(value)
        if pid <= 0:
            raise ValueError("PID 必须大于 0")
        return pid

    @staticmethod
    def validate_pid(pid: int) -> PidValidationResult:
        if pid <= 0:
            return PidValidationResult(ok=False, message="PID 必须大于 0")
        if not psutil.pid_exists(pid):
            return PidValidationResult(ok=False, message=f"PID {pid} 不存在")

        try:
            process = psutil.Process(pid)
            return PidValidationResult(ok=True, pid=pid, process_name=process.name())
        except psutil.Error as exc:
            return PidValidationResult(ok=False, message=f"无法访问 PID {pid}: {exc}")

    def resolve_capture_target(self, input_pid: int) -> CaptureTargetResolution:
        validation = self.validate_pid(input_pid)
        if not validation.ok or validation.pid is None:
            return CaptureTargetResolution(ok=False, message=validation.message or "PID 无效")

        process_name = validation.process_name

        try:
            active_audio = self.list_audio_processes()
        except Exception as exc:
            return CaptureTargetResolution(
                ok=True,
                capture_pid=input_pid,
                process_name=process_name,
                hint=f"无法读取音频会话列表，将直接尝试 PID {input_pid}：{exc}",
            )

        for item in active_audio:
            if item.pid == input_pid:
                return CaptureTargetResolution(
                    ok=True,
                    capture_pid=input_pid,
                    process_name=process_name,
                )

        same_name = [item for item in active_audio if item.name.lower() == process_name.lower()]
        if same_name:
            selected = self._pick_most_related_pid(input_pid, same_name)
            return CaptureTargetResolution(
                ok=True,
                capture_pid=selected.pid,
                process_name=selected.name,
                hint=(
                    f"输入 PID {input_pid} 当前无活跃音频会话，已自动改用"
                    f" {selected.name} ({selected.pid}) 进行录制。"
                ),
            )

        return CaptureTargetResolution(
            ok=True,
            capture_pid=input_pid,
            process_name=process_name,
            hint=(
                f"PID {input_pid} 当前不在活跃音频会话里。"
                "若启动失败，请先让该进程发声后再重试，或从左侧列表选择。"
            ),
        )

    def _pick_most_related_pid(self, target_pid: int, candidates: list[AudioProcess]) -> AudioProcess:
        def score(candidate_pid: int) -> tuple[int, int]:
            return (self._process_tree_distance(target_pid, candidate_pid), candidate_pid)

        return min(candidates, key=lambda item: score(item.pid))

    @staticmethod
    def _process_tree_distance(pid_a: int, pid_b: int) -> int:
        if pid_a == pid_b:
            return 0

        chain_a = ProcessService._ancestor_depth_map(pid_a)
        chain_b = ProcessService._ancestor_depth_map(pid_b)

        common = set(chain_a.keys()) & set(chain_b.keys())
        if common:
            return min(chain_a[p] + chain_b[p] for p in common)

        return 1_000_000 + abs(pid_a - pid_b)

    @staticmethod
    def _ancestor_depth_map(pid: int) -> dict[int, int]:
        result: dict[int, int] = {}
        try:
            proc = psutil.Process(pid)
        except psutil.Error:
            return {pid: 0}

        depth = 0
        while True:
            result[proc.pid] = depth
            try:
                parent = proc.parent()
            except psutil.Error:
                break
            if parent is None or parent.pid == proc.pid:
                break
            proc = parent
            depth += 1

        return result

