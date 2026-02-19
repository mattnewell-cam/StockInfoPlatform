from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load fiscal financials from cached_financials_2.json into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="data/cached_financials_2.json",
            help="Path to cached fiscal JSON (default: data/cached_financials_2.json)",
        )
        parser.add_argument(
            "--ticker",
            type=str,
            help="Only load a specific ticker",
        )
        parser.add_argument(
            "--skip-create",
            action="store_true",
            help="Skip creating missing companies",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without writing",
        )

    def handle(self, *args, **options):
        kwargs = {
            "file": options["file"],
            "ticker": options.get("ticker"),
            "skip_create": options.get("skip_create", False),
            "dry_run": options.get("dry_run", False),
        }
        # Reuse the fiscal loader command directly.
        call_command("load_cached_financials_2", **kwargs)
