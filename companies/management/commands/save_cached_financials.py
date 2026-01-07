from django.core.management.base import BaseCommand
import json
from companies.models import Company
import yfinance as yf
import csv
from datetime import datetime, timezone

class Command(BaseCommand):
    help = "Add all company financials from a local json to the database."

    def handle(self, *args, **options):
        with open("cached_financials.json", "r", encoding="utf-8") as f:
            all_financials = json.load(f)
            for ticker, financials in all_financials.items():
                print(ticker)
                company = Company.objects.filter(ticker=ticker)[0]
                print(company)
                company.pass_annual_financials(financials)
