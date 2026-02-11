import argparse
import csv
import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://fiscal.ai"
WORKERS_DEFAULT = 4
FAST_MODE_DEFAULT = True
BASE_DIR = Path(__file__).resolve().parent

DEFAULT_OUT_JSON = str((BASE_DIR / ".." / "cached_financials_2.json").resolve())
DEFAULT_FAILED_CSV = str((BASE_DIR / ".." / "financials_failed.csv").resolve())
DEFAULT_TICKERS_CSV = str((BASE_DIR / ".." / "sp500_tickers_fiscal_exchange.csv").resolve())
DEFAULT_CHECKPOINT_JSON = str((BASE_DIR / ".." / "tmp" / "fiscal_checkpoint.json").resolve())
DEFAULT_METRICS_JSONL = str((BASE_DIR / ".." / "tmp" / "fiscal_metrics.jsonl").resolve())


STATEMENT_SLUGS = {
    "IS": ["income-statement"],
    "BS": ["balance-sheet"],
    "CF": ["cash-flow-statement"],
}

SUPPLEMENTAL_TABLES = {
    "BS": {"slug": "balance-sheet", "names": ["Liabilities", "Equity"]},
    "CF": {"slug": "cash-flow-statement", "names": ["Investing Activities", "Financing Activities"]},
}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def load_json(path: str, default):
    p = Path(path)
    if not p.exists():
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    ensure_parent(path)
    tmp = Path(path).with_suffix(Path(path).suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def append_jsonl(path: str, payload: dict, lock: Lock | None = None):
    if not path:
        return
    ensure_parent(path)
    row = dict(payload)
    row.setdefault("ts", utc_now_iso())
    line = json.dumps(row, ensure_ascii=False)
    if lock:
        with lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def wait_for(driver, by, value, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def safe_click(driver, element):
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def normalize_exchange(exchange: str) -> str:
    if not exchange:
        return exchange
    u = exchange.strip().upper()
    if u in {"NASDAQ", "NMS", "NAS", "NGS"}:
        return "NasdaqGS"
    if u in {"NYSE", "NYQ", "NYS"}:
        return "NYSE"
    return exchange.strip()


def build_fiscal_ticker(ticker, exchange):
    if "-" in ticker:
        return ticker
    return f"{normalize_exchange(exchange)}-{ticker}"


def start_login_flow(driver):
    driver.get(URL)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    btn = driver.find_element(By.ID, "ph-marketing-header__sign-up-button")
    driver.execute_script("arguments[0].click();", btn)

    email = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'],input[name='email']"))
    )
    email.clear()
    email.send_keys("matthew_newell@outlook.com")
    email.send_keys(Keys.RETURN)
    print("Paste fiscal.ai magic link:")
    return input().strip()


def open_magic_link(driver, magic_link):
    driver.get(magic_link)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)


def assert_authenticated(driver):
    driver.get(f"{URL}/dashboard")
    wait_for(driver, By.TAG_NAME, "body", timeout=12)
    body = driver.find_element(By.TAG_NAME, "body").text.lower()
    cur = (driver.current_url or "").lower()
    if any(x in cur for x in ["login", "sign-in", "auth"]) or "magic link" in body:
        raise RuntimeError("Auth check failed")


def ensure_k_units(driver, timeout=10):
    try:
        label = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.XPATH, "//label[.//span[contains(@class,'mantine-SegmentedControl-innerLabel') and normalize-space()='K']]")
            )
        )
        if label.get_attribute("data-active") != "true":
            safe_click(driver, label)
            time.sleep(0.15)
    except Exception:
        pass


def is_ticker_not_found(driver):
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return False
    return any(m in body for m in ["not found", "no results", "no data", "does not exist", "cannot find"])


def quick_missing_check(driver, ticker, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'):
            return
        if is_ticker_not_found(driver):
            raise RuntimeError(f"{ticker} not found on fiscal.ai")
        time.sleep(0.2)


def slider_range_already_adequate(driver, min_val=5, max_val=22):
    try:
        thumbs = driver.find_elements(By.CSS_SELECTOR, ".mantine-Slider-thumb")
        if len(thumbs) < 2:
            return False
        left = int(thumbs[0].get_attribute("aria-valuenow"))
        right = int(thumbs[1].get_attribute("aria-valuenow"))
        return left <= min_val and right >= max_val
    except Exception:
        return False


def set_slider_range(driver, min_val=5, max_val=22, key_delay=0.0, max_seconds=3.0):
    t0 = time.perf_counter()
    thumbs = driver.find_elements(By.CSS_SELECTOR, ".mantine-Slider-thumb")
    if len(thumbs) < 2:
        return False
    left, right = thumbs[0], thumbs[1]

    def adjust(thumb, target, left_side):
        try:
            safe_click(driver, thumb)
            thumb.send_keys(Keys.HOME if left_side else Keys.END)
            cur = int(thumb.get_attribute("aria-valuenow"))
            key = Keys.ARROW_LEFT if target < cur else Keys.ARROW_RIGHT
            for _ in range(abs(target - cur)):
                if time.perf_counter() - t0 > max_seconds:
                    return False
                thumb.send_keys(key)
                if key_delay:
                    time.sleep(key_delay)
            return int(thumb.get_attribute("aria-valuenow")) == target
        except Exception:
            return False

    ok1 = adjust(left, min_val, True)
    ok2 = adjust(right, max_val, False)
    return ok1 and ok2


def extract_rows_from_table(table_root):
    parity = os.getenv("EXTRACT_PARITY", "0").lower() in {"1", "true", "yes", "on"}

    def slow_extract(root):
        rows = root.find_elements(By.CSS_SELECTOR, "tr") or root.find_elements(By.CSS_SELECTOR, "[role='row']")
        out = []
        for row in rows:
            cells = row.find_elements(By.CSS_SELECTOR, "th,td") or row.find_elements(By.CSS_SELECTOR, "[role='columnheader'],[role='cell']")
            vals = [c.text.strip() for c in cells]
            if len(vals) >= 2 and any(vals[1:]):
                out.append(vals)
        return out

    try:
        d = getattr(table_root, "_parent", None)
        fast = d.execute_script(
            """
            const root=arguments[0];
            const rows=root.querySelectorAll('tr,[role="row"]');
            const out=[];
            for (const r of rows){
              const cells=r.querySelectorAll('th,td,[role="columnheader"],[role="cell"]');
              out.push(Array.from(cells).map(c=>(c.innerText||c.textContent||'').trim()));
            }
            return out;
            """,
            table_root,
        )
        fast = [r for r in fast if isinstance(r, list) and len(r) >= 2 and any((x or "").strip() for x in r[1:])]
        if fast and not parity:
            return fast
        slow = slow_extract(table_root)
        if parity and len(fast) != len(slow):
            return slow
        return fast or slow
    except Exception:
        return slow_extract(table_root)


def extract_all_tables_from_page(driver):
    tables = []
    for el in driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'):
        rows = extract_rows_from_table(el)
        if rows:
            tables.append(rows)
    return tables


def find_table_by_name(tables, name):
    target = name.strip().lower()
    for t in tables:
        if t and t[0] and t[0][0].strip().lower() == target:
            return t
    return None


def load_statement_table(driver, ticker, slug, expand_slider=True, fast_mode=False, skip_slider_if_adequate=True):
    timings = {}
    t_all = time.perf_counter()
    url = f"{URL}/company/{ticker}/financials/{slug}/annual/"

    t0 = time.perf_counter()
    driver.get(url)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    timings["nav"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    if not fast_mode:
        time.sleep(0.35)
    timings["sleep"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    if slug == "income-statement":
        ensure_k_units(driver)
    timings["units"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    quick_missing_check(driver, ticker, timeout=3 if fast_mode else 5)
    timings["missing"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    skipped = False
    if expand_slider:
        if skip_slider_if_adequate and slider_range_already_adequate(driver):
            skipped = True
        else:
            set_slider_range(driver, min_val=5, max_val=22, key_delay=0.005 if fast_mode else 0.02, max_seconds=3.0)
    timings["slider"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    WebDriverWait(driver, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"] tr,[data-sentry-component="TableContent"] [role="row"]')) > 1
    )
    root = WebDriverWait(driver, 15 if fast_mode else 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-sentry-component="TableContent"]'))
    )
    rows = extract_rows_from_table(root)
    timings["extract"] = time.perf_counter() - t0
    timings["total"] = time.perf_counter() - t_all
    timings["slider_skipped"] = skipped
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{ticker} {slug} empty rows")
    return rows, timings


def load_page_all_tables(driver, ticker, slug, expand_slider=True, fast_mode=False, skip_slider_if_adequate=True):
    url = f"{URL}/company/{ticker}/financials/{slug}/annual/"
    driver.get(url)
    wait_for(driver, By.TAG_NAME, "body", timeout=15)
    if not fast_mode:
        time.sleep(0.35)
    quick_missing_check(driver, ticker, timeout=3 if fast_mode else 5)
    if expand_slider:
        if not (skip_slider_if_adequate and slider_range_already_adequate(driver)):
            set_slider_range(driver, min_val=5, max_val=22, key_delay=0.005 if fast_mode else 0.02, max_seconds=3.0)
    WebDriverWait(driver, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, '[data-sentry-component="TableContent"] tr,[data-sentry-component="TableContent"] [role="row"]')) > 1
    )
    time.sleep(0.25 if fast_mode else 0.9)
    return extract_all_tables_from_page(driver)


def pull_supplemental(driver, ticker, exchange="LSE", expand_slider=True, fast_mode=False, skip_slider_if_adequate=True):
    def run(exch):
        fiscal_ticker = build_fiscal_ticker(ticker, exch)
        result = {}
        for stmt, cfg in SUPPLEMENTAL_TABLES.items():
            all_tables = load_page_all_tables(
                driver,
                fiscal_ticker,
                cfg["slug"],
                expand_slider=expand_slider,
                fast_mode=fast_mode,
                skip_slider_if_adequate=skip_slider_if_adequate,
            )
            rows = []
            for name in cfg["names"]:
                t = find_table_by_name(all_tables, name)
                if t:
                    rows.extend(t)
            if rows:
                result[stmt] = rows
        return result

    try:
        return run(exchange), exchange, {}
    except Exception as exc:
        if "not found" in str(exc).lower():
            fb = "AIM" if exchange != "AIM" else "LSE"
            return run(fb), fb, {}
        raise


def pull_financials(driver, ticker, exchange="LSE", expand_slider=True, fast_mode=False, skip_slider_if_adequate=True):
    def run(exch):
        fiscal_ticker = build_fiscal_ticker(ticker, exch)
        out = {}
        per_statement_timings = {}
        for statement, slugs in STATEMENT_SLUGS.items():
            last = None
            for slug in slugs:
                try:
                    rows, timing = load_statement_table(
                        driver,
                        fiscal_ticker,
                        slug,
                        expand_slider=expand_slider,
                        fast_mode=fast_mode,
                        skip_slider_if_adequate=skip_slider_if_adequate,
                    )
                    out[statement] = rows
                    per_statement_timings[statement] = timing
                    last = None
                    break
                except Exception as exc:
                    last = exc
            if last:
                raise last
        return out, per_statement_timings

    try:
        fin, t = run(exchange)
        return fin, exchange, t
    except Exception as exc:
        if "not found" in str(exc).lower():
            fb = "AIM" if exchange != "AIM" else "LSE"
            fin, t = run(fb)
            return fin, fb, t
        raise


def validate_required_tables(financials):
    missing = []
    for req in ("IS", "BS", "CF"):
        if req not in financials or not financials[req]:
            missing.append(req)
    if "BS" in financials:
        labels = {r[0].strip().lower() for r in financials["BS"] if r}
        for x in ["liabilities", "equity"]:
            if x not in labels:
                missing.append(f"BS:{x}")
    if "CF" in financials:
        labels = {r[0].strip().lower() for r in financials["CF"] if r}
        for x in ["investing activities", "financing activities"]:
            if x not in labels:
                missing.append(f"CF:{x}")
    return missing


def load_failed_set(path):
    if not Path(path).exists():
        return set()
    out = set()
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if row:
                out.add(row[0])
    return out


def needs_supplemental(ticker_data):
    for stmt, cfg in SUPPLEMENTAL_TABLES.items():
        if stmt not in ticker_data:
            return True
        labels = {r[0].strip().lower() for r in ticker_data[stmt] if r}
        for n in cfg["names"]:
            if n.strip().lower() not in labels:
                return True
    return False


def heartbeat_loop(stop_event: Event, state: dict, checkpoint_path: str, lock: Lock, interval_seconds: float, metrics_jsonl: str):
    while not stop_event.wait(interval_seconds):
        with lock:
            processed = state["processed"]
            total = state["total"]
            started = state["started_at"]
            in_flight = dict(state["in_flight"])
        elapsed = max(time.time() - started, 0.001)
        rate_h = (processed / elapsed) * 3600.0
        remaining = max(total - processed, 0)
        eta = (remaining / processed * elapsed) if processed > 0 else None
        msg = f"[heartbeat] processed={processed}/{total} rate={rate_h:.1f}/h"
        if eta is not None:
            msg += f" ETA={int(eta)}s"
        print(msg)
        append_jsonl(metrics_jsonl, {
            "type": "heartbeat",
            "processed": processed,
            "total": total,
            "in_flight": in_flight,
            "rate_per_hour": rate_h,
            "eta_seconds": eta,
            "checkpoint": checkpoint_path,
        }, lock=lock)


def main():
    parser = argparse.ArgumentParser(description="Fetch fiscal.ai financials with checkpointing + structured metrics")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--magic-link", default="")
    parser.add_argument("--tickers-csv", default=DEFAULT_TICKERS_CSV)
    parser.add_argument("--use-csv", action="store_true")
    parser.add_argument("--ticker", default="")
    parser.add_argument("--out-json", default=DEFAULT_OUT_JSON)
    parser.add_argument("--failed-csv", default=DEFAULT_FAILED_CSV)
    parser.add_argument("--checkpoint-json", default=DEFAULT_CHECKPOINT_JSON)
    parser.add_argument("--metrics-jsonl", default=DEFAULT_METRICS_JSONL)
    parser.add_argument("--workers", type=int, default=WORKERS_DEFAULT)
    parser.add_argument("--no-slider", action="store_true")
    parser.add_argument("--fast", action="store_true", default=FAST_MODE_DEFAULT)
    parser.add_argument("--no-fast", action="store_true")
    parser.add_argument("--skip-slider-if-adequate", action="store_true", default=True)
    parser.add_argument("--no-skip-slider-if-adequate", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--heartbeat-minutes", type=float, default=5.0)
    parser.add_argument("--ticker-limit", type=int, default=0)
    parser.add_argument("--benchmark-tag", default="")
    args = parser.parse_args()

    def build_driver():
        opts = uc.ChromeOptions()
        if args.headless:
            opts.add_argument("--headless")
        d = uc.Chrome(options=opts, version_main=144)
        d.implicitly_wait(10)
        return d

    def split_chunks(items, workers):
        chunks = [[] for _ in range(max(1, workers))]
        for i, t in enumerate(items):
            chunks[i % len(chunks)].append(t)
        return [c for c in chunks if c]

    checkpoint = load_json(args.checkpoint_json, {
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "completed": {},
        "failed": {},
        "in_flight": {},
        "workers": {},
    })
    cached = load_json(args.out_json, {})
    failed_existing = load_failed_set(args.failed_csv)

    ticker_market = {}
    if args.use_csv or not args.ticker:
        tickers = []
        with open(args.tickers_csv, newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row and row[0].strip():
                    t = row[0].strip()
                    tickers.append(t)
                    if len(row) > 1 and row[1].strip():
                        ticker_market[t] = normalize_exchange(row[1].strip())
    else:
        tickers = [args.ticker]

    pending = []
    for t in tickers:
        if t in checkpoint.get("completed", {}):
            continue
        if (not args.retry_failed) and t in checkpoint.get("failed", {}):
            continue
        pending.append(t)

    if args.ticker_limit and args.ticker_limit > 0:
        pending = pending[:args.ticker_limit]

    if not pending:
        print("No tickers to process")
        return

    lock = Lock()
    state = {
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "total": len(pending),
        "started_at": time.time(),
        "in_flight": {},
    }

    def checkpoint_save():
        checkpoint["updated_at"] = utc_now_iso()
        save_json(args.checkpoint_json, checkpoint)

    stop = Event()
    heartbeat = Thread(
        target=heartbeat_loop,
        args=(stop, state, args.checkpoint_json, lock, max(10.0, args.heartbeat_minutes * 60.0), args.metrics_jsonl),
        daemon=True,
    )
    heartbeat.start()

    def worker_run(worker_id, driver, chunk):
        fast_mode = args.fast and not args.no_fast
        skip_slider_if_adequate = args.skip_slider_if_adequate and not args.no_skip_slider_if_adequate
        failed_local = []

        for t in chunk:
            t0 = time.perf_counter()
            exch = ticker_market.get(t, "LSE")
            with lock:
                checkpoint.setdefault("in_flight", {})[str(worker_id)] = {
                    "ticker": t,
                    "exchange": exch,
                    "started_at": utc_now_iso(),
                }
                state["in_flight"][str(worker_id)] = t
                checkpoint_save()

            kind = "supplemental" if (t in cached and needs_supplemental(cached[t])) else "full"
            if t in cached and not needs_supplemental(cached[t]):
                with lock:
                    checkpoint.setdefault("completed", {})[t] = {"kind": "skip_already_complete", "worker": worker_id, "ts": utc_now_iso()}
                    checkpoint["in_flight"].pop(str(worker_id), None)
                    state["in_flight"].pop(str(worker_id), None)
                    state["processed"] += 1
                    state["successful"] += 1
                    checkpoint_save()
                append_jsonl(args.metrics_jsonl, {"type": "ticker", "ticker": t, "worker": worker_id, "kind": "skip", "outcome": "ok"}, lock=lock)
                continue

            try:
                if kind == "supplemental":
                    supp, used_exchange, _ = pull_supplemental(
                        driver,
                        t,
                        exchange=exch,
                        expand_slider=not args.no_slider,
                        fast_mode=fast_mode,
                        skip_slider_if_adequate=skip_slider_if_adequate,
                    )
                    with lock:
                        for stmt, rows in supp.items():
                            cur = cached[t].setdefault(stmt, [])
                            seen = {json.dumps(r, ensure_ascii=False) for r in cur}
                            for row in rows:
                                k = json.dumps(row, ensure_ascii=False)
                                if k not in seen:
                                    cur.append(row)
                                    seen.add(k)
                        save_json(args.out_json, cached)
                    validation_missing = validate_required_tables(cached[t])
                    timing_sections = {}
                else:
                    financials, used_exchange, timing_sections = pull_financials(
                        driver,
                        t,
                        exchange=exch,
                        expand_slider=not args.no_slider,
                        fast_mode=fast_mode,
                        skip_slider_if_adequate=skip_slider_if_adequate,
                    )
                    validation_missing = validate_required_tables(financials)
                    if validation_missing:
                        raise RuntimeError("validation missing: " + ", ".join(validation_missing))
                    with lock:
                        cached[t] = financials
                        save_json(args.out_json, cached)

                elapsed = time.perf_counter() - t0
                row_counts = {k: len(cached[t].get(k, [])) for k in ("IS", "BS", "CF")} if t in cached else {}
                with lock:
                    checkpoint.setdefault("completed", {})[t] = {
                        "worker": worker_id,
                        "kind": kind,
                        "exchange": used_exchange,
                        "seconds": round(elapsed, 3),
                        "row_counts": row_counts,
                        "validation_missing": validation_missing,
                        "ts": utc_now_iso(),
                    }
                    checkpoint.get("failed", {}).pop(t, None)
                    checkpoint["in_flight"].pop(str(worker_id), None)
                    state["in_flight"].pop(str(worker_id), None)
                    state["processed"] += 1
                    state["successful"] += 1
                    checkpoint_save()
                append_jsonl(args.metrics_jsonl, {
                    "type": "ticker",
                    "ticker": t,
                    "worker": worker_id,
                    "kind": kind,
                    "exchange": used_exchange,
                    "outcome": "ok",
                    "seconds": round(elapsed, 3),
                    "row_counts": row_counts,
                    "validation_missing": validation_missing,
                    "timings": timing_sections,
                    "benchmark_tag": args.benchmark_tag or None,
                }, lock=lock)
                print(f"[{worker_id}] OK {t} {kind} {elapsed:.2f}s")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                reason = str(e)
                failed_local.append(t)
                with lock:
                    checkpoint.setdefault("failed", {})[t] = {
                        "worker": worker_id,
                        "kind": kind,
                        "exchange": exch,
                        "seconds": round(elapsed, 3),
                        "reason": reason,
                        "trace": traceback.format_exc(limit=5),
                        "ts": utc_now_iso(),
                    }
                    checkpoint["in_flight"].pop(str(worker_id), None)
                    state["in_flight"].pop(str(worker_id), None)
                    state["processed"] += 1
                    state["failed"] += 1
                    checkpoint_save()
                    if t not in failed_existing:
                        failed_existing.add(t)
                        ensure_parent(args.failed_csv)
                        with open(args.failed_csv, "a", newline="") as f:
                            csv.writer(f).writerow([t, exch, reason])
                append_jsonl(args.metrics_jsonl, {
                    "type": "ticker",
                    "ticker": t,
                    "worker": worker_id,
                    "kind": kind,
                    "exchange": exch,
                    "outcome": "failed",
                    "seconds": round(elapsed, 3),
                    "reason": reason,
                    "benchmark_tag": args.benchmark_tag or None,
                }, lock=lock)
                print(f"[{worker_id}] FAIL {t}: {reason}")
        return failed_local

    drivers = []
    try:
        chunks = split_chunks(pending, max(1, args.workers))
        d0 = build_driver()
        drivers.append(d0)
        magic = args.magic_link.strip() if args.magic_link else start_login_flow(d0)

        for _ in range(len(chunks) - 1):
            drivers.append(build_driver())
        for i, d in enumerate(drivers, start=1):
            open_magic_link(d, magic)
            assert_authenticated(d)
            print(f"Worker browser {i}/{len(drivers)} authenticated")

        failed = []
        with ThreadPoolExecutor(max_workers=len(chunks)) as ex:
            futs = [ex.submit(worker_run, idx + 1, d, c) for idx, (d, c) in enumerate(zip(drivers, chunks))]
            for f in as_completed(futs):
                failed.extend(f.result())

        print(f"Done. completed={len(checkpoint.get('completed', {}))} failed={len(checkpoint.get('failed', {}))} run_failed={len(failed)}")
    finally:
        stop.set()
        for d in drivers:
            try:
                d.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
