from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Flask server in the background.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--stdout", required=True)
    parser.add_argument("--stderr", required=True)
    parser.add_argument("--app-log", required=True)
    return parser.parse_args()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    pid_file = Path(args.pid_file).resolve()
    stdout_path = Path(args.stdout).resolve()
    stderr_path = Path(args.stderr).resolve()
    app_log = Path(args.app_log).resolve()

    ensure_parent(pid_file)
    ensure_parent(stdout_path)
    ensure_parent(stderr_path)
    ensure_parent(app_log)

    run_py = root / "run.py"
    if not run_py.exists():
        print(f"Nu gasesc {run_py}", file=sys.stderr)
        return 1

    python_exe = Path(sys.executable)
    pythonw = python_exe.with_name("pythonw.exe")
    child_executable = str(pythonw if pythonw.exists() else python_exe)

    stdout_handle = stdout_path.open("a", encoding="utf-8", buffering=1)
    stderr_handle = stderr_path.open("a", encoding="utf-8", buffering=1)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        [child_executable, str(run_py)],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=stderr_handle,
        env=env,
        creationflags=creationflags,
        close_fds=True,
    )

    pid_file.write_text(str(process.pid), encoding="utf-8")
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        print(process.pid)
        return 0

    pid_file.unlink(missing_ok=True)
    print(f"Serverul s-a oprit imediat cu codul {process.returncode}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
