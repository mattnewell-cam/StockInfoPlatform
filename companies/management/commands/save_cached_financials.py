from django.core.management.base import BaseCommand
import csv
from scripts.pull_financials import save_bulk_financials

class Command(BaseCommand):
    help = "Fetch QuickFS financials and save directly to the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tickers-csv",
            default="ftse_tickers.csv",
            help="Path to CSV with tickers (default: ftse_tickers.csv)",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing financials in the DB for each ticker",
        )
        parser.add_argument(
            "--ticker",
            type=str,
            help="Only update a specific ticker",
        )

    def handle(self, *args, **options):
        ticker = options.get("ticker")
        if ticker:
            tickers = [ticker]
        else:
            with open(options["tickers_csv"]) as f:
                tickers = [l[0] for l in list(csv.reader(f))]

        save_bulk_financials(tickers, overwrite=options.get("overwrite", False))
