from django.core.management.base import BaseCommand
from companies.models import Company, Financial
from companies.utils import end_of_month
import json
import re


# Set to True to re-process companies that already exist in the database
OVERWRITE = False


# Month name to number mapping
MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}


def parse_date_header(header):
    """
    Parse date headers like "Dec '24", "Dec '23", "LTM", "Dec '27 (E)"
    Returns (month, year, is_estimate, is_ltm) or None if can't parse.
    """
    if not header or not isinstance(header, str):
        return None

    header = header.strip()

    # Skip estimates
    if '(E)' in header:
        return None

    # Handle LTM (Last Twelve Months) - similar to TTM
    if header == 'LTM':
        return (None, None, False, True)

    # Try to parse "Mon 'YY" format
    match = re.match(r"([A-Za-z]{3})\s*'(\d{2})", header)
    if match:
        month_str, year_short = match.groups()
        month = MONTH_MAP.get(month_str.capitalize())
        if month:
            # Convert 2-digit year to 4-digit
            year_int = int(year_short)
            year = 2000 + year_int if year_int < 50 else 1900 + year_int
            return (month, year, False, False)

    return None


def parse_value(value_str):
    """
    Parse a value string, converting em dashes and other special chars to 0.
    """
    if not value_str or not isinstance(value_str, str):
        return 0.0

    value_str = value_str.strip()

    # Empty string
    if not value_str:
        return 0.0

    # Em dash (Unicode) - treat as zero
    if value_str == '\u2014' or value_str == '—':
        return 0.0

    # Regular dash alone - treat as zero
    if value_str == '-':
        return 0.0

    # Clean up the string
    cleaned = value_str.replace(',', '').replace('£', '').replace('$', '').strip()

    # Handle parentheses for negative numbers: (123) -> -123
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# Maps fiscal-normalised exchange names → yfinance exchange codes stored in Company.exchange
EXCHANGE_ALIASES = {
    "NasdaqGS": ["NMS"],
    "NYSE": ["NYQ"],
    "LSE": ["LSE"],
}


DEFAULT_FILES = [
    'cached_financials_uk.json',
    'data/sp500_financials.json',
]


class Command(BaseCommand):
    help = "Load financials from cached_financials_uk.json and data/sp500_financials.json."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            nargs='+',
            default=DEFAULT_FILES,
            help='Path(s) to JSON file(s) (default: cached_financials_uk.json data/sp500_financials.json)'
        )
        parser.add_argument(
            '--ticker',
            type=str,
            help='Only process a specific ticker'
        )
        parser.add_argument(
            '--skip-create',
            action='store_true',
            help='Skip creating new companies (only update existing)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )

    def handle(self, *args, **options):
        file_paths = options['file']
        single_ticker = options.get('ticker')
        skip_create = options.get('skip_create')
        dry_run = options.get('dry_run')

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        created_companies = 0
        updated_companies = 0
        failed = 0

        for file_path in file_paths:
            self.stdout.write(f"\nLoading {file_path}...")
            try:
                with open(file_path) as f:
                    data = json.load(f)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to load {file_path}: {e}"))
                continue

            tickers_to_process = [single_ticker] if single_ticker else list(data.keys())
            total = len(tickers_to_process)
            _created, _updated, _failed = self._process_file(
                data, tickers_to_process, total, skip_create, dry_run
            )
            created_companies += _created
            updated_companies += _updated
            failed += _failed

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. Companies created: {created_companies}, "
            f"Companies updated: {updated_companies}, Failed: {failed}"
        ))

    def _process_file(self, data, tickers_to_process, total, skip_create, dry_run):
        created_companies = 0
        updated_companies = 0
        failed = 0

        for i, raw_ticker in enumerate(tickers_to_process, 1):
            ticker = raw_ticker.rstrip('.')

            self.stdout.write(f"[{i}/{total}] Processing {ticker}...")

            if exchange:
                aliases = EXCHANGE_ALIASES.get(exchange, [exchange])
                company = Company.objects.filter(ticker=ticker, exchange__in=aliases).first()
            else:
                company = Company.objects.filter(ticker=ticker).first()
            if company is None:
                if skip_create:
                    self.stdout.write(f"  Skipping {ticker} - not in database")
                    continue

                if dry_run:
                    self.stdout.write(f"  Would create company {ticker}")
                    continue

                try:
                    company = self._create_company(ticker)
                    created_companies += 1
                    self.stdout.write(self.style.SUCCESS(f"  Created company: {company.name}"))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  Failed to create company {ticker}: {e}"))
                    failed += 1
                    continue
            elif not OVERWRITE and company.financials.exists():
                self.stdout.write(f"  Already has financials, skipping")
                continue

            ticker_data = data[raw_ticker]
            exchange = ticker_data.get("exchange")
            entries = []

            for statement in ['IS', 'BS', 'CF']:
                if statement not in ticker_data:
                    continue

                statement_data = ticker_data[statement]
                if not statement_data or len(statement_data) < 2:
                    continue

                headers = statement_data[0]
                date_info = []
                for h in headers[1:]:
                    parsed = parse_date_header(h)
                    date_info.append(parsed)

                for row in statement_data[1:]:
                    if not row:
                        continue

                    metric = row[0]
                    if not metric or metric in ['Income Statement', 'Balance Sheet', 'Cash Flow']:
                        continue

                    for val_idx, value_str in enumerate(row[1:]):
                        if val_idx >= len(date_info):
                            continue

                        date_parsed = date_info[val_idx]
                        if date_parsed is None:
                            continue

                        month, year, is_estimate, is_ltm = date_parsed

                        if is_ltm:
                            if company.FYE_month:
                                recent_year = None
                                for di in date_info:
                                    if di and not di[3] and di[1]:
                                        if recent_year is None or di[1] > recent_year:
                                            recent_year = di[1]

                                if recent_year:
                                    if company.FYE_month > 6:
                                        ltm_year = recent_year + 1
                                        ltm_month = company.FYE_month - 6
                                    else:
                                        ltm_year = recent_year
                                        ltm_month = company.FYE_month + 6
                                    period_end_date = end_of_month(ltm_year, ltm_month)
                                else:
                                    continue
                            else:
                                continue
                        else:
                            if month and year:
                                period_end_date = end_of_month(year, month)
                            elif year and company.FYE_month:
                                period_end_date = end_of_month(year, company.FYE_month)
                            else:
                                continue

                        value = parse_value(value_str)

                        entries.append(Financial(
                            company=company,
                            period_end_date=period_end_date,
                            statement=statement,
                            metric=metric,
                            value=value,
                            currency=company.currency
                        ))

            if entries:
                if dry_run:
                    self.stdout.write(f"  Would create {len(entries)} financial entries")
                else:
                    Financial.objects.bulk_create(entries, ignore_conflicts=True)
                    self.stdout.write(self.style.SUCCESS(f"  Created {len(entries)} financial entries"))
                    updated_companies += 1
            else:
                self.stdout.write(f"  No financial entries to create")

        return created_companies, updated_companies, failed

    def _create_company(self, ticker):
        """Create a minimal company record (no yfinance needed)."""
        company = Company.objects.create(
            name=ticker,  # Just use ticker as name for now
            exchange="LSE",
            ticker=ticker,
            currency="GBp",
            FYE_month=12,  # Default to December
        )
        return company
