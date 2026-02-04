from django.core.management.base import BaseCommand
from companies.models import Company
import yfinance as yf
import time


class Command(BaseCommand):
    help = "Update market cap and shares outstanding for all companies from yfinance. Run daily."

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            help='Update a specific ticker only',
        )

    def handle(self, *args, **options):
        ticker = options.get('ticker')

        if ticker:
            companies = Company.objects.filter(ticker=ticker)
        else:
            companies = Company.objects.all()

        total = companies.count()
        updated = 0
        failed = 0

        self.stdout.write(f"Updating market caps for {total} companies...")

        for i, company in enumerate(companies, 1):
            try:
                yf_ticker = yf.Ticker(f"{company.ticker}.L")
                info = yf_ticker.get_info()

                market_cap = info.get("marketCap")
                shares_outstanding = info.get("sharesOutstanding")

                changes = []
                if market_cap is not None:
                    old_cap = company.market_cap
                    if old_cap != market_cap:
                        pct_change = ""
                        if old_cap and old_cap > 0:
                            pct = ((market_cap - old_cap) / old_cap) * 100
                            pct_change = f" ({pct:+.1f}%)"
                        changes.append(f"market_cap: {self._format_cap(old_cap)} -> {self._format_cap(market_cap)}{pct_change}")
                    company.market_cap = market_cap

                if shares_outstanding is not None:
                    if company.shares_outstanding != shares_outstanding:
                        changes.append(f"shares: {self._format_shares(company.shares_outstanding)} -> {self._format_shares(shares_outstanding)}")
                    company.shares_outstanding = shares_outstanding

                if changes:
                    company.save(update_fields=['market_cap', 'shares_outstanding'])
                    self.stdout.write(f"[{i}/{total}] {company.ticker}: {', '.join(changes)}")
                    updated += 1
                else:
                    self.stdout.write(f"[{i}/{total}] {company.ticker}: unchanged")

                # Rate limit
                time.sleep(0.3)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{i}/{total}] {company.ticker}: FAILED - {e}"))
                failed += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done. Updated: {updated}, Failed: {failed}, Unchanged: {total - updated - failed}"))

    def _format_cap(self, value):
        if value is None:
            return "N/A"
        if value >= 1e9:
            return f"{value/1e9:.2f}B"
        if value >= 1e6:
            return f"{value/1e6:.2f}M"
        return f"{value:,}"

    def _format_shares(self, value):
        if value is None:
            return "N/A"
        if value >= 1e9:
            return f"{value/1e9:.2f}B"
        if value >= 1e6:
            return f"{value/1e6:.2f}M"
        return f"{value:,}"
