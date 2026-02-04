from django.core.management.base import BaseCommand
from scripts.generate_AI_summaries import generate_summaries_for_ticker, generate_summaries_for_tickers, load_tickers_from_csv


class Command(BaseCommand):
    help = "Generate AI summaries and save directly to the database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Only update a specific ticker'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing summaries in the database (default: only fill empty fields)'
        )
        parser.add_argument(
            '--tickers-csv',
            type=str,
            default=None,
            help='Path to CSV with tickers (default: tickers.csv in repo root)'
        )

    def handle(self, *args, **options):
        ticker_filter = options.get('ticker')
        overwrite = options.get('overwrite', False)
        tickers_csv = options.get('tickers_csv')

        if ticker_filter:
            generate_summaries_for_ticker(ticker_filter, overwrite=overwrite)
        else:
            tickers = load_tickers_from_csv(tickers_csv)
            generate_summaries_for_tickers(tickers, overwrite=overwrite)
