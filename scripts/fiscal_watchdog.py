import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def jsonl_append(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    row = dict(payload)
    row.setdefault("ts", utc_now())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Watchdog wrapper for fiscal pull")
    ap.add_argument("--max-restarts", type=int, default=8)
    ap.add_argument("--window-seconds", type=int, default=3600)
    ap.add_argument("--backoff-start", type=int, default=15)
    ap.add_argument("--backoff-max", type=int, default=600)
    ap.add_argument("--log-jsonl", default="tmp/fiscal_watchdog.jsonl")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run after --")
    args = ap.parse_args()

    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("No command provided.")
        print("Example: python scripts/fiscal_watchdog.py -- python scripts/pull_financials_fiscal.py ...")
        sys.exit(2)

    restart_times = []
    attempt = 0
    backoff = args.backoff_start

    while True:
        attempt += 1
        t0 = time.time()
        jsonl_append(args.log_jsonl, {"event": "start", "attempt": attempt, "cmd": cmd})
        proc = subprocess.run(cmd)
        elapsed = round(time.time() - t0, 2)

        if proc.returncode == 0:
            jsonl_append(args.log_jsonl, {"event": "exit_ok", "attempt": attempt, "elapsed_sec": elapsed})
            print("Command exited 0, watchdog done.")
            return

        reason = f"exit_code={proc.returncode}"
        jsonl_append(args.log_jsonl, {
            "event": "exit_fail",
            "attempt": attempt,
            "elapsed_sec": elapsed,
            "reason": reason,
        })

        now = time.time()
        restart_times = [t for t in restart_times if (now - t) <= args.window_seconds]
        restart_times.append(now)

        if len(restart_times) > args.max_restarts:
            jsonl_append(args.log_jsonl, {
                "event": "stop_window_cap",
                "attempt": attempt,
                "restarts_in_window": len(restart_times),
                "window_seconds": args.window_seconds,
                "reason": reason,
            })
            print("Restart window cap exceeded. Stopping.")
            return

        jsonl_append(args.log_jsonl, {
            "event": "restart_scheduled",
            "attempt": attempt,
            "sleep_sec": backoff,
            "reason": reason,
        })
        print(f"Command failed ({reason}). Restarting in {backoff}s...")
        time.sleep(backoff)
        backoff = min(args.backoff_max, backoff * 2)


if __name__ == "__main__":
    main()
