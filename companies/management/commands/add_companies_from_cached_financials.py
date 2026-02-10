from datetime import datetime, timezone
import csv

import yfinance as yf
from django.core.management.base import BaseCommand

from companies.models import Company
from companies.utils import normalize_exchange, yfinance_symbol


class Command(BaseCommand):
    help = "Add companies from a tickers CSV that are missing from the database. CSV columns: ticker[,exchange]"

    def add_arguments(self, parser):
        parser.add_argument(
            '--tickers-csv',
            type=str,
            default='tickers.csv',
            help='Path to tickers CSV (default: tickers.csv)'
        )
        parser.add_argument(
            '--default-exchange',
            type=str,
            default='LSE',
            help='Fallback exchange when missing in CSV (default: LSE)'
        )

    def handle(self, *args, **options):
        tickers_csv = options.get('tickers_csv')
        default_exchange = normalize_exchange(options.get('default_exchange') or 'LSE')

        try:
            with open(tickers_csv, newline="") as f:
                rows = list(csv.reader(f))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to read tickers CSV: {e}"))
            return

        if not rows:
            self.stdout.write("No tickers in CSV.")
            return

        added = 0
        skipped = 0
        failed = 0

        for row in rows:
            if not row:
                continue
            ticker = (row[0] or "").strip().upper().rstrip('.')
            if not ticker:
                continue
            exchange = normalize_exchange(row[1] if len(row) >= 2 else default_exchange) or default_exchange

            if Company.objects.filter(ticker=ticker, exchange=exchange).exists():
                skipped += 1
                continue

            try:
                yf_ticker = yf.Ticker(yfinance_symbol(ticker, exchange))
                info = yf_ticker.get_info()

                name = (info.get("longName") or info.get("shortName") or ticker).replace("Public Limited Company", "plc")
                currency = info.get("currency") or ""
                sector = info.get("sectorDisp") or info.get("sector") or ""
                industry = info.get("industryDisp") or info.get("industry") or ""
                country = info.get("country") or ""

                try:
                    ts = info.get("lastFiscalYearEnd")
                    fye_month = datetime.fromtimestamp(ts, tz=timezone.utc).date().month if ts else 12
                except Exception:
                    fye_month = 12

                Company.objects.create(
                    name=name,
                    exchange=exchange,
                    ticker=ticker,
                    currency=currency,
                    FYE_month=fye_month,
                    sector=sector,
                    industry=industry,
                    country=country,
                    market_cap=info.get("marketCap"),
                    shares_outstanding=info.get("sharesOutstanding"),
                )
                added += 1
                self.stdout.write(self.style.SUCCESS(f"Added {name} ({exchange}:{ticker})"))
            except Exception as e:
                failed += 1
                self.stderr.write(self.style.ERROR(f"Failed to add {exchange}:{ticker}: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Added: {added}, Skipped: {skipped}, Failed: {failed}"
        ))
