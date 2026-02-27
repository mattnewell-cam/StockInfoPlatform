from django.core.management.base import BaseCommand
from django.db.models import Count
from companies.models import Company, Financial, FinancialMetric
from companies.utils import end_of_month, normalize_exchange
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
        return 0

    value_str = value_str.strip()

    # Empty string
    if not value_str:
        return 0

    # Em dash (Unicode) - treat as zero
    if value_str == '\u2014' or value_str == '—':
        return 0

    # Regular dash alone - treat as zero
    if value_str == '-':
        return 0

    # Clean up the string
    cleaned = value_str.replace(',', '').replace('£', '').replace('$', '').strip()

    # Handle parentheses for negative numbers: (123) -> -123
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]

    try:
        return round(float(cleaned))
    except ValueError:
        return 0


# Maps source exchange labels to canonical Company.exchange candidates.
EXCHANGE_ALIASES = {
    "NMS": ["NMS"],
    "NASDAQ": ["NMS"],
    "NASDAQGS": ["NMS"],
    "NASDAQGM": ["NMS"],
    "NASDAQCM": ["NMS"],
    "NYQ": ["NYQ"],
    "NYSE": ["NYQ"],
    "NYS": ["NYQ"],
    "LSE": ["LSE"],
    "AIM": ["AIM"],
}


DEFAULT_FILES = [
    'data/cached_financials_uk.json',
    'data/all_us_financials.json',
]

# Safety bound for obviously corrupt values.
MAX_ABS_VALUE = 1e14

# Metrics that are never rendered to users — dropped by the display pipeline in views.py.
# Keep this in sync with FISCAL_METRICS_DROP in companies/views.py.
# These are skipped at import time to avoid storing data we'll never show.
METRICS_NEVER_DISPLAYED = {
    "Total Revenues % Chg.",
    "Total Revenues %Chg",
    "Operating Margin",
    "Interest Expense",
    "Interest Expense, Total",
    "Interest And Invest. Income",
    "Interest And Investment Income",
    "Interest and Investment Income",
    "Gross Profit Margin",
    "Earnings From Continuing Operations",
    "Net Income to Common Excl. Extra Items",
    "Net Income to Common Incl Extra Items",
    "Total Shares Outstanding",
    "EBT, Excl. Unusual Items",
    "Basic EPS",
    "Diluted EPS",
    "EPS",
    "EPS Diluted",
    "Basic Weighted Average Shares Outstanding",
    "Diluted Weighted Average Shares Outstanding",
    "EBITDA",
    "Effective Tax Rate",
    "Gross Property Plant And Equipment",
    "Accumulated Depreciation",
}


class Command(BaseCommand):
    help = "Load financials from cached_financials_uk.json and data/all_us_financials.json."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            nargs='+',
            default=DEFAULT_FILES,
            help='Path(s) to JSON file(s) (default: cached_financials_uk.json data/all_us_financials.json)'
        )
        parser.add_argument(
            '--ticker',
            type=str,
            help='Only process a specific ticker'
        )
        parser.add_argument(
            '--skip-create',
            action='store_true',
            help='Skip creating new companies (legacy flag; now default behavior)'
        )
        parser.add_argument(
            '--create-missing',
            action='store_true',
            help='Allow creating missing company rows from the financials payload',
        )
        parser.add_argument(
            '--target-exchange',
            type=str,
            help=(
                'Filter companies by this exact exchange value (e.g. LSE, AIM, NMS). '
                'Bypasses EXCHANGE_ALIASES lookup and targets the exact DB row. '
                'Also enables overwrite (ignores existing financials check).'
            )
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Stop after this many companies have had financials saved',
        )
        parser.add_argument(
            '--allow-ticker-fallback',
            action='store_true',
            help=(
                "Allow ticker-only fallback when exchange matching fails. "
                "Off by default to prevent writing to the wrong ticker/exchange row."
            ),
        )

    def handle(self, *args, **options):
        file_paths = options['file']
        single_ticker = options.get('ticker')
        if options.get('create_missing'):
            skip_create = False
        elif options.get('skip_create'):
            skip_create = True
        else:
            # Safe default: do not create new rows unless explicitly requested.
            skip_create = True
        dry_run = options.get('dry_run')
        target_exchange = normalize_exchange(options.get('target_exchange'))
        limit = options.get('limit')
        allow_ticker_fallback = options.get('allow_ticker_fallback')

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))
        if skip_create:
            self.stdout.write("Safe mode: missing companies will be skipped (use --create-missing to override).")

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
            metric_map = self._preload_metrics(data, tickers_to_process, dry_run)
            remaining = None if limit is None else limit - updated_companies
            if remaining is not None and remaining <= 0:
                self.stdout.write("Limit reached, stopping.")
                break
            _created, _updated, _failed = self._process_file(
                data, tickers_to_process, total, skip_create, dry_run, metric_map,
                target_exchange=target_exchange,
                allow_ticker_fallback=allow_ticker_fallback,
                limit=remaining,
            )
            created_companies += _created
            updated_companies += _updated
            failed += _failed

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. Companies created: {created_companies}, "
            f"Companies updated: {updated_companies}, Failed: {failed}"
        ))

    def _preload_metrics(self, data, tickers_to_process, dry_run):
        # Preload metrics once per file to avoid burning the sequence with
        # per-ticker bulk_create(..., ignore_conflicts=True) in Postgres.
        raw_metric_names = set()
        for raw_ticker in tickers_to_process:
            ticker_data = data.get(raw_ticker)
            if not ticker_data:
                continue
            for statement in ['IS', 'BS', 'CF']:
                for row in ticker_data.get(statement, [])[1:]:
                    if row and row[0] and row[0] not in ['Income Statement', 'Balance Sheet', 'Cash Flow']:
                        if row[0] not in METRICS_NEVER_DISPLAYED:
                            raw_metric_names.add(row[0])

        if not raw_metric_names:
            return {}

        if not dry_run:
            FinancialMetric.objects.bulk_create(
                [FinancialMetric(name=n) for n in raw_metric_names], ignore_conflicts=True
            )
            metric_qs = FinancialMetric.objects.filter(name__in=raw_metric_names)
            return {m.name: m for m in metric_qs}

        # Dry-run: include placeholders for missing metrics so counts are accurate.
        existing = {m.name: m for m in FinancialMetric.objects.filter(name__in=raw_metric_names)}
        for name in raw_metric_names:
            if name not in existing:
                existing[name] = FinancialMetric(name=name)
        return existing

    def _process_file(self, data, tickers_to_process, total, skip_create, dry_run, metric_map,
                      target_exchange=None, allow_ticker_fallback=False, limit=None):
        created_companies = 0
        updated_companies = 0
        failed = 0

        for i, raw_ticker in enumerate(tickers_to_process, 1):
            if limit is not None and updated_companies >= limit:
                self.stdout.write(f"Limit of {limit} companies reached, stopping.")
                break
            ticker = raw_ticker.rstrip('.')

            self.stdout.write(f"[{i}/{total}] Processing {ticker}...")

            if raw_ticker not in data:
                self.stderr.write(self.style.ERROR(f"  {ticker} not found in data file"))
                failed += 1
                continue

            ticker_data = data[raw_ticker]
            source_exchange = ticker_data.get("exchange")
            normalized_source_exchange = normalize_exchange(source_exchange)

            if target_exchange:
                # Exact-match lookup: bypass alias resolution entirely.
                company = Company.objects.filter(ticker=ticker, exchange=target_exchange).first()
            else:
                company = self._resolve_company(
                    ticker=ticker,
                    source_exchange=normalized_source_exchange,
                    allow_ticker_fallback=allow_ticker_fallback,
                )

            if isinstance(company, str):
                # Ambiguous match marker with explanatory message.
                self.stderr.write(self.style.ERROR(f"  {company}"))
                failed += 1
                continue
            if company is None:
                if skip_create:
                    self.stdout.write(f"  Skipping {ticker} - not in database")
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  Would create company {ticker} ({normalized_source_exchange or 'LSE'})"
                    )
                    continue

                try:
                    company = self._create_company(
                        ticker=ticker,
                        exchange=normalized_source_exchange or "LSE",
                    )
                    created_companies += 1
                    self.stdout.write(self.style.SUCCESS(f"  Created company: {company.name}"))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  Failed to create company {ticker}: {e}"))
                    failed += 1
                    continue
            elif not target_exchange and not OVERWRITE and company.financials.exists():
                self.stdout.write(f"  Already has financials, skipping")
                continue
            entries = []
            skipped_overflow = 0

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

                    metric_name = row[0]
                    if not metric_name or metric_name in ['Income Statement', 'Balance Sheet', 'Cash Flow']:
                        continue
                    if metric_name in METRICS_NEVER_DISPLAYED:
                        continue
                    metric_obj = metric_map.get(metric_name)
                    if not metric_obj:
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
                        if abs(value) >= MAX_ABS_VALUE:
                            skipped_overflow += 1
                            continue

                        entries.append(Financial(
                            company=company,
                            period_end_date=period_end_date,
                            statement=statement,
                            metric=metric_obj,
                            value=value,
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

            if skipped_overflow:
                self.stdout.write(self.style.WARNING(
                    f"  Skipped {skipped_overflow} values outside Decimal range"
                ))

        return created_companies, updated_companies, failed

    def _exchange_candidates(self, source_exchange):
        normalized = normalize_exchange(source_exchange)
        if not normalized:
            return []
        aliases = EXCHANGE_ALIASES.get(normalized, [normalized])
        out = []
        for ex in aliases:
            value = normalize_exchange(ex)
            if value and value not in out:
                out.append(value)
        return out

    def _pick_best_company(self, queryset):
        rows = list(queryset.annotate(fin_count=Count("financials")))
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]

        rows.sort(key=lambda c: c.fin_count, reverse=True)
        top = rows[0]
        if top.fin_count > 0 and all(r.fin_count == 0 for r in rows[1:]):
            return top
        return None

    def _resolve_company(self, ticker, source_exchange, allow_ticker_fallback=False):
        candidates = self._exchange_candidates(source_exchange)
        if candidates:
            candidate_qs = Company.objects.filter(ticker=ticker, exchange__in=candidates)
            picked = self._pick_best_company(candidate_qs)
            if picked:
                return picked
            if candidate_qs.count() > 1:
                return (
                    f"Ambiguous exchange match for {ticker} from source exchange "
                    f"{source_exchange}: exchanges {sorted(set(candidate_qs.values_list('exchange', flat=True)))}. "
                    "Use --target-exchange explicitly."
                )

        if not allow_ticker_fallback:
            return None

        fallback = self._pick_best_company(Company.objects.filter(ticker=ticker))
        if fallback:
            return fallback

        rows = Company.objects.filter(ticker=ticker).values_list("exchange", flat=True)
        row_count = rows.count()
        if row_count > 1:
            return (
                f"Ambiguous ticker-only fallback for {ticker}: "
                f"{row_count} rows across exchanges {sorted(set(rows))}. "
                "Use --target-exchange explicitly."
            )
        return None

    def _create_company(self, ticker, exchange):
        """Create a minimal company record (no yfinance needed)."""
        normalized_exchange = normalize_exchange(exchange) or "LSE"
        default_currency = "GBp" if normalized_exchange in {"LSE", "AIM"} else "USD"
        company = Company.objects.create(
            name=ticker,  # Just use ticker as name for now
            exchange=normalized_exchange,
            ticker=ticker,
            currency=default_currency,
            FYE_month=12,  # Default to December
        )
        return company
