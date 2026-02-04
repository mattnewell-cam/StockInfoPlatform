from django.core.management.base import BaseCommand
from companies.models import Company
import yfinance as yf
import time


class Command(BaseCommand):
    help = "Backfill country, sector, exchange, industry for existing companies from yfinance."

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Update a specific ticker only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        ticker = options.get('ticker')
        dry_run = options.get('dry_run')

        if ticker:
            companies = Company.objects.filter(ticker=ticker)
        else:
            companies = Company.objects.all()

        total = companies.count()
        updated = 0
        failed = 0

        self.stdout.write(f"Processing {total} companies...")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        for i, company in enumerate(companies, 1):
            try:
                yf_ticker = yf.Ticker(f"{company.ticker}.L")
                info = yf_ticker.get_info()

                country = info.get("country", "")
                sector = info.get("sectorDisp", "") or info.get("sector", "")
                industry = info.get("industryDisp", "") or info.get("industry", "")
                exchange = info.get("exchange", "")

                changes = []
                if country and company.country != country:
                    changes.append(f"country: '{company.country}' -> '{country}'")
                    if not dry_run:
                        company.country = country

                if sector and company.sector != sector:
                    changes.append(f"sector: '{company.sector}' -> '{sector}'")
                    if not dry_run:
                        company.sector = sector

                if industry and company.industry != industry:
                    changes.append(f"industry: '{company.industry}' -> '{industry}'")
                    if not dry_run:
                        company.industry = industry

                if exchange and company.exchange != exchange:
                    changes.append(f"exchange: '{company.exchange}' -> '{exchange}'")
                    if not dry_run:
                        company.exchange = exchange

                if changes:
                    self.stdout.write(f"[{i}/{total}] {company.ticker}: {', '.join(changes)}")
                    if not dry_run:
                        company.save(update_fields=['country', 'sector', 'industry', 'exchange'])
                    updated += 1
                else:
                    self.stdout.write(f"[{i}/{total}] {company.ticker}: no changes needed")

                # Rate limit to avoid hitting yfinance too hard
                time.sleep(0.5)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{i}/{total}] {company.ticker}: FAILED - {e}"))
                failed += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Updated: {updated}, Failed: {failed}, Unchanged: {total - updated - failed}"))
