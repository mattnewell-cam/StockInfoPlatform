"""
Import db_export.json into Postgres.

Usage:
1. Set DATABASE_URL env var to your Render Postgres URL
2. Run: python import_to_postgres.py
"""
import json
import os

# Must set DATABASE_URL before importing Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.contrib.auth.models import User
from companies.models import (
    Company, Financial, StockPrice, Note, NoteCompany,
    DiscussionThread, DiscussionMessage, ChatSession, ChatMessage
)

def run():
    with open('db_export.json', 'r') as f:
        data = json.load(f)

    # Import users first
    print("Importing users...")
    for row in data.get('auth_user', []):
        User.objects.update_or_create(
            id=row['id'],
            defaults={
                'username': row['username'],
                'email': row['email'],
                'password': row['password'],
                'is_staff': row['is_staff'],
                'is_active': row['is_active'],
                'is_superuser': row['is_superuser'],
                'date_joined': row['date_joined'],
                'last_login': row['last_login'],
                'first_name': row.get('first_name', ''),
                'last_name': row.get('last_name', ''),
            }
        )
    print(f"  {len(data.get('auth_user', []))} users")

    # Import companies
    print("Importing companies...")
    for row in data.get('companies_company', []):
        Company.objects.update_or_create(
            id=row['id'],
            defaults={
                'name': row['name'],
                'ticker': row['ticker'],
                'exchange': row.get('exchange', ''),
                'currency': row.get('currency', ''),
                'FYE_month': row.get('FYE_month', 12),
                'sector': row.get('sector', ''),
                'industry': row.get('industry', ''),
                'description': row.get('description', ''),
                'special_sits': row.get('special_sits', ''),
                'writeups': row.get('writeups'),
            }
        )
    print(f"  {len(data.get('companies_company', []))} companies")

    # Import financials
    print("Importing financials...")
    Financial.objects.all().delete()
    financials = []
    for row in data.get('companies_financial', []):
        financials.append(Financial(
            id=row['id'],
            company_id=row['company_id'],
            statement=row['statement'],
            metric=row['metric'],
            period_end_date=row['period_end_date'],
            value=row['value'],
        ))
    Financial.objects.bulk_create(financials, batch_size=500)
    print(f"  {len(financials)} financials")

    # Import stock prices
    print("Importing stock prices (this may take a while)...")
    StockPrice.objects.all().delete()
    prices = []
    for i, row in enumerate(data.get('companies_stockprice', [])):
        prices.append(StockPrice(
            id=row['id'],
            company_id=row['company_id'],
            date=row['date'],
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            volume=row['volume'],
        ))
        if len(prices) >= 10000:
            StockPrice.objects.bulk_create(prices, batch_size=1000)
            prices = []
            print(f"  {i+1} prices...")
    if prices:
        StockPrice.objects.bulk_create(prices, batch_size=1000)
    print(f"  {len(data.get('companies_stockprice', []))} stock prices")

    # Import notes
    print("Importing notes...")
    for row in data.get('companies_note', []):
        Note.objects.update_or_create(
            id=row['id'],
            defaults={
                'user_id': row['user_id'],
                'company_id': row['company_id'],
                'title': row.get('title', ''),
                'content': row['content'],
                'folder': row.get('folder', ''),
                'created_at': row['created_at'],
            }
        )
    print(f"  {len(data.get('companies_note', []))} notes")

    # Import note companies
    print("Importing note companies...")
    for row in data.get('companies_notecompany', []):
        NoteCompany.objects.update_or_create(
            id=row['id'],
            defaults={
                'user_id': row['user_id'],
                'company_id': row['company_id'],
            }
        )
    print(f"  {len(data.get('companies_notecompany', []))} note companies")

    # Import discussion threads
    print("Importing discussion threads...")
    for row in data.get('companies_discussionthread', []):
        DiscussionThread.objects.update_or_create(
            id=row['id'],
            defaults={
                'company_id': row['company_id'],
                'user_id': row['user_id'],
                'title': row['title'],
                'created_at': row['created_at'],
            }
        )
    print(f"  {len(data.get('companies_discussionthread', []))} threads")

    # Import discussion messages
    print("Importing discussion messages...")
    for row in data.get('companies_discussionmessage', []):
        DiscussionMessage.objects.update_or_create(
            id=row['id'],
            defaults={
                'thread_id': row['thread_id'],
                'user_id': row['user_id'],
                'content': row['content'],
                'is_opening': row['is_opening'],
                'created_at': row['created_at'],
            }
        )
    print(f"  {len(data.get('companies_discussionmessage', []))} messages")

    # Import chat sessions
    print("Importing chat sessions...")
    for row in data.get('companies_chatsession', []):
        ChatSession.objects.update_or_create(
            id=row['id'],
            defaults={
                'user_id': row['user_id'],
                'company_id': row['company_id'],
                'title': row.get('title', ''),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            }
        )
    print(f"  {len(data.get('companies_chatsession', []))} chat sessions")

    # Import chat messages
    print("Importing chat messages...")
    for row in data.get('companies_chatmessage', []):
        ChatMessage.objects.update_or_create(
            id=row['id'],
            defaults={
                'session_id': row['session_id'],
                'role': row['role'],
                'content': row['content'],
                'created_at': row['created_at'],
            }
        )
    print(f"  {len(data.get('companies_chatmessage', []))} chat messages")

    print("\nDone!")

if __name__ == '__main__':
    run()
