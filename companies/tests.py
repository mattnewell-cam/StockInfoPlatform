from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from companies.models import Company, Financial
from companies.utils import normalize_exchange, yfinance_symbol
from companies.views import CompanyDetailView


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
