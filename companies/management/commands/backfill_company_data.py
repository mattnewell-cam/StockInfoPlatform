import os
from django.db.models import Q
from django.core.management.base import BaseCommand
from django.conf import settings
from companies.models import Company
from companies.utils import yfinance_symbol
import yfinance as yf
import yfinance.cache as yf_cache
import signal
import time


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError("Timed out")


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

    def handle(self, *args, **options):
        cache_dir = os.getenv("YFINANCE_CACHE_DIR") or os.path.join(
            str(settings.BASE_DIR), "tmp", "yfinance-cache"
        )
        os.makedirs(cache_dir, exist_ok=True)
        yf_cache.set_cache_location(cache_dir)

        ticker = options.get('ticker')
        dry_run = options.get('dry_run')
        names_only = options.get('names_only')
        process_all = options.get('all')
        sleep_seconds = options.get('sleep')
        timeout_seconds = options.get('timeout')

        if ticker:
            companies = Company.objects.filter(ticker=ticker)
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

        total = companies.count()
        updated = 0
        failed = 0

        self.stdout.write(f"Processing {total} companies...")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        for i, company in enumerate(companies, 1):
            try:
                # Set timeout for get_info call if supported on this platform
                if hasattr(signal, "SIGALRM"):
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(timeout_seconds)

                yf_ticker = yf.Ticker(yfinance_symbol(company.ticker, company.exchange))
                info = yf_ticker.get_info()

                if hasattr(signal, "SIGALRM"):
                    signal.alarm(0)  # Cancel the alarm

                # Extract fields
                name = info.get("longName") or info.get("shortName") or ""
                if name:
                    name = name.replace("Public Limited Company", "plc")
                exchange = info.get("exchange", "")
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

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Updated: {updated}, Failed: {failed}, Unchanged: {total - updated - failed}"))
