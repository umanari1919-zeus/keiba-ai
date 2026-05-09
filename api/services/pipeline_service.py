"""
Pipeline 実行管理サービス

asyncio.create_subprocess_exec で run_all.py をラップし、
trace_id ベースで実行状態を管理する。
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ProcessHandle:
    """実行プロセス情報"""
    trace_id: str
    proc: asyncio.subprocess.Process
    pattern: str
    start_time: datetime
    log_path: Path
    end_time: Optional[datetime] = None
    exit_code: Optional[int] = None


class PipelineExecutor:
    """Popen + trace_id 管理"""

    _processes: Dict[str, ProcessHandle] = {}

    @classmethod
    async def run_pipeline(cls, pattern: str = "v2") -> str:
        """
        Pipeline 非同期実行

        Args:
            pattern: "v2", "morning", "weekly", "results"

        Returns:
            trace_id: 実行識別子
        """
        # パターン検証
        valid_patterns = ["v2", "morning", "weekly", "results"]
        if pattern not in valid_patterns:
            raise ValueError(f"Invalid pattern. Must be one of {valid_patterns}")

        # trace_id 生成
        trace_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        log_path = Path("logs") / f"{trace_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # subprocess 実行
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "run_all.py", f"--{pattern}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start pipeline: {e}")

        # ハンドル + メタデータ保存
        handle = ProcessHandle(
            trace_id=trace_id,
            proc=proc,
            pattern=pattern,
            start_time=datetime.now(),
            log_path=log_path,
        )
        cls._processes[trace_id] = handle

        # ログ書き込みタスク（バックグラウンド）
        asyncio.create_task(cls._stream_logs(trace_id))

        return trace_id

    @classmethod
    async def _stream_logs(cls, trace_id: str) -> None:
        """ストリーム出力を logs/ に記録"""
        if trace_id not in cls._processes:
            return

        handle = cls._processes[trace_id]
        try:
            with open(handle.log_path, "w", encoding="utf-8") as f:
                async for line in handle.proc.stdout:
                    f.write(line.decode("utf-8", errors="replace"))
                    f.flush()

            # プロセス終了を待機
            await handle.proc.wait()

            # 終了情報を記録
            handle.exit_code = handle.proc.returncode
            handle.end_time = datetime.now()

        except Exception as e:
            with open(handle.log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[ERROR] Log streaming error: {e}\n")

    @classmethod
    async def get_status(cls, trace_id: str) -> Dict[str, Any]:
        """実行状態確認"""
        if trace_id not in cls._processes:
            raise ValueError(f"Trace ID not found: {trace_id}")

        handle = cls._processes[trace_id]
        poll_result = handle.proc.poll()

        # 実行中または既に終了
        status = "running" if poll_result is None else ("completed" if poll_result == 0 else "failed")

        elapsed = (datetime.now() - handle.start_time).total_seconds() if handle.start_time else None

        return {
            "trace_id": trace_id,
            "status": status,
            "exit_code": poll_result,
            "elapsed_seconds": elapsed,
            "start_time": handle.start_time.isoformat(),
            "end_time": handle.end_time.isoformat() if handle.end_time else None,
        }

    @classmethod
    async def get_log(cls, trace_id: str, tail: int = 100) -> Dict[str, Any]:
        """ログ取得"""
        if trace_id not in cls._processes:
            raise ValueError(f"Trace ID not found: {trace_id}")

        handle = cls._processes[trace_id]
        if not handle.log_path.exists():
            return {
                "trace_id": trace_id,
                "lines": ["[No log available yet]"],
                "total_lines": 0,
            }

        # ファイル末尾から tail 行取得
        with open(handle.log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        selected_lines = all_lines[-tail:] if tail > 0 else all_lines
        lines = [line.rstrip("\n") for line in selected_lines]

        return {
            "trace_id": trace_id,
            "lines": lines,
            "total_lines": total,
        }

    @classmethod
    async def cancel_pipeline(cls, trace_id: str) -> Dict[str, str]:
        """Pipeline キャンセル（graceful shutdown）"""
        if trace_id not in cls._processes:
            raise ValueError(f"Trace ID not found: {trace_id}")

        handle = cls._processes[trace_id]

        # SIGTERM で graceful shutdown
        try:
            handle.proc.terminate()
            try:
                await asyncio.wait_for(handle.proc.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                # SIGKILL で強制終了
                handle.proc.kill()
                await handle.proc.wait()

            handle.end_time = datetime.now()
            handle.exit_code = handle.proc.returncode

            return {"trace_id": trace_id, "message": "Pipeline cancelled"}
        except Exception as e:
            raise RuntimeError(f"Failed to cancel pipeline: {e}")

    @classmethod
    def get_history(cls, limit: int = 50) -> list[Dict[str, Any]]:
        """実行履歴取得"""
        history = []
        for trace_id, handle in sorted(cls._processes.items(), key=lambda x: x[1].start_time, reverse=True)[:limit]:
            duration = (handle.end_time - handle.start_time).total_seconds() if handle.end_time else None
            history.append({
                "trace_id": trace_id,
                "pattern": handle.pattern,
                "status": "running" if handle.exit_code is None else ("completed" if handle.exit_code == 0 else "failed"),
                "start_time": handle.start_time.isoformat(),
                "end_time": handle.end_time.isoformat() if handle.end_time else None,
                "duration_seconds": duration,
                "exit_code": handle.exit_code,
            })
        return history
