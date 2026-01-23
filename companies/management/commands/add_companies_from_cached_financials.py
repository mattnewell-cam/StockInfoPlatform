from django.core.management.base import BaseCommand
from companies.models import Company
import json
import yfinance as yf
from datetime import datetime, timezone


class Command(BaseCommand):
    help = "Add companies from cached_financials.json that are missing from the database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--cache-path',
            type=str,
            default='cached_financials.json',
            help='Path to cached_financials.json (default: cached_financials.json)'
        )

    def handle(self, *args, **options):
        cache_path = options.get('cache_path')
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to read cache: {e}"))
            return

        tickers = sorted(cached.keys())
        if not tickers:
            self.stdout.write("No tickers in cache.")
            return

        added = 0
        skipped = 0
        for t in tickers:
            if Company.objects.filter(ticker=t).exists():
                skipped += 1
                continue

            try:
                yf_ticker = yf.Ticker(f"{t}.L")
                info = yf_ticker.get_info()

                name = info.get("longName") or info.get("shortName") or t
                name = name.replace("Public Limited Company", "plc")
                exchange = info.get("exchange") or ""
                currency = info.get("currency") or ""
                sector = info.get("sectorDisp") or info.get("sector") or ""
                industry = info.get("industryDisp") or info.get("industry") or ""

                try:
                    ts = info.get("lastFiscalYearEnd")
                    fye_month = datetime.fromtimestamp(ts, tz=timezone.utc).date().month if ts else 12
                except Exception:
                    fye_month = 12

                Company.objects.create(
                    name=name,
                    exchange=exchange,
                    ticker=t,
                    currency=currency,
                    FYE_month=fye_month,
                    sector=sector,
                    industry=industry,
                )
                added += 1
                self.stdout.write(self.style.SUCCESS(f"Added {name} ({t})"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to add {t}: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Added: {added}, Skipped: {skipped}"
        ))
