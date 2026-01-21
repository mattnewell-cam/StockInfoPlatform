from openai import OpenAI
import os
import json
import csv
import yfinance as yf

# Path to cached summaries JSON (relative to this script's location)
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "cached_summaries.json")

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

API_KEY = "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"

CATEGORIES = ["description", "special_sits", "writeups"]


def load_cache():
    """Load existing cached summaries from JSON file."""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    """Save cached summaries to JSON file."""
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


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
        response = client.responses.create(
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
            ]
        )
        return response.output_text

    except Exception as e:
        print(f"GPT call failed for {ticker} ({category}).\nCause: {e}")
        return None


def generate_summaries_for_ticker(ticker, categories=None, overwrite=False, model="gpt-5.2"):
    """
    Generate AI summaries for a single ticker and save to cache.

    Args:
        ticker: Stock ticker symbol (e.g., "LLOY")
        categories: List of categories to generate. Defaults to all categories.
        overwrite: If False, skip categories that already exist in cache.
                   If True, regenerate and replace existing summaries.
        model: OpenAI model to use.

    Returns:
        dict: The updated summaries for this ticker.
    """
    if categories is None:
        categories = CATEGORIES

    cache = load_cache()

    if ticker not in cache:
        cache[ticker] = {}

    for category in categories:
        # Check if we should skip this category
        if not overwrite and category in cache[ticker] and cache[ticker][category]:
            print(f"Skipping {ticker} - {category} (already exists, use overwrite=True to replace)")
            continue

        print(f"Generating {category} for {ticker}...")
        result = ask_gpt(category, ticker, model=model)

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

            cache[ticker][category] = result
            save_cache(cache)  # Save after each successful generation
            print(f"Saved {category} for {ticker}")
        else:
            print(f"Failed to generate {category} for {ticker}")

    return cache.get(ticker, {})


def generate_summaries_for_tickers(tickers, categories=None, overwrite=False, model="gpt-5.2"):
    """
    Generate AI summaries for multiple tickers.

    Args:
        tickers: List of ticker symbols.
        categories: List of categories to generate. Defaults to all categories.
        overwrite: If False, skip categories that already exist in cache.
        model: OpenAI model to use.
    """
    for ticker in tickers:
        print(f"\n{'='*50}")
        print(f"Processing {ticker}")
        print('='*50)
        generate_summaries_for_ticker(ticker, categories, overwrite, model)


def load_tickers_from_csv(csv_path=None):
    """Load ticker list from CSV file."""
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(__file__), "..", "tickers.csv")

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
