from django.core.management.base import BaseCommand
from companies.models import Company, StockPrice
import yfinance as yf
from datetime import date, timedelta


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
            help='Fetch full history (default: only fetch missing/new data)'
        )
        parser.add_argument(
            '--years',
            type=int,
            default=10,
            help='Number of years of history to fetch for full refresh (default: 10)'
        )

    def handle(self, *args, **options):
        ticker_filter = options.get('ticker')
        full_refresh = options.get('full', False)
        years = options.get('years', 10)

        if ticker_filter:
            companies = Company.objects.filter(ticker=ticker_filter)
            if not companies.exists():
                self.stderr.write(self.style.ERROR(f"Company {ticker_filter} not found"))
                return
        else:
            companies = Company.objects.all()

        for company in companies:
            self.stdout.write(f"Processing {company.ticker}...")

            try:
                self.fetch_prices(company, full_refresh, years)
                self.stdout.write(self.style.SUCCESS(f"  {company.ticker}: done"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  {company.ticker}: failed - {e}"))

    def fetch_prices(self, company, full_refresh, years):
        yf_ticker = yf.Ticker(f"{company.ticker}.L")

        if full_refresh:
            # Fetch full history
            start_date = date.today() - timedelta(days=years * 365)
            df = yf_ticker.history(start=start_date.isoformat(), end=date.today().isoformat())
        else:
            # Only fetch from last known date
            last_price = StockPrice.objects.filter(company=company).order_by('-date').first()
            if last_price:
                start_date = last_price.date + timedelta(days=1)
                if start_date >= date.today():
                    self.stdout.write(f"  {company.ticker}: already up to date")
                    return
            else:
                # No data yet, fetch full history
                start_date = date.today() - timedelta(days=years * 365)

            df = yf_ticker.history(start=start_date.isoformat(), end=date.today().isoformat())

        if df.empty:
            self.stdout.write(f"  {company.ticker}: no new data")
            return

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
        created = StockPrice.objects.bulk_create(records, ignore_conflicts=True)
        self.stdout.write(f"  {company.ticker}: added {len(records)} price records")
