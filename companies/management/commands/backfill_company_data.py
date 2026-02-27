import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from django.db.models import Q
from django.core.management.base import BaseCommand
from django.conf import settings
from companies.models import Company
from companies.utils import yfinance_symbol, YF_EXCHANGE_NORMALIZE, normalize_exchange
import yfinance as yf
import yfinance.cache as yf_cache
import time


def is_rate_limit_error(err: Exception) -> bool:
    msg = str(err).lower()
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        return True
    if "yf ratelimit" in msg or "yfratelimit" in msg:
        return True
    return False


class Command(BaseCommand):
    help = "Backfill name, exchange, currency, market_cap, shares from yfinance."

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Update a specific ticker only',
        )
        parser.add_argument(
            '--exchange',
            type=str,
            help='Optional exchange filter when used with --ticker (e.g. LSE, NMS, NYQ)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process all companies (default is only missing fields)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--names-only',
            action='store_true',
            help='Only update companies where name == ticker (stub companies)',
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=0.5,
            help='Seconds to sleep between requests (default: 0.5)',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='Seconds before timing out a request (default: 30)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of companies to process in this run',
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help='Skip this many companies after filtering (default: 0)',
        )
        parser.add_argument(
            '--min-id',
            type=int,
            default=None,
            help='Only process companies with id >= this value',
        )
        parser.add_argument(
            '--max-id',
            type=int,
            default=None,
            help='Only process companies with id <= this value',
        )
        parser.add_argument(
            '--checkpoint-file',
            type=str,
            default='',
            help='Optional file path storing the last processed company id',
        )
        parser.add_argument(
            '--resume-from-checkpoint',
            action='store_true',
            help='Resume from the id recorded in --checkpoint-file',
        )

    def _fetch_info(self, symbol: str, timeout: int) -> dict | None:
        """Fetch yfinance info for a symbol with a thread-based timeout. Returns None on timeout."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(yf.Ticker(symbol).get_info)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError:
                return None

    def handle(self, *args, **options):
        cache_dir = os.getenv("YFINANCE_CACHE_DIR") or os.path.join(
            str(settings.BASE_DIR), "tmp", "yfinance-cache"
        )
        os.makedirs(cache_dir, exist_ok=True)
        yf_cache.set_cache_location(cache_dir)

        ticker = options.get('ticker')
        exchange_filter = normalize_exchange(options.get('exchange'))
        dry_run = options.get('dry_run')
        names_only = options.get('names_only')
        process_all = options.get('all')
        sleep_seconds = options.get('sleep')
        timeout_seconds = options.get('timeout')
        limit = options.get('limit')
        offset = max(0, options.get('offset') or 0)
        min_id = options.get('min_id')
        max_id = options.get('max_id')
        checkpoint_file = (options.get('checkpoint_file') or '').strip()
        resume_from_checkpoint = options.get('resume_from_checkpoint')

        if resume_from_checkpoint and not checkpoint_file:
            self.stderr.write(self.style.ERROR(
                "--resume-from-checkpoint requires --checkpoint-file"
            ))
            return
        if resume_from_checkpoint:
            resume_id = self._read_checkpoint_id(checkpoint_file)
            if resume_id is not None:
                min_id = max(min_id or 0, resume_id + 1)
                self.stdout.write(f"Resuming from checkpoint id {resume_id} (next id >= {min_id})")
            else:
                self.stdout.write("Checkpoint file not found or invalid; starting from filtered queryset")

        if ticker:
            companies = Company.objects.filter(ticker=ticker)
            if exchange_filter:
                companies = companies.filter(exchange=exchange_filter)
        elif names_only:
            # Only companies where name equals ticker (stubs)
            companies = Company.objects.extra(where=['name = ticker'])
        elif process_all:
            companies = Company.objects.all()
        else:
            missing = (
                Q(name__isnull=True) | Q(name__exact="") |
                Q(exchange__isnull=True) | Q(exchange__exact="") |
                Q(currency__isnull=True) | Q(currency__exact="") |
                Q(market_cap__isnull=True) |
                Q(shares_outstanding__isnull=True)
            )
            companies = Company.objects.filter(missing)

        companies = companies.order_by('id')
        if min_id is not None:
            companies = companies.filter(id__gte=min_id)
        if max_id is not None:
            companies = companies.filter(id__lte=max_id)
        if offset:
            companies = companies[offset:]
        if limit is not None:
            companies = companies[:limit]

        total = companies.count()
        updated = 0
        failed = 0

        self.stdout.write(f"Processing {total} companies...")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))
        self.stdout.flush()

        for i, company in enumerate(companies, 1):
            try:
                symbol = yfinance_symbol(company.ticker, company.exchange)
                info = self._fetch_info(symbol, timeout_seconds)

                # If the exchange-suffixed lookup found nothing, fall back to bare ticker
                if (info is None or (not info.get("longName") and not info.get("shortName"))) and symbol != company.ticker:
                    info = self._fetch_info(company.ticker, timeout_seconds)

                if info is None:
                    self.stdout.write(self.style.WARNING(
                        f"[{i}/{total}] {company.ticker}: timed out, skipping"
                    ))
                    self.stdout.flush()
                    failed += 1
                    continue

                # Extract fields
                name = info.get("longName") or info.get("shortName") or ""
                if name:
                    name = name.replace("Public Limited Company", "plc")
                exchange = info.get("exchange", "")
                exchange = YF_EXCHANGE_NORMALIZE.get(exchange, exchange)
                exchange = normalize_exchange(exchange)
                currency = info.get("currency", "")
                market_cap = info.get("marketCap")
                shares = info.get("sharesOutstanding")

                # Convert to int if present
                if market_cap:
                    market_cap = int(market_cap)
                if shares:
                    shares = int(shares)

                changes = []
                update_fields = []

                if name and company.name != name:
                    changes.append(f"name: '{company.name}' -> '{name}'")
                    if not dry_run:
                        company.name = name
                    update_fields.append('name')

                if exchange and company.exchange != exchange:
                    changes.append(f"exchange: '{company.exchange}' -> '{exchange}'")
                    if not dry_run:
                        company.exchange = exchange
                    update_fields.append('exchange')

                if currency and company.currency != currency:
                    changes.append(f"currency: '{company.currency}' -> '{currency}'")
                    if not dry_run:
                        company.currency = currency
                    update_fields.append('currency')

                if market_cap and company.market_cap != market_cap:
                    changes.append(f"market_cap: {company.market_cap} -> {market_cap}")
                    if not dry_run:
                        company.market_cap = market_cap
                    update_fields.append('market_cap')

                if shares and company.shares_outstanding != shares:
                    changes.append(f"shares: {company.shares_outstanding} -> {shares}")
                    if not dry_run:
                        company.shares_outstanding = shares
                    update_fields.append('shares_outstanding')

                if changes:
                    self.stdout.write(f"[{i}/{total}] {company.ticker}: {', '.join(changes)}")
                    if not dry_run and update_fields:
                        company.save(update_fields=update_fields)
                    updated += 1
                else:
                    self.stdout.write(f"[{i}/{total}] {company.ticker}: no changes needed")
                self.stdout.flush()

                if sleep_seconds and sleep_seconds > 0:
                    time.sleep(sleep_seconds)

            except Exception as e:
                if is_rate_limit_error(e):
                    if sleep_seconds < 3:
                        sleep_seconds = 3
                        self.stdout.write(self.style.WARNING(
                            f"[{i}/{total}] {company.ticker}: rate limit hit; "
                            "increasing sleep to 3 seconds"
                        ))
                        failed += 1
                        continue
                    self.stdout.write(self.style.ERROR(
                        f"[{i}/{total}] {company.ticker}: rate limit persisted at 3s; aborting"
                    ))
                    raise
                else:
                    self.stdout.write(self.style.ERROR(f"[{i}/{total}] {company.ticker}: FAILED - {e}"))
                    failed += 1
            finally:
                if checkpoint_file:
                    self._write_checkpoint_id(checkpoint_file, company.id)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Updated: {updated}, Failed: {failed}, Unchanged: {total - updated - failed}"))

    def _read_checkpoint_id(self, path: str) -> int | None:
        try:
            raw = Path(path).read_text(encoding='utf-8').strip()
            if not raw:
                return None
            return int(raw)
        except Exception:
            return None

    def _write_checkpoint_id(self, path: str, company_id: int) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(company_id), encoding='utf-8')
