import argparse
import json
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path, row):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({**row, "ts": now()}, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Watchdog wrapper for pull_financials_fiscal.py")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--log-jsonl", default="tmp/fiscal_watchdog.jsonl")
    ap.add_argument("--max-restarts", type=int, default=6)
    ap.add_argument("--window-seconds", type=int, default=3600)
    ap.add_argument("--backoff-seconds", type=int, default=30)
    ap.add_argument("pull_args", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    restart_times = deque()
    run_num = 0

    extra_args = list(args.pull_args)
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    while True:
        run_num += 1
        cmd = ["python3", "scripts/pull_financials_fiscal.py", *extra_args]
        append_jsonl(args.log_jsonl, {"event": "launch", "run_num": run_num, "cmd": cmd})
        proc = subprocess.run(cmd, cwd=args.workdir)
        code = int(proc.returncode)

        if code == 0:
            append_jsonl(args.log_jsonl, {"event": "exit_ok", "run_num": run_num, "returncode": code})
            print("Watchdog: pull completed successfully")
            return

        append_jsonl(args.log_jsonl, {"event": "exit_nonzero", "run_num": run_num, "returncode": code})
        now_ts = time.time()
        restart_times.append(now_ts)
        while restart_times and now_ts - restart_times[0] > args.window_seconds:
            restart_times.popleft()

        if len(restart_times) > args.max_restarts:
            append_jsonl(
                args.log_jsonl,
                {
                    "event": "watchdog_abort",
                    "reason": "restart_limit_exceeded",
                    "restarts_in_window": len(restart_times),
                    "window_seconds": args.window_seconds,
                },
            )
            print("Watchdog: aborting (restart limit exceeded)")
            raise SystemExit(2)

        delay = args.backoff_seconds * min(len(restart_times), 5)
        append_jsonl(args.log_jsonl, {"event": "restart_scheduled", "delay_sec": delay, "run_num": run_num})
        print(f"Watchdog: process crashed (code={code}), restarting in {delay}s")
        time.sleep(delay)


if __name__ == "__main__":
    main()
