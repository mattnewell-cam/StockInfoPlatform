import argparse
import json
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def append_jsonl(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), **payload}, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Watchdog wrapper for fiscal pull")
    ap.add_argument("--script", default="scripts/pull_financials_fiscal.py")
    ap.add_argument("--checkpoint-json", required=True)
    ap.add_argument("--watchdog-jsonl", default="tmp/fiscal_watchdog.jsonl")
    ap.add_argument("--max-restarts", type=int, default=6)
    ap.add_argument("--window-minutes", type=int, default=60)
    ap.add_argument("--backoff-start", type=int, default=20)
    ap.add_argument("--backoff-cap", type=int, default=300)
    ap.add_argument("--min-complete-delta", type=int, default=1)
    ap.add_argument("pull_args", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    restart_times = deque()
    backoff = args.backoff_start
    last_completed = 0

    while True:
        cmd = ["python3", args.script] + args.pull_args
        append_jsonl(args.watchdog_jsonl, {"event": "start", "cmd": cmd})
        print("[watchdog] start", " ".join(cmd))
        proc = subprocess.run(cmd)

        cp = load_json(args.checkpoint_json, {"completed": {}})
        completed_now = len((cp or {}).get("completed", {}))
        delta = completed_now - last_completed
        last_completed = completed_now

        reason = "exit_nonzero" if proc.returncode != 0 else "no_progress" if delta < args.min_complete_delta else "normal_exit"
        append_jsonl(args.watchdog_jsonl, {
            "event": "exit",
            "returncode": proc.returncode,
            "reason": reason,
            "completed": completed_now,
            "delta_completed": delta,
        })

        if reason == "normal_exit":
            print("[watchdog] normal completion; exiting")
            break

        now = time.time()
        restart_times.append(now)
        while restart_times and now - restart_times[0] > args.window_minutes * 60:
            restart_times.popleft()
        if len(restart_times) > args.max_restarts:
            append_jsonl(args.watchdog_jsonl, {
                "event": "abort",
                "reason": "restart_cap_exceeded",
                "restarts_in_window": len(restart_times),
                "window_minutes": args.window_minutes,
            })
            raise SystemExit(2)

        append_jsonl(args.watchdog_jsonl, {"event": "restart_scheduled", "backoff_seconds": backoff, "reason": reason})
        print(f"[watchdog] restart in {backoff}s reason={reason}")
        time.sleep(backoff)
        backoff = min(args.backoff_cap, max(args.backoff_start, backoff * 2))


if __name__ == "__main__":
    main()
