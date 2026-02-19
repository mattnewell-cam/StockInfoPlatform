from datetime import timedelta

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from companies.models import Follow, Notification


class Command(BaseCommand):
    help = "Fetch latest FCA filings for followed companies and create in-app notifications."

    def add_arguments(self, parser):
        parser.add_argument('--size', type=int, default=20, help='Number of filings to fetch per company (default: 20)')
        parser.add_argument('--hours', type=int, default=48, help='Only include filings newer than this many hours (default: 48)')

    def handle(self, *args, **options):
        size = min(max(options.get('size', 20), 1), 200)
        max_age_hours = max(options.get('hours', 48), 1)
        cutoff = timezone.now() - timedelta(hours=max_age_hours)

        follows = Follow.objects.select_related('user', 'company')
        if not follows.exists():
            self.stdout.write('No follows found.')
            return

        created = 0
        skipped = 0

        for follow in follows:
            company = follow.company
            company_name = (company.name or '').strip()
            if not company_name:
                continue

            criteria = [
                {"name": "latest_flag", "value": "Y"},
                {"name": "company_lei", "value": [company_name, "", "disclose_org", "related_org"]},
            ]
            payload = {
                "from": 0,
                "size": size,
                "sort": "submitted_date",
                "sortorder": "desc",
                "criteriaObj": {"criteria": criteria},
            }

            try:
                resp = requests.post(
                    "https://api.data.fca.org.uk/search",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Origin": "https://data.fca.org.uk",
                        "Referer": "https://data.fca.org.uk/",
                    },
                    params={"index": "fca-nsm-searchdata"},
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                hits = resp.json().get("hits", {}).get("hits", [])
            except Exception:
                continue

            for hit in hits:
                src = hit.get("_source", {})
                submitted = src.get("submitted_date") or ""
                if submitted:
                    try:
                        dt = timezone.datetime.fromisoformat(submitted.replace('Z', '+00:00'))
                        if dt < cutoff:
                            continue
                    except Exception:
                        pass

                headline = src.get("title") or src.get("headline") or src.get("document_title") or "Filing update"
                filing_type = src.get("type") or src.get("type_code") or "Filing"
                dedupe_qs = Notification.objects.filter(
                    user=follow.user,
                    company=company,
                    kind="filing",
                    title=headline,
                    created_at__gte=timezone.now() - timedelta(days=7),
                )
                if dedupe_qs.exists():
                    skipped += 1
                    continue

                Notification.objects.create(
                    user=follow.user,
                    company=company,
                    kind="filing",
                    title=headline[:255],
                    body=f"{filing_type} • {company.ticker}",
                    payload={
                        "submitted_date": submitted,
                        "type": filing_type,
                        "type_code": src.get("type_code", ""),
                        "download_link": src.get("download_link", ""),
                    },
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Notifications created: {created}, skipped: {skipped}"))
