"""
Resolve exchange conflicts arising from tickers appearing in both
all_us_tickers.csv and lse_all_tickers.csv.

Actions:
  1. Delete 12 stub rows with no useful data.
  2. Fix exchange codes for 10 tickers that were incorrectly set to LSE.

Run dry-run first to review, then apply:
    python manage.py cleanup_exchange_conflicts --dry-run
    python manage.py cleanup_exchange_conflicts --apply
"""

import csv
from django.core.management.base import BaseCommand
from django.db.models import Count
from companies.models import Company
from companies.utils import normalize_exchange


# --- Deletions ---

# Cat 3: LSE stubs with no name/financials; real data lives on the NMS row.
CAT3_LSE_STUBS = ["ALLE", "AMCR", "AME", "AMT", "AOS", "APD", "ATO", "TSCO"]

# Pure stubs: no data anywhere (no name, no financials on any row).
PURE_STUBS_LSE = ["AVBH", "FLOC"]

# Cat 2a: NMS stub row for companies whose real data is on the LSE row.
CAT2A_NMS_STUBS = ["CCL", "CRH"]

# --- Exchange fixes (LSE → correct US exchange) ---

# These tickers exist in all_us_tickers.csv but were stored as LSE.
# The correct exchange is read from all_us_tickers.csv at runtime.
EXCHANGE_FIX_TICKERS = ["AA", "AEI", "AIXI", "ALUR", "CBC", "COSO", "FIGR", "KFS", "MUFG", "STLA"]

US_TICKERS_CSV = "data/all_us_tickers.csv"


class Command(BaseCommand):
    help = "Delete stub rows and fix incorrect exchange codes for dual-listed tickers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without making any changes.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually apply deletes/updates. Without this flag the command runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"] or (not options["apply"])
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made.\n"))

        # --- Build US exchange lookup ---
        us_exchange = {}
        try:
            with open(US_TICKERS_CSV, newline="") as f:
                for row in csv.DictReader(f):
                    ticker = (row.get("ticker") or "").strip().upper()
                    exchange = normalize_exchange(row.get("exchange"))
                    if ticker and exchange:
                        us_exchange[ticker] = exchange
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"Cannot open {US_TICKERS_CSV}"))
            return

        # ----------------------------------------------------------------
        # 1. DELETIONS
        # ----------------------------------------------------------------
        self.stdout.write("=== DELETIONS ===")

        total_deleted = 0

        # Cat 3 LSE stubs
        total_deleted += self._delete_stubs(
            CAT3_LSE_STUBS, "LSE", "Cat 3 LSE stubs", dry_run
        )

        # Pure stubs (LSE)
        total_deleted += self._delete_stubs(
            PURE_STUBS_LSE, "LSE", "Pure stubs (LSE)", dry_run
        )

        # Cat 2a NMS stubs
        total_deleted += self._delete_stubs(
            CAT2A_NMS_STUBS, "NMS", "Cat 2a NMS stubs", dry_run
        )

        self.stdout.write(f"\nTotal rows {'would be ' if dry_run else ''}deleted: {total_deleted}\n")

        # ----------------------------------------------------------------
        # 2. EXCHANGE FIXES
        # ----------------------------------------------------------------
        self.stdout.write("=== EXCHANGE FIXES (LSE → correct US exchange) ===")

        fix_count = 0
        missing_from_csv = []

        for ticker in EXCHANGE_FIX_TICKERS:
            correct_exchange = us_exchange.get(ticker)
            if not correct_exchange:
                missing_from_csv.append(ticker)
                self.stdout.write(
                    self.style.WARNING(f"  {ticker}: not found in {US_TICKERS_CSV}, skipping")
                )
                continue

            qs = Company.objects.filter(ticker=ticker, exchange="LSE")
            count = qs.count()
            if count == 0:
                self.stdout.write(f"  {ticker}: no LSE row found, skipping")
                continue

            self.stdout.write(
                f"  {ticker}: LSE → {correct_exchange}"
                + (" (would update)" if dry_run else "")
            )
            if not dry_run:
                updated = qs.update(exchange=correct_exchange)
                fix_count += updated
            else:
                fix_count += count

        self.stdout.write(f"\nTotal exchange fixes {'would be ' if dry_run else ''}applied: {fix_count}")

        if missing_from_csv:
            self.stdout.write(
                self.style.WARNING(
                    f"\nTickers not found in US CSV (check manually): {missing_from_csv}"
                )
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run complete. Run without --dry-run to apply."))
        else:
            self.stdout.write(self.style.SUCCESS("\nDone."))

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _delete_stubs(self, tickers, exchange, label, dry_run):
        """Delete (or report) stub rows for the given tickers+exchange."""
        self.stdout.write(f"\n{label}:")
        deleted_count = 0

        for ticker in tickers:
            qs = Company.objects.filter(ticker=ticker, exchange=exchange).annotate(
                fin_count=Count("financials")
            )
            rows = list(qs)
            if not rows:
                self.stdout.write(f"  {ticker}/{exchange}: not found, skipping")
                continue

            for company in rows:
                fin = company.fin_count
                name = company.name or "(no name)"
                if fin > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {ticker}/{exchange} [{name}]: has {fin} financials — skipping "
                            f"(unexpected, please review manually)"
                        )
                    )
                    continue

                self.stdout.write(
                    f"  {ticker}/{exchange} [{name}]: 0 financials"
                    + (" → would delete" if dry_run else " → deleted")
                )
                if not dry_run:
                    company.delete()
                deleted_count += 1

        return deleted_count
