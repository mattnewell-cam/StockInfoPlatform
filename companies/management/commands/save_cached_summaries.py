from django.core.management.base import BaseCommand
import json
import os
from companies.models import Company


class Command(BaseCommand):
    help = "Load AI-generated summaries from cached_summaries.json and save to the database."

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

    def handle(self, *args, **options):

        with open("cached_summaries.json", "r", encoding="utf-8") as f:
            all_summaries = json.load(f)

        ticker_filter = options.get('ticker')
        overwrite = options.get('overwrite', False)

        if ticker_filter:
            if ticker_filter not in all_summaries:
                self.stderr.write(self.style.ERROR(f"Ticker {ticker_filter} not found in cache"))
                return
            tickers_to_process = {ticker_filter: all_summaries[ticker_filter]}
        else:
            tickers_to_process = all_summaries

        updated_count = 0
        skipped_count = 0

        for ticker, summaries in tickers_to_process.items():
            try:
                company = Company.objects.get(ticker=ticker)
            except Company.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Company {ticker} not found in database, skipping"))
                continue

            updated_fields = []

            # Description
            if 'description' in summaries:
                if overwrite or not company.description:
                    company.description = summaries['description']
                    updated_fields.append('description')

            # Special sits
            if 'special_sits' in summaries:
                if overwrite or not company.special_sits:
                    company.special_sits = summaries['special_sits']
                    updated_fields.append('special_sits')

            # Writeups (list of strings)
            if 'writeups' in summaries:
                if overwrite or not company.writeups:
                    company.writeups = summaries['writeups']
                    updated_fields.append('writeups')

            if updated_fields:
                company.save()
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"{ticker}: updated {', '.join(updated_fields)}"
                ))
            else:
                skipped_count += 1
                self.stdout.write(f"{ticker}: no updates needed")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Updated: {updated_count}, Skipped: {skipped_count}"
        ))
