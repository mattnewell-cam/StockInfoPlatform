from django.core.management.base import BaseCommand

from companies.models import Company
from companies.utils import yfinance_symbol
import yfinance as yf
import csv
from datetime import datetime, timezone

class Command(BaseCommand):
    help = "Add a list (csv) of companies to the database."

    def handle(self, *args, **options):

        with open("tickers.csv") as f:
            tickers = [l[0] for l in list(csv.reader(f))]
        print(tickers)

        for t in tickers:
            try:
                # CSV is raw ticker; default to LSE mapping for legacy file
                yf_ticker = yf.Ticker(yfinance_symbol(t, "LSE"))

                info = yf_ticker.get_info()

                name = info["longName"].replace("Public Limited Company", "plc")
                exchange = info["exchange"]
                currency = info["currency"]
                sector = info.get("sectorDisp", "")
                industry = info.get("industryDisp", "")
                country = info.get("country", "")
                market_cap = info.get("marketCap")
                shares_outstanding = info.get("sharesOutstanding")

                try:
                    ts = info["lastFiscalYearEnd"]
                    fye_month = datetime.fromtimestamp(ts, tz=timezone.utc).date().month
                except Exception:
                    print(f"YF has no FYE data for {t} - assuming Dec.")
                    fye_month = 12

                Company.objects.create(
                    name=name,
                    exchange=exchange,
                    ticker=t,
                    currency=currency,
                    FYE_month=fye_month,
                    sector=sector,
                    industry=industry,
                    country=country,
                    market_cap=market_cap,
                    shares_outstanding=shares_outstanding,
                )

                print(f"Added {name} ({t})")

            except Exception as e:
                print(e)
                print(f"{t} already defined. Skipping...")

