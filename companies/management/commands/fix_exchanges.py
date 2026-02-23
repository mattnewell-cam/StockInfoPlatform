"""
Fix company exchanges that were incorrectly set to LSE.

Sources:
  data/all_us_tickers.csv        - active US tickers  (ticker, exchange)
  data/all_us_tickers_removed.csv - removed US tickers (ticker, exchange)
  data/lse_all_tickers.csv       - LSE/AIM tickers    (ticker, market)

Logic:
  1. If ticker is in lse_all_tickers.csv → keep as LSE or update to AIM; skip US lookup.
  2. If ticker is NOT in lse_all_tickers.csv but IS in a US CSV → update to US exchange.
  3. Otherwise → leave unchanged.

Tickers that appear in both CSVs are left as LSE (to be resolved separately).
"""

import csv
from django.core.management.base import BaseCommand
from companies.models import Company


class Command(BaseCommand):
    help = "Fix company exchange values using CSV source files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print changes without applying them",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # --- Build lookup tables ---
        us_exchange = {}
        for fname in ["data/all_us_tickers.csv", "data/all_us_tickers_removed.csv"]:
            with open(fname, newline="") as f:
                for row in csv.DictReader(f):
                    us_exchange[row["ticker"]] = row["exchange"]

        lse_market = {}
        with open("data/lse_all_tickers.csv", newline="") as f:
            for row in csv.DictReader(f):
                lse_market[row["ticker"]] = row["market"] if row["market"] else "LSE"

        # Tickers in both CSVs — flag for later, leave untouched
        both = set(us_exchange) & set(lse_market)
        if both:
            self.stdout.write(f"\nTickers in both CSVs (left unchanged for now): {len(both)}")
            self.stdout.write(f"  {sorted(both)[:20]}")

        # --- Identify changes ---
        changes: dict[str, list[str]] = {}
        skipped = []

        companies = Company.objects.filter(exchange="LSE").only("ticker", "exchange")

        for company in companies:
            ticker = company.ticker
            if ticker in lse_market:
                new_ex = lse_market[ticker]  # LSE or AIM
                if new_ex == "LSE":
                    continue  # already correct
            elif ticker in us_exchange:
                new_ex = us_exchange[ticker]
            else:
                skipped.append(ticker)
                continue

            changes.setdefault(new_ex, []).append(ticker)

        # --- Report ---
        total_updates = sum(len(v) for v in changes.items())
        self.stdout.write(f"\nExchange updates to apply: {sum(len(v) for v in changes.values())}")
        for ex, tickers in sorted(changes.items()):
            self.stdout.write(f"  {ex}: {len(tickers)}")
        self.stdout.write(f"No CSV match (left as LSE): {len(skipped)}")
        if skipped:
            self.stdout.write(f"  Sample: {skipped[:10]}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — no changes written."))
            return

        # --- Apply in bulk ---
        updated_total = 0
        for new_ex, tickers in changes.items():
            # Bulk update in chunks to avoid huge IN clauses
            chunk_size = 500
            for i in range(0, len(tickers), chunk_size):
                chunk = tickers[i : i + chunk_size]
                n = Company.objects.filter(ticker__in=chunk, exchange="LSE").update(
                    exchange=new_ex
                )
                updated_total += n

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Updated {updated_total} companies.")
        )
