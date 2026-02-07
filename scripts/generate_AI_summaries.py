from openai import OpenAI
import os
import sys
import csv
from pathlib import Path
import yfinance as yf

DEV_MSGS = {
    "description":
        """
        You write concise, plain-English business overviews.

        Output format:
        1) First line: one sentence describing what the company does (what it makes/does + where + who it sells to).
        2) Then 1-2 short paragraphs (aim 100–200 words total, but be shorter if the business is simple). Prose, not headers + bullet points.

        Content rules:
        - Assume the reader understands general business concepts, but does not have sector knowledge. Your job is simply to help them grasp the business at a high level.
        - Clearly explain the product or service (without belabouring the obvious)
        - Be specific about the product/service (vague phrases like "specialist components" must be qualified or avoided).
        - Use examples of specific products or services where helpful. If self-explanatory, do not include these.
        - Generally, you should explain who customers are, what the revenue model is, where they sit in the value chain only.
        - However, **omit anything obvious** - you wouldn't explain the business model of a bank, for example. If unsure, refer to point 1 - they have good general business knowledge, but no sector knowledge beyond that.
        - If relevant to the business (e.g. manufacturing) explain where their key sites are
        - Avoid jargon; if a technical term is necessary, explain it in plain English.
        - If there are distinct segments, quantify revenue contribution in % ONLY if you are confident; otherwise say "Not disclosed".
        - Do not invent facts. If unsure, say what's unknown rather than guessing.

        Quality control (must do)
        - Before finalising, double-check there are no unqualified vague phrases, unexplained jargon, unexpanded acronyms or marketing fluff
        """,
    "special_sits":
        """
        You are an investment-focused research assistant. The user will provide only a company name and ask you to follow instructions.

        TASK
        Identify and report ONLY big, decision-relevant things, either within the last 12 months or upcoming.
        Your job is to surface special-situation items that could materially change valuation, control, capital structure, governance, or investability.

        SCOPE (FLAG ONLY IF MATERIAL; OTHERWISE OMIT SILENTLY)
        Flag items ONLY if they meet the materiality thresholds. Specifically consider:

        (a) Takeover / strategic interest:
        - Any offer for the company (including rejected approaches).
        - Evidence-based indications an offer may be coming, e.g. (i) new large stake by a competitor/strategic buyer, (ii) formal "strategic review" / "exploring options" / "in discussions" statements, (iii) press rumours, but FLAG CLEARLY AS RUMOURS

        (b) Major disposals / breakups:
        - Spin-offs, demergers, sale of a major division, disposal of a core business, transformational asset sale, reverse takeover.

        (c) Large insider dealings:
        - Director/insider trades that are large and decision-relevant:
          - Value threshold: > £100k, AND
          - Size threshold: > 0.5% of shares outstanding (S/O).
        Include both buys and sells. Ignore small routine transactions.

        (d) Major buybacks / tender offers or special returns:
        - Buyback or special dividend only if > 10% of shares outstanding OR > 10% of market capitalisation.
        Ignore immaterial "token" specials (e.g., small pence-level extras due to marginally better results).

        (e) Delisting / liquidation / wind-down:
        - Any announcement or credible process toward delisting, cancellation of listing, liquidation, administration, solvent wind-down, "return of cash" liquidations.

        (f) Major litigation / regulatory action:
        - Material litigation (by or against the company), major regulatory investigations, fines, injunctions, or outcomes that could move enterprise value or constrain operations.

        (g) Going concern / solvency red flags:
        - Explicit going concern warnings, material uncertainty statements, covenant breach disclosures, near-term liquidity crises.

        (h) Governance / gatekeeper disruptions:
        - Auditor, NOMAD, broker resignations; qualified/modified audit opinions; abrupt CFO/CEO departure (especially sudden or unexplained); other senior finance leadership disruption with obvious governance implications.

        (i) Related-party transactions:
        - Material related-party deals (financing, asset sales, services) that could shift value, control, or create conflicts.

        (j) Significant capital structure events:
        - Significant issuance of equity or debt that changes dilution/leverage meaningfully.
        - Exclude mere refinancings unless they are effectively "rescue" financings, highly dilutive, distressed, or change control economics.
        - Exclude director option/share grants unless VERY material - >5% dilutive

        (k) Accounting restatements
        - Significant financial restatements that cause a material change in profit (past or future) or the balance sheet
        - Ignore accounting changes like revenue recognition (unless suspicious / changed after auditor concerns) or things that moderately improve financials

        (l) Transformational M&A
        - An acquisition or merger (or offer of such) by the company which can genuinely be regarded as transformational
        - If disclosed, headline amount must be at least 20% of the company's market cap. If not disclosed, err on the side of caution - only mention if you're sure it's transformational

        (m) Other special situations (strictly limited):
        - Only include genuinely large, decision-relevant items that do not fit (a)-(l) - like sudden CEO death, major fire, act of god, major product recall
        - This is NOT a catch-all to list everything—use it rarely.

        CRITICAL FILTERING / MATERIALITY RULES
        - Search widely and creatively. Pull at small threads. Do searches that might turn up unexpected things, like "[CEO name] scandal" or "[Company] whistleblower"
        - Before finalising your answer, carefully consider the item(s) - are they GENUINELY big and decision-relevant? If not, discard.
        - If none of (a)-(k) apply, output nothing beyond a brief statement like: "No decision-relevant special-situation items found in the last 12 months."
        - DO NOT state "(x) does not apply" for each category. Do not enumerate non-events. Do not state "omit". Your direct response to this prompt will be displayed to users. Simply ignore all that do not apply. 
        - DO NOT pad output with routine results, normal trading updates, small contracts, minor dividends, standard refinancing, routine board changes, or generic "strategy" commentary.

        EVIDENCE AND SOURCE BEHAVIOUR
        - Prefer primary disclosures (RNS/press releases/filings) and credible financial press.
        - However, rumours / market chatter can be included IF CLEARLY FLAGGED AS SO
        - Details to include: a concise description of the event/item; any relevant quantification (£/%/shares etc.); the relevant dates; any non-obvious details or potential impacts
        - Clearly label what is confirmed vs. reported by third parties; do not turn rumours into facts.
        """,
    "special_sits_qc":
        """
        You are a strict editorial quality-control agent. You will receive a draft special-situations report about a company.

        YOUR ONLY JOB: Remove content that does not belong. You may lightly re-word surrounding text so the result reads naturally after removals, but you must NOT add new information, facts, analysis, or commentary. If everything in the draft is compliant, return it unchanged.

        PERMITTED TOPICS — an item may ONLY stay if it fits one of these categories AND meets materiality:
        (a) Takeover / strategic interest (offers, approaches, large strategic stakes, "strategic review" / "exploring options", press rumours clearly flagged)
        (b) Major disposals / breakups (spin-offs, demergers, sale of a major division, reverse takeover)
        (c) Large insider dealings (> £100k AND > 0.5% of shares outstanding)
        (d) Major buybacks / tender offers / special returns (> 10% of S/O or market cap)
        (e) Delisting / liquidation / wind-down
        (f) Major litigation / regulatory action (material fines, investigations, injunctions)
        (g) Going concern / solvency red flags (going concern warnings, covenant breaches, liquidity crises)
        (h) Governance / gatekeeper disruptions (auditor/NOMAD/broker resignations, qualified audits, abrupt unexplained CEO/CFO departure)
        (i) Material related-party transactions
        (j) Significant capital structure events (highly dilutive equity/debt issuance, rescue financings — NOT routine refinancings or minor option grants)
        (k) Accounting restatements (material restatements — NOT routine accounting policy changes)
        (l) Transformational M&A (acquisitions/mergers at least 20% of market cap)
        (m) Other genuinely extraordinary events (e.g. sudden CEO death, major fire/act of god, major product recall) — this is NOT a catch-all

        REMOVE any content that:
        1. Does not fit categories (a)-(m) above. This includes but is not limited to: normal financial results, revenue/profit updates, trading updates, earnings beats/misses, contract wins, new partnerships, product launches, expansion plans, strategy commentary, dividend declarations (unless special and > 10% of market cap), routine board appointments, AGM dates, results dates, analyst forecasts.
        2. Fits a category but is below materiality thresholds (e.g. small insider trades, minor buybacks, routine refinancings, small related-party deals).
        3. Enumerates categories that do not apply (e.g. "No takeover approaches were identified..."). Non-events must be silently omitted, not listed.
        4. Contains sign-off offers like "If you'd like, I can...", "Would you like me to...", "I can drill into...", or any similar conversational padding.
        5. Contains "Notes" or "Context" sections that merely restate what was NOT found or offer to do more work.
        6. Contains framing headers like "Material items (last 12 months or upcoming)" — jump straight into the items.

        BE AGGRESSIVE. When in doubt, remove. It is far better to strip something borderline than to leave noise in.

        If after removals nothing material remains, return exactly:
        "No decision-relevant special-situation items found in the last 12 months."
        """,
    "writeups":
        """
        TASK:
        Find any dedicated, thesis-style investment write-ups of the company. Look at Substack and similar, as well as individual blog sites.

        WHAT TO IGNORE:
        - News articles or anything of the like
        - Sponsored equity research / paid puff pieces
        - Brief mentions within multi-stock write-ups
        Any write-ups that you include must be dedicated, high-quality write-ups. If there are none that is fine, however ensure you search exhaustively.

        STRUCTURE:
        Give me the links in the form of a python list:
        ["https://example1...", "https://example2...]
        Include NO OTHER text in your response - no "Here is the list:", simply return the list and nothing else.
        """
}

PROMPT = "Follow the instructions given. Company: "

API_KEY = os.getenv("OPENAI_API_KEY")
CATEGORIES = ["description", "special_sits", "writeups"]


BASE_DIR = Path(__file__).resolve().parent


def ensure_django():
    project_root = BASE_DIR.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django
        from django.apps import apps
        if not apps.ready:
            django.setup()
    except Exception:
        import django
        django.setup()


def get_company(ticker):
    ensure_django()
    from companies.models import Company
    try:
        return Company.objects.get(ticker=ticker)
    except Company.DoesNotExist:
        return None


def ask_gpt(category, ticker, model="gpt-5.2", effort="high"):
    """Call OpenAI API to generate a summary for the given category and ticker."""
    client = OpenAI(api_key=API_KEY)

    dev_msg = DEV_MSGS[category]

    try:
        yf_ticker = yf.Ticker(f"{ticker}.L")
        info = yf_ticker.get_info()
        name = info["longName"]
    except Exception as e:
        print(e)
        name = f"The company with the ticker LSE:{ticker}"

    try:
        kwargs = dict(
            model=model,
            tools=[{"type": "web_search"}],
            input=[
                {
                    "role": "developer",
                    "content": dev_msg
                },
                {
                    "role": "user",
                    "content": PROMPT + name
                }
            ],
        )
        if effort:
            kwargs["reasoning"] = {"effort": effort}
        response = client.responses.create(**kwargs
        )

        # Calculate and print cost
        usage = response.usage
        if usage:
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            pricing = {
                "gpt-5.2": {"input": 2.50, "output": 10.00},
                "gpt-5-mini": {"input": 0.30, "output": 1.20},
                "gpt-4o": {"input": 2.50, "output": 10.00},
                "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            }
            rates = pricing.get(model, {"input": 2.50, "output": 10.00})
            cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
            print(f"  Tokens: {input_tokens} in / {output_tokens} out | Cost: ${cost:.6f}")

        return response.output_text

    except Exception as e:
        print(f"GPT call failed for {ticker} ({category}).\nCause: {e}")
        return None


def qc_special_sits(raw_text, model="gpt-5-nano"):
    """Run a QC pass on a special_sits response to strip padding and enforce materiality rules."""
    client = OpenAI(api_key=API_KEY)
    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "developer",
                    "content": DEV_MSGS["special_sits_qc"]
                },
                {
                    "role": "user",
                    "content": raw_text
                }
            ]
        )
        usage = response.usage
        if usage:
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            print(f"  QC pass — Tokens: {input_tokens} in / {output_tokens} out")
        return response.output_text
    except Exception as e:
        print(f"QC pass failed, using raw text. Cause: {e}")
        return raw_text


def generate_summaries_for_ticker(ticker, categories=None, overwrite=False, model="gpt-5.2", effort="high"):
    """
    Generate AI summaries for a single ticker and save to the DB.

    Args:
        ticker: Stock ticker symbol (e.g., "LLOY")
        categories: List of categories to generate. Defaults to all categories.
        overwrite: If False, skip categories that already exist in cache.
                   If True, regenerate and replace existing summaries.
        model: OpenAI model to use.
        effort: Reasoning effort level (low, medium, high).

    Returns:
        dict: The updated summaries for this ticker.
    """
    if categories is None:
        categories = CATEGORIES

    company = get_company(ticker)
    if not company:
        print(f"{ticker} not found in DB. Skipping.")
        return {}

    updated = {}
    for category in categories:
        if category == "description":
            if not overwrite and company.description:
                print(f"Skipping {ticker} - {category} (already exists, use overwrite=True to replace)")
                continue
        elif category == "special_sits":
            if not overwrite and company.special_sits:
                print(f"Skipping {ticker} - {category} (already exists, use overwrite=True to replace)")
                continue
        elif category == "writeups":
            if not overwrite and company.writeups:
                print(f"Skipping {ticker} - {category} (already exists, use overwrite=True to replace)")
                continue

        print(f"Generating {category} for {ticker}...")
        result = ask_gpt(category, ticker, model=model, effort=effort)

        if result is not None and category == "special_sits":
            print(f"Running QC pass on {category} for {ticker}...")
            result = qc_special_sits(result, model=model)

        if result is not None:
            # For writeups, parse the list from the response
            if category == "writeups":
                try:
                    # Try to parse as Python list
                    parsed = eval(result)
                    if isinstance(parsed, list):
                        result = parsed
                    else:
                        result = []
                except:
                    # If parsing fails, store empty list
                    print(f"Warning: Could not parse writeups response for {ticker}")
                    result = []

            if category == "description":
                company.description = result
            elif category == "special_sits":
                company.special_sits = result
            elif category == "writeups":
                company.writeups = result

            company.save(update_fields=[category])
            updated[category] = result
            print(f"Saved {category} for {ticker}")
        else:
            print(f"Failed to generate {category} for {ticker}")

    return updated


def generate_summaries_for_tickers(tickers, categories=None, overwrite=False, model="gpt-5.2", effort="high"):
    """
    Generate AI summaries for multiple tickers.

    Args:
        tickers: List of ticker symbols.
        categories: List of categories to generate. Defaults to all categories.
        overwrite: If False, skip categories that already exist in cache.
        model: OpenAI model to use.
        effort: Reasoning effort level (low, medium, high).
    """
    for ticker in tickers:
        print(f"\n{'='*50}")
        print(f"Processing {ticker}")
        print('='*50)
        generate_summaries_for_ticker(ticker, categories, overwrite, model, effort)


def load_tickers_from_csv(csv_path=None):
    """Load ticker list from CSV file."""
    if csv_path is None:
        csv_path = str((BASE_DIR / ".." / "tickers.csv").resolve())

    with open(csv_path) as f:
        return [row[0] for row in csv.reader(f)]


# ============================================================================
# USAGE EXAMPLES
# ============================================================================
#
# Generate all summaries for a single ticker (skips if existing ticker + category combo exists in cache):
#     generate_summaries_for_ticker("LLOY")
#
# Generate only description for a ticker (ditto):
#     generate_summaries_for_ticker("LLOY", categories=["description"])
#
# Overwrite existing summaries:
#     generate_summaries_for_ticker("LLOY", overwrite=True)
#
# Generate for all tickers in tickers.csv:
#     tickers = load_tickers_from_csv()
#     generate_summaries_for_tickers(tickers)
#
# Generate for specific tickers:
#     generate_summaries_for_tickers(["LLOY", "BARC", "HSBA"])
#
# ============================================================================


if __name__ == "__main__":

    tickers = load_tickers_from_csv()
    generate_summaries_for_tickers(tickers, overwrite=False, model="gpt-4.1")

    # Test run for a single ticker:
    # generate_summaries_for_ticker("LLOY", overwrite=False, model="gpt-4.1")

    pass
