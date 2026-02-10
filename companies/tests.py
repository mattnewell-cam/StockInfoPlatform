import json
from datetime import date
from io import StringIO
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from companies.models import Company, Financial, Follow, Notification
from companies.utils import normalize_exchange, yfinance_symbol
from companies.views import (
    CompanyDetailView,
    follow_company,
    unfollow_company,
    notification_list,
    notification_mark_read,
)


class SymbolMappingTests(TestCase):
    def test_normalize_exchange_uppercases_and_strips(self):
        self.assertEqual(normalize_exchange(" lse "), "LSE")
        self.assertEqual(normalize_exchange(""), "")
        self.assertEqual(normalize_exchange(None), "")

    def test_yfinance_symbol_lse_aim_and_us(self):
        self.assertEqual(yfinance_symbol("BT.A", "LSE"), "BT-A.L")
        self.assertEqual(yfinance_symbol("vod", "aim"), "VOD.L")
        self.assertEqual(yfinance_symbol("AAPL", "NMS"), "AAPL")
        self.assertEqual(yfinance_symbol("MSFT", "NYQ"), "MSFT")


class CompanyDetailFiscalPipelineTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.company = Company.objects.create(
            ticker="TEST",
            exchange="LSE",
            name="Test Plc",
            currency="GBP",
            FYE_month=12,
        )

    def _add_financial(self, statement, metric, period_end_date, value):
        Financial.objects.create(
            company=self.company,
            statement=statement,
            metric=metric,
            period_end_date=period_end_date,
            value=value,
            currency="GBP",
        )

    def test_detail_view_uses_fiscal_transformations(self):
        self._add_financial("IS", "Total Revenues", date(2024, 12, 31), 1000)
        self._add_financial("IS", "Cost of Goods Sold, Total", date(2024, 12, 31), 400)
        self._add_financial("IS", "Net Income", date(2024, 12, 31), 120)

        request = self.factory.get(f"/companies/{self.company.ticker}/")
        request.user = AnonymousUser()
        response = CompanyDetailView.as_view()(request, ticker=self.company.ticker)
        response.render()

        is_table = response.context_data["IS_table"]
        metric_names = [row["metric"] for row in is_table["rows"] if "metric" in row]

        # Fiscal rename should be applied: Total Revenues -> Revenue
        self.assertIn("Revenue", metric_names)
        # Original fiscal name should not leak to display
        self.assertNotIn("Total Revenues", metric_names)

    def test_detail_view_handles_empty_financials(self):
        request = self.factory.get(f"/companies/{self.company.ticker}/")
        request.user = AnonymousUser()
        response = CompanyDetailView.as_view()(request, ticker=self.company.ticker)
        response.render()

        self.assertEqual(response.context_data["IS_table"]["rows"], [])
        self.assertEqual(response.context_data["BS_table"]["rows"], [])
        self.assertEqual(response.context_data["CF_table"]["rows"], [])


class SaveCachedFinancialsCommandTests(TestCase):
    @patch("companies.management.commands.save_cached_financials.call_command")
    def test_save_cached_financials_delegates_to_fiscal_loader(self, mock_call_command):
        call_command(
            "save_cached_financials",
            "--file",
            "custom_financials.json",
            "--ticker",
            "ABC",
            "--skip-create",
            "--dry-run",
        )

        mock_call_command.assert_called_once_with(
            "load_cached_financials_2",
            file="custom_financials.json",
            ticker="ABC",
            skip_create=True,
            dry_run=True,
        )


class AddCompaniesByCsvTests(TestCase):
    @patch("companies.management.commands.add_companies_by_csv.yf.Ticker")
    def test_add_companies_accepts_exchange_column(self, mock_ticker_cls):
        class DummyTicker:
            def get_info(self):
                return {
                    "longName": "Acme Inc",
                    "currency": "USD",
                    "sector": "Technology",
                    "industry": "Software",
                    "country": "United States",
                    "marketCap": 123,
                    "sharesOutstanding": 456,
                    "lastFiscalYearEnd": None,
                }

        mock_ticker_cls.return_value = DummyTicker()

        with NamedTemporaryFile("w+", newline="", suffix=".csv") as f:
            f.write("AAPL,NMS\n")
            f.flush()
            call_command("add_companies_by_csv", "--tickers-csv", f.name)

        self.assertTrue(Company.objects.filter(ticker="AAPL", exchange="NMS").exists())


class NotificationFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.company = Company.objects.create(ticker="ABCD", exchange="LSE", name="ABCD plc")
        self.factory = RequestFactory()

    def test_follow_unfollow_endpoints(self):
        req1 = self.factory.post(f"/companies/{self.company.ticker}/follow/")
        req1.user = self.user
        r1 = follow_company(req1, ticker=self.company.ticker)
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(Follow.objects.filter(user=self.user, company=self.company).exists())

        req2 = self.factory.post(f"/companies/{self.company.ticker}/unfollow/")
        req2.user = self.user
        r2 = unfollow_company(req2, ticker=self.company.ticker)
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(Follow.objects.filter(user=self.user, company=self.company).exists())

    def test_notifications_list_and_mark_read(self):
        n = Notification.objects.create(
            user=self.user,
            company=self.company,
            kind="system",
            title="Hello",
            body="World",
        )

        req_list = self.factory.get("/companies/notifications/")
        req_list.user = self.user
        res = notification_list(req_list)
        self.assertEqual(res.status_code, 200)
        payload = json.loads(res.content)
        self.assertEqual(payload["unread_count"], 1)

        req_read = self.factory.post(f"/companies/notifications/{n.id}/read/")
        req_read.user = self.user
        res2 = notification_mark_read(req_read, notification_id=n.id)
        self.assertEqual(res2.status_code, 200)
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)
