"""
Delete Financial rows for metrics that are never displayed (FISCAL_METRICS_DROP).
Deletes per company_id to leverage the leading column of the unique constraint index,
avoiding a full table scan on a 4.5M-row table with no metric_id index.
"""
from django.core.management.base import BaseCommand
from companies.models import Company, Financial, FinancialMetric


# Keep this in sync with FISCAL_METRICS_DROP in companies/views.py
# and METRICS_NEVER_DISPLAYED in save_cached_financials.py.
METRICS_TO_PRUNE = {
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
    help = "Delete Financial rows for metrics that are never displayed."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Count rows to delete without deleting',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of companies to process per batch (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no deletions will be made"))

        # Resolve metric IDs once
        metric_ids = list(
            FinancialMetric.objects.filter(name__in=METRICS_TO_PRUNE).values_list('id', flat=True)
        )
        if not metric_ids:
            self.stdout.write("No matching metrics found in DB.")
            return

        self.stdout.write(f"Found {len(metric_ids)} metric IDs to prune: {metric_ids}")

        company_ids = list(Company.objects.values_list('id', flat=True).order_by('id'))
        total_companies = len(company_ids)
        total_deleted = 0

        for batch_start in range(0, total_companies, batch_size):
            batch = company_ids[batch_start:batch_start + batch_size]
            if dry_run:
                count = Financial.objects.filter(
                    company_id__in=batch,
                    metric_id__in=metric_ids,
                ).count()
                total_deleted += count
            else:
                deleted, _ = Financial.objects.filter(
                    company_id__in=batch,
                    metric_id__in=metric_ids,
                ).delete()
                total_deleted += deleted

            done = min(batch_start + batch_size, total_companies)
            self.stdout.write(f"  [{done}/{total_companies} companies] {'would delete' if dry_run else 'deleted'} {total_deleted} rows so far")

        action = "Would delete" if dry_run else "Deleted"
        self.stdout.write(self.style.SUCCESS(f"\n{action} {total_deleted} Financial rows across {total_companies} companies."))
        if not dry_run:
            self.stdout.write("Run VACUUM ANALYZE on companies_financial to reclaim space.")
