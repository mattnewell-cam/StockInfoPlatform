import calendar
import datetime as dt
import os
import re
import requests
from django.db import connection


def end_of_month(year:int, month) -> dt.date:
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, last_day)


class SQLValidator:
    """Validates generated SQL queries for safety."""

    ALLOWED_TABLES = {
        "companies_company",
        "companies_financial",
        "companies_stockprice",
    }

    BLOCKED_KEYWORDS = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
        "GRANT", "REVOKE", "EXEC", "EXECUTE", "ATTACH", "DETACH",
        "PRAGMA", "VACUUM", "REINDEX", "REPLACE",
    ]

    BLOCKED_PATTERNS = [
        r"--",  # SQL comment
        r"/\*",  # Block comment start
        r"\*/",  # Block comment end
        r";.*\S",  # Multiple statements (semicolon followed by non-whitespace)
    ]

    @classmethod
    def validate(cls, sql: str) -> tuple[bool, str]:
        """
        Validate SQL for safety.
        Returns (is_valid, error_message).
        """
        if not sql or not sql.strip():
            return False, "Empty SQL query"

        sql_upper = sql.upper().strip()

        # Must start with SELECT or WITH (for CTEs)
        if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
            return False, "Query must start with SELECT or WITH"

        # Check for blocked keywords
        for keyword in cls.BLOCKED_KEYWORDS:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper):
                return False, f"Blocked keyword: {keyword}"

        # Check for blocked patterns
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, sql):
                return False, f"Blocked pattern detected"

        # Extract CTE names from WITH clause (e.g., WITH revenue AS (...), margins AS (...))
        # Find all "name AS (" patterns which indicate CTE definitions
        cte_name_pattern = r'\b([A-Z_][A-Z0-9_]*)\s+AS\s*\('
        cte_names = {name.lower() for name in re.findall(cte_name_pattern, sql_upper)}

        # Build set of allowed names (tables + CTEs)
        allowed_names = {t.lower() for t in cls.ALLOWED_TABLES} | cte_names

        # Verify only allowed tables/CTEs are referenced in FROM/JOIN
        table_pattern = r'\b(FROM|JOIN|INTO)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(table_pattern, sql, re.IGNORECASE)
        for _, table in matches:
            if table.lower() not in allowed_names:
                return False, f"Table not allowed: {table}"

        return True, ""


def execute_screener_query(sql: str, limit: int = 100) -> tuple[list[dict], str]:
    """
    Execute a validated screener SQL query.
    Returns (results, error_message).
    """
    # Validate first
    is_valid, error = SQLValidator.validate(sql)
    if not is_valid:
        return [], error

    # Force LIMIT if not present
    sql_upper = sql.upper()
    if "LIMIT" not in sql_upper:
        sql = f"{sql.rstrip().rstrip(';')} LIMIT {limit}"
    else:
        # Check if existing limit is too high
        limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
        if limit_match:
            existing_limit = int(limit_match.group(1))
            if existing_limit > 500:
                sql = re.sub(r'LIMIT\s+\d+', f'LIMIT 500', sql, flags=re.IGNORECASE)

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [col[0] for col in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results, ""
    except Exception as e:
        return [], str(e)


def generate_screener_sql(nl_query: str) -> tuple[str, str]:
    """
    Generate SQL from natural language query using OpenAI.
    Returns (sql, error_message).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "", "Missing OPENAI_API_KEY"

    schema_description = """
Database Schema:

Table: companies_company (alias: c)
- id: INTEGER PRIMARY KEY
- name: VARCHAR(255) - Company name
- ticker: VARCHAR(50) - Stock ticker symbol
- exchange: VARCHAR(50) - Exchange (e.g., "LSE")
- currency: VARCHAR(3) - Currency code (e.g., "GBp")
- sector: VARCHAR(100) - Business sector
- industry: VARCHAR(100) - Industry within sector
- country: VARCHAR(100) - Country of incorporation
- market_cap: BIGINT - Market capitalization in local currency
- shares_outstanding: BIGINT - Number of shares outstanding
- FYE_month: SMALLINT - Fiscal year end month (1-12)

Table: companies_financial (alias: f)
- id: INTEGER PRIMARY KEY
- company_id: INTEGER FOREIGN KEY -> companies_company.id
- period_end_date: DATE - End date of the financial period
- statement: VARCHAR(2) - "IS" (Income Statement), "BS" (Balance Sheet), or "CF" (Cash Flow)
- metric: VARCHAR(100) - Name of the financial metric
- value: DECIMAL - Value of the metric
- currency: VARCHAR(3)

Available metrics in companies_financial:
Income Statement (IS): Revenue, Cost of Goods Sold, Gross Profit, Sales General & Administrative,
  Other Operating Expense, Total Operating Expenses, Operating Profit, Net Interest Income,
  Other Non-Operating Income, Pre-Tax Income, Income Tax, Other Non-recurring, Net Income,
  Shares (Basic), Shares (Diluted)
Balance Sheet (BS): Cash & Equivalents, Accounts Receivable, Inventories, Other Current Assets,
  Total Current Assets, Property Plant & Equipment (Net), Goodwill, Other Intangible Assets,
  Other Assets, Total Assets, Accounts Payable, Tax Payable, Short-Term Debt,
  Current Portion of Capital Leases, Other Current Liabilities, Total Current Liabilities,
  Long-Term Debt, Capital Leases, Pension Liabilities, Other Liabilities, Total Liabilities,
  Retained Earnings, Paid-in Capital, Common Stock, Other, Shareholders Equity, Liabilities & Equity
Cash Flow (CF): Net Income, Depreciation & Amortization, Change in Working Capital,
  Change in Deferred Tax, Stock-Based Compensation, Other, Cash From Operations,
  Property Plant & Equipment, Acquisitions, Intangibles, Cash From Investing,
  Net Issuance of Common Stock, Net Issuance of Debt, Cash From Financing, Free Cash Flow

Table: companies_stockprice (alias: sp)
- id: INTEGER PRIMARY KEY
- company_id: INTEGER FOREIGN KEY -> companies_company.id
- date: DATE
- open: DECIMAL
- high: DECIMAL
- low: DECIMAL
- close: DECIMAL
- volume: BIGINT

Common calculations:
- Operating Margin = Operating Profit / Revenue
- Net Margin = Net Income / Revenue
- Gross Margin = Gross Profit / Revenue
- ROE = Net Income / Shareholders Equity
- Revenue Growth = (Current Revenue - Prior Revenue) / Prior Revenue

Rules:
1. ALWAYS return these columns: c.id, c.ticker, c.name
2. Include computed values as named columns
3. Use table aliases: c for company, f for financial, sp for stockprice
4. Use CTEs (WITH clause) for complex period comparisons
5. Only use SELECT statements - no INSERT, UPDATE, DELETE, etc.
6. IMPORTANT: This is SQLite - use CAST(value AS REAL) for division to avoid integer division (e.g., CAST(f1.value AS REAL) / f2.value)
7. Return ONLY the SQL query, no explanation
"""

    few_shot_examples = """
Example 1: "Companies with positive revenue growth last year"
WITH revenue AS (
  SELECT company_id, period_end_date, value,
         ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY period_end_date DESC) as rn
  FROM companies_financial
  WHERE metric = 'Revenue' AND statement = 'IS'
)
SELECT c.id, c.ticker, c.name,
       r1.value as latest_revenue,
       r2.value as prior_revenue,
       ROUND(CAST(r1.value - r2.value AS REAL) / NULLIF(r2.value, 0) * 100, 2) as revenue_growth_pct
FROM companies_company c
JOIN revenue r1 ON c.id = r1.company_id AND r1.rn = 1
JOIN revenue r2 ON c.id = r2.company_id AND r2.rn = 2
WHERE r1.value > r2.value

Example 2: "Stocks where average operating margin last 3 years exceeds prior 5 years"
WITH margins AS (
  SELECT f1.company_id, f1.period_end_date,
         CAST(f1.value AS REAL) / NULLIF(f2.value, 0) as op_margin,
         ROW_NUMBER() OVER (PARTITION BY f1.company_id ORDER BY f1.period_end_date DESC) as rn
  FROM companies_financial f1
  JOIN companies_financial f2 ON f1.company_id = f2.company_id
    AND f1.period_end_date = f2.period_end_date
    AND f2.metric = 'Revenue' AND f2.statement = 'IS'
  WHERE f1.metric = 'Operating Profit' AND f1.statement = 'IS'
),
recent AS (
  SELECT company_id, AVG(op_margin) as avg_margin
  FROM margins WHERE rn <= 3 GROUP BY company_id
),
prior AS (
  SELECT company_id, AVG(op_margin) as avg_margin
  FROM margins WHERE rn > 3 AND rn <= 8 GROUP BY company_id
)
SELECT c.id, c.ticker, c.name,
       ROUND(recent.avg_margin * 100, 2) as recent_3yr_margin_pct,
       ROUND(prior.avg_margin * 100, 2) as prior_5yr_margin_pct
FROM companies_company c
JOIN recent ON c.id = recent.company_id
JOIN prior ON c.id = prior.company_id
WHERE recent.avg_margin > prior.avg_margin

Example 3: "Companies in the Technology sector with market cap over 100 million"
SELECT c.id, c.ticker, c.name, c.sector, c.market_cap
FROM companies_company c
WHERE c.sector = 'Technology' AND c.market_cap > 100000000
"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": f"{schema_description}\n\n{few_shot_examples}\n\nGenerate ONLY the SQL query for the user's request. No explanation, just SQL."
                },
                {
                    "role": "user",
                    "content": nl_query
                }
            ],
        )

        sql = response.output_text.strip()

        # Clean up markdown code blocks if present
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        sql = sql.strip()

        # Validate the generated SQL
        is_valid, error = SQLValidator.validate(sql)
        if not is_valid:
            return "", f"Generated SQL failed validation: {error}"

        return sql, ""

    except Exception as e:
        return "", f"OpenAI request failed: {e}"


def send_verification_email(to_email: str, code: str) -> bool:
    """Send verification code via Brevo API."""
    api_key = os.getenv("EMAIL_API_KEY")
    if not api_key:
        return False

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "content-type": "application/json"},
            json={
                "sender": {"name": "Tearsheet", "email": "verify@tearsheet.one"},
                "to": [{"email": to_email}],
                "subject": "Your Tearsheet verification code",
                "htmlContent": f'<p>Your verification code is: <strong>{code}</strong></p><p>Expires in 15 minutes.</p>',
            },
        )
        return response.status_code == 201
    except:
        return False