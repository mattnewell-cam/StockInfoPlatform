from django.core.management.base import BaseCommand
from companies.models import Company, StockPrice
import yfinance as yf
import pandas as pd
from datetime import date, timedelta
import time


class Command(BaseCommand):
    help = "Fetch historical stock prices from yfinance and save to database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Only update a specific ticker'
        )
        parser.add_argument(
            '--full',
            action='store_true',
            help='Fetch all available history (default: only fetch missing/new data)'
        )
        parser.add_argument(
            '--missing-only',
            action='store_true',
            help='Only process companies with no price data'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay between requests in seconds (default: 1.0)'
        )
        parser.add_argument(
            '--retries',
            type=int,
            default=3,
            help='Number of retries for failed requests (default: 3)'
        )

    def handle(self, *args, **options):
        ticker_filter = options.get('ticker')
        full_refresh = options.get('full', False)
        missing_only = options.get('missing_only', False)
        self.delay = options.get('delay', 1.0)
        self.retries = options.get('retries', 3)

        if ticker_filter:
            companies = Company.objects.filter(ticker=ticker_filter)
            if not companies.exists():
                self.stderr.write(self.style.ERROR(f"Company {ticker_filter} not found"))
                return
        elif missing_only:
            # Only companies with no price data
            companies = Company.objects.filter(prices__isnull=True).distinct()
            self.stdout.write(f"Found {companies.count()} companies with no price data")
        else:
            companies = Company.objects.all()

        for i, company in enumerate(companies):
            self.stdout.write(f"Processing {company.ticker}...")

            try:
                self.fetch_prices(company, full_refresh)
                self.stdout.write(self.style.SUCCESS(f"  {company.ticker}: done"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  {company.ticker}: failed - {e}"))

            # Rate limiting delay (skip for last item)
            if self.delay > 0 and i < len(list(companies)) - 1:
                time.sleep(self.delay)

    def fetch_prices(self, company, full_refresh):
        # Replace dots with hyphens for yfinance (e.g., BT.A -> BT-A)
        yf_symbol = company.ticker.replace('.', '-')
        yf_full = f"{yf_symbol}.L"

        # Check if we need to fetch
        last_price = StockPrice.objects.filter(company=company).order_by('-date').first()
        if last_price and not full_refresh:
            start_date = last_price.date + timedelta(days=1)
            if start_date >= date.today():
                self.stdout.write(f"  {company.ticker}: already up to date")
                return
            start = start_date.isoformat()
            end = date.today().isoformat()
        else:
            start = None
            end = None

        df = None
        for attempt in range(self.retries):
            try:
                # Use yf.download() instead of Ticker.history() - more robust
                if start and end:
                    df = yf.download(yf_full, start=start, end=end, progress=False, auto_adjust=True)
                else:
                    df = yf.download(yf_full, period="max", progress=False, auto_adjust=True)

                # If we got data or empty (not an error), break
                if df is not None:
                    break

            except Exception as e:
                if attempt < self.retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff
                    self.stdout.write(f"  {company.ticker}: retry {attempt + 1}/{self.retries} in {wait_time}s...")
                    time.sleep(wait_time)

        if df is None or df.empty:
            self.stdout.write(f"  {company.ticker}: no new data")
            return

        # Handle multi-level columns from yf.download
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Prepare records
        records = []
        for idx, row in df.iterrows():
            price_date = idx.date() if hasattr(idx, 'date') else idx
            records.append(StockPrice(
                company=company,
                date=price_date,
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=int(row['Volume'])
            ))

        # Bulk insert, ignore conflicts (duplicates)
        StockPrice.objects.bulk_create(records, ignore_conflicts=True)
        self.stdout.write(f"  {company.ticker}: added {len(records)} price records")
