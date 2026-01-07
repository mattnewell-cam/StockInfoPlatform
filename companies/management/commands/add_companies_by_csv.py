from django.core.management.base import BaseCommand

from companies.models import Company
import yfinance as yf
from datetime import datetime, timezone

class Command(BaseCommand):
    help = "Add a list (csv) of companies to the database."

    def handle(self, *args, **options):

        with open("tickers.csv") as csv:
            tickers = csv.readlines()

        for t in tickers:
            try:
                yf_ticker = yf.Ticker(f"{t}.L")

                info = yf_ticker.get_info()

                name = info["longName"].replace("Public Limited Company", "plc")
                exchange = info["exchange"]
                currency = info["currency"]
                ts = info["lastFiscalYearEnd"]
                fye_date = datetime.fromtimestamp(ts, tz=timezone.utc).date().month
                sector = info["sectorDisp"]
                industry = info["industryDisp"]

                Company.objects.create(
                    name=name,
                    exchange=exchange,
                    ticker=t,
                    currency=currency,
                    FYE_month=fye_date,
                    sector=sector,
                    industry=industry,
                )

                print(f"Added {name}")

            except Exception as e:
                print(e)
                print(f"{name} already defined. Skipping...")

