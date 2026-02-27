import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from companies.models import Company, Financial


class Command(BaseCommand):
    help = (
        "Build a safe CSV of low-revenue prune candidates from DB financials. "
        "Uses latest Income Statement Revenue/Total Revenues per ticker/exchange."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-revenue",
            type=int,
            default=500_000,
            help="Candidate threshold: latest revenue must be strictly below this value",
        )
        parser.add_argument(
            "--large-cap-guard",
            type=int,
            default=5_000_000_000,
            help=(
                "Exclude companies at/above this market cap from candidates unless "
                "--allow-large-cap is set"
            ),
        )
        parser.add_argument(
            "--allow-large-cap",
            action="store_true",
            help="Allow companies above --large-cap-guard into output",
        )
        parser.add_argument(
            "--out",
            type=str,
            default="data/prune_candidates_revenue.csv",
            help="Output CSV path",
        )

    def handle(self, *args, **options):
        max_revenue = int(options["max_revenue"])
        large_cap_guard = int(options["large_cap_guard"])
        allow_large_cap = bool(options["allow_large_cap"])
        out_path = Path(options["out"])

        companies = Company.objects.all().only("id", "ticker", "exchange", "name", "market_cap")

        rows = []
        excluded_large_cap = []
        missing_revenue = 0

        for company in companies:
            latest = (
                Financial.objects.filter(
                    company=company,
                    statement="IS",
                    metric__name__in=["Revenue", "Total Revenues"],
                )
                .order_by("-period_end_date")
                .values("value", "period_end_date")
                .first()
            )
            if not latest:
                missing_revenue += 1
                continue

            value = latest["value"]
            if value is None or value >= max_revenue:
                continue

            market_cap = company.market_cap
            if (
                not allow_large_cap
                and market_cap is not None
                and market_cap >= large_cap_guard
            ):
                excluded_large_cap.append(
                    (company.ticker, company.exchange, company.name, value, market_cap)
                )
                continue

            rows.append(
                {
                    "ticker": company.ticker,
                    "exchange": company.exchange,
                    "name": company.name,
                    "latest_revenue": value,
                    "period_end_date": latest["period_end_date"],
                    "market_cap": market_cap,
                }
            )

        # De-dupe in-memory by ticker/exchange to prevent accidental duplicate rows.
        deduped = {}
        for row in rows:
            deduped[(row["ticker"], row["exchange"])] = row
        rows = sorted(deduped.values(), key=lambda r: (r["exchange"], r["ticker"]))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "ticker",
                    "exchange",
                    "name",
                    "latest_revenue",
                    "period_end_date",
                    "market_cap",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {len(rows)} candidate rows to {out_path} "
                f"(max_revenue={max_revenue})"
            )
        )
        self.stdout.write(f"Companies missing revenue metric: {missing_revenue}")

        if excluded_large_cap:
            self.stdout.write(
                self.style.WARNING(
                    f"Excluded {len(excluded_large_cap)} large-cap rows by guard "
                    f"(market_cap >= {large_cap_guard})"
                )
            )
            sample = excluded_large_cap[:20]
            self.stdout.write(f"Sample excluded: {sample}")
