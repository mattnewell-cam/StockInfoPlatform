from openai import OpenAI
import os
import requests
import csv
import yfinance as yf

DEV_MSGS = {
    "business description":
        """
        You write concise, plain-English business overviews.
        
        Output format:
        1) First line: one sentence describing what the company does (what it makes/does + where + who it sells to).
        2) Then 1-2 short paragraphs (aim 100–200 words total, but be shorter if the business is simple). Prose, not headers + bullet points.
        
        Content rules:
        - Assume the reader understands general business concepts, but does not have sector knowledge. Your job is simply to help them grasp the business at a high level.
        - Clearly explain the product or service (without belabouring the obvious)
        - Be specific about the product/service (vague phrases like “specialist components” must be qualified or avoided).
        - Use examples of specific products or services where helpful. If self-explanatory, do not include these.
        - Generally, you should explain who customers are, what the revenue model is, where they sit in the value chain only, but omit any of these that are obvious
        - If relevant to the business (e.g. manufacturing) explain where their key sites are
        - Avoid jargon; if a technical term is necessary, explain it in plain English.
        - If there are distinct segments, quantify revenue contribution in % ONLY if you are confident; otherwise say “Not disclosed”.
        - Do not invent facts. If unsure, say what’s unknown rather than guessing.
        
        Quality control (must do)
        - Before finalising, double-check there are no unqualified vague phrases, unexplained jargon, unexpanded acronyms or marketing fluff 
        """,
    "special sits monitor":
        """
        You are an investment-focused research assistant. The user will provide only a company name and ask you to follow instructions.
        
        TASK
        Identify and report ONLY big, decision-relevant things, either within the last 12 months or upcoming.
        Your job is to surface special-situation items that could materially change valuation, control, capital structure, governance, or investability.
        
        SCOPE (FLAG ONLY IF MATERIAL; OTHERWISE OMIT SILENTLY)
        Flag items ONLY if they meet the materiality thresholds. Specifically consider:
        
        (a) Takeover / strategic interest:
        - Any offer for the company (including rejected approaches).
        - Evidence-based indications an offer may be coming, e.g. (i) new large stake by a competitor/strategic buyer, (ii) formal “strategic review” / “exploring options” / “in discussions” statements, (iii) press rumours, but FLAG CLEARLY AS RUMOURS
        
        (b) Major disposals / breakups:
        - Spin-offs, demergers, sale of a major division, disposal of a core business, transformational asset sale, reverse takeover.
        
        (c) Large insider dealings:
        - Director/insider trades that are large and decision-relevant:
          - Value threshold: > £100k, AND
          - Size threshold: > 0.5% of shares outstanding (S/O).
        Include both buys and sells. Ignore small routine transactions.
        
        (d) Major buybacks / tender offers or special returns:
        - Buyback or special dividend only if > 10% of shares outstanding OR > 10% of market capitalisation.
        Ignore immaterial “token” specials (e.g., small pence-level extras due to marginally better results).
        
        (e) Delisting / liquidation / wind-down:
        - Any announcement or credible process toward delisting, cancellation of listing, liquidation, administration, solvent wind-down, “return of cash” liquidations.
        
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
        - Exclude mere refinancings unless they are effectively “rescue” financings, highly dilutive, distressed, or change control economics.
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
        - If none of (a)-(k) apply, output nothing beyond a brief statement like: “No decision-relevant special-situation items found in the last 12 months.”
        - DO NOT state “(x) does not apply” for each category. Do not enumerate non-events.
        - DO NOT pad output with routine results, normal trading updates, small contracts, minor dividends, standard refinancing, routine board changes, or generic “strategy” commentary.
        
        EVIDENCE AND SOURCE BEHAVIOUR
        - Prefer primary disclosures (RNS/press releases/filings) and credible financial press. 
        - However, rumours / market chatter can be included IF CLEARLY FLAGGED AS SO
        - Details to include: a concise description of the event/item; any relevant quantification (£/%/shares etc.); the relevant dates; any non-obvious details or potential impacts
        - Clearly label what is confirmed vs. reported by third parties; do not turn rumours into facts.
        """,
    "write-ups":
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


def ask_gpt(category, ticker, model="gpt-5.2", effort="high", ):
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
            # reasoning={"effort": effort},
            tools=[{"type": "web_search"}],
            input=[
                {
                "role": "developer",
                "content": dev_msg
                },
                {"role": "user",
                 "content": PROMPT + name
                 }
            ]
        )
        return response.output_text

    except Exception as e:
        print(f"GPT call failed for {ticker}.\nCause: {e}")
        return



with open("../tickers.csv") as f:
    tickers = [l[0] for l in list(csv.reader(f))]

for t in tickers:
    resp = ask_gpt("write-ups", t, model="gpt-4.1")
    print(resp)



