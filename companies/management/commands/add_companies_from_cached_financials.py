from django.core.management.base import BaseCommand
from companies.models import Company
from companies.utils import yfinance_symbol
import csv
import yfinance as yf
from datetime import datetime, timezone


class Command(BaseCommand):
    help = "Add companies from a tickers CSV that are missing from the database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--tickers-csv',
            type=str,
            default='tickers.csv',
            help='Path to tickers CSV (default: tickers.csv)'
        )

    def handle(self, *args, **options):
        tickers_csv = options.get('tickers_csv')
        try:
            with open(tickers_csv) as f:
                tickers = [row[0] for row in csv.reader(f)]
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to read tickers CSV: {e}"))
            return

        if not tickers:
            self.stdout.write("No tickers in CSV.")
            return

        added = 0
        skipped = 0
        for t in tickers:
            if Company.objects.filter(ticker=t).exists():
                skipped += 1
                continue

            try:
                # CSV is raw ticker; default to LSE mapping for legacy file
                yf_ticker = yf.Ticker(yfinance_symbol(t, "LSE"))
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
