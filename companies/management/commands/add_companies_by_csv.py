from django.core.management.base import BaseCommand

from companies.models import Company
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
                yf_ticker = yf.Ticker(f"{t}.L")

                info = yf_ticker.get_info()

                name = info["longName"].replace("Public Limited Company", "plc")
                exchange = info["exchange"]
                currency = info["currency"]
                sector = info["sectorDisp"]
                industry = info["industryDisp"]

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
                )

                print(f"Added {name} ({t})")

            except Exception as e:
                print(e)
                print(f"{t} already defined. Skipping...")

