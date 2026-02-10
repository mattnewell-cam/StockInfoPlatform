import csv

from django.core.management.base import BaseCommand

from companies.utils import normalize_exchange
from scripts.generate_AI_summaries import (
    generate_summaries_for_ticker,
    generate_summaries_for_tickers,
    load_tickers_from_csv,
    CATEGORIES,
)


class Command(BaseCommand):
    help = "Generate AI summaries and save directly to the database."

    def add_arguments(self, parser):
        parser.add_argument('--ticker', type=str, help='Only update a specific ticker')
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing summaries in the database (default: only fill empty fields)'
        )
        parser.add_argument(
            '--exchange',
            type=str,
            default=None,
            help='Optional exchange for single-ticker runs (e.g. LSE, NMS, NYQ)'
        )
        parser.add_argument(
            '--tickers-csv',
            type=str,
            default=None,
            help='Path to CSV with rows ticker[,exchange] (default: tickers.csv in repo root)'
        )
        parser.add_argument(
            '--categories',
            type=str,
            default=','.join(CATEGORIES),
            help='Comma-separated list from: description,special_sits,writeups'
        )
        parser.add_argument('--model', type=str, default='gpt-5-mini', help='OpenAI model to use for generation')
        parser.add_argument('--effort', type=str, default='medium', help='Reasoning effort: low|medium|high')
        parser.add_argument('--budget-usd', type=float, default=None, help='Optional budget cap in USD for this run')
        parser.add_argument(
            '--reserve-usd',
            type=float,
            default=0.0,
            help='Optional safety reserve before cap (e.g. 5 means stop at budget-5)'
        )

    def handle(self, *args, **options):
        ticker_filter = options.get('ticker')
        overwrite = options.get('overwrite', False)
        exchange = normalize_exchange(options.get('exchange'))
        tickers_csv = options.get('tickers_csv')
        model = options.get('model')
        effort = options.get('effort')
        budget_usd = options.get('budget_usd')
        reserve_usd = options.get('reserve_usd', 0.0)

        categories_raw = (options.get('categories') or '').strip()
        categories = [c.strip() for c in categories_raw.split(',') if c.strip()]
        invalid = [c for c in categories if c not in CATEGORIES]
        if invalid:
            self.stderr.write(self.style.ERROR(f"Invalid categories: {', '.join(invalid)}"))
            self.stderr.write(self.style.ERROR(f"Allowed categories: {', '.join(CATEGORIES)}"))
            return

        if ticker_filter:
            _, spent = generate_summaries_for_ticker(
                ticker_filter,
                categories=categories,
                overwrite=overwrite,
                model=model,
                effort=effort,
                exchange=exchange,
            )
            self.stdout.write(self.style.SUCCESS(f"Done. Estimated spend: ${spent:.6f}"))
            return

        csv_path = tickers_csv
        if not csv_path:
            tickers = load_tickers_from_csv(None)
            spent = generate_summaries_for_tickers(
                tickers,
                categories=categories,
                overwrite=overwrite,
                model=model,
                effort=effort,
                budget_usd=budget_usd,
                reserve_usd=reserve_usd,
            )
            self.stdout.write(self.style.SUCCESS(f"Done. Estimated spend: ${spent:.6f}"))
            return

        # Exchange-aware CSV run: rows are ticker[,exchange]
        with open(csv_path, newline="") as f:
            rows = [r for r in csv.reader(f) if r and (r[0] or '').strip()]

        spent = 0.0
        processed = 0
        if budget_usd is not None:
            self.stdout.write(f"Budget cap enabled: ${budget_usd:.2f} (reserve: ${reserve_usd:.2f})")

        for row in rows:
            t = row[0].strip().upper().rstrip('.')
            ex = normalize_exchange(row[1]) if len(row) >= 2 else exchange

            if budget_usd is not None and spent >= max(0.0, budget_usd - reserve_usd):
                self.stdout.write("BUDGET STOP: reached cap threshold.")
                break

            _, cost = generate_summaries_for_ticker(
                t,
                categories=categories,
                overwrite=overwrite,
                model=model,
                effort=effort,
                exchange=ex,
            )
            spent += cost
            processed += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Processed: {processed}. Estimated spend: ${spent:.6f}"))
