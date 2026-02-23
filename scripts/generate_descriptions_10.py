#!/usr/bin/env python3
import argparse
import json
import os
import random
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent

DEV_MSG = """
You write concise, plain-English business overviews.

Output format:
1) First line: one sentence describing what the company does (what it makes/does + where + who it sells to).
2) Then 1-2 short paragraphs (aim 100-200 words total, but be shorter if the business is simple). Prose only.

Content rules:
- Assume the reader understands general business concepts, but does not have sector knowledge.
- Clearly explain the product or service (without belaboring the obvious).
- Be specific about the product/service; avoid vague phrases like "specialist components".
- Use examples of specific products or services where helpful; if self-explanatory, omit.
- Explain who customers are and the revenue model when it's not obvious.
- If relevant (e.g., manufacturing), explain where key sites are located.
- Avoid jargon; if a technical term is necessary, explain it plainly.
- If there are distinct segments, quantify revenue contributions only if certain; otherwise say "Not disclosed".
- Do not invent facts. If unsure, say what's unknown.

Quality control:
- Remove unqualified vague phrases, unexplained jargon, unexpanded acronyms, or marketing fluff.
""".strip()

PROMPT_TEMPLATE = "Follow the instructions given. Company: {name}"

# Pricing (USD per 1M tokens) from OpenAI pricing docs (see README output for citations).
PRICING = {
    "gpt-4o-mini": {
        "input": 0.15,
        "cached_input": 0.075,
        "output": 0.60,
    },
    "gpt-5-mini": {
        "input": 0.25,
        "cached_input": 0.025,
        "output": 2.00,
    },
}

WEB_SEARCH_CALL_COST_PER_1K = 10.0

def ensure_django():
    if str(BASE_DIR) not in sys.path:
        sys.path.append(str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()


def load_companies(limit: int):
    ensure_django()
    from companies.models import Company

    qs = Company.objects.filter(description="")
    ids = list(qs.values_list("id", flat=True))
    if not ids:
        return []
    random.shuffle(ids)
    picked = ids[:limit]
    companies = list(Company.objects.filter(id__in=picked))
    by_id = {c.id: c for c in companies}
    return [by_id[i] for i in picked if i in by_id]


def get_cached_tokens(usage):
    if not usage:
        return 0
    for attr in ("input_tokens_details", "prompt_tokens_details"):
        details = getattr(usage, attr, None)
        if details is not None:
            return getattr(details, "cached_tokens", 0) or 0
    return 0


def usage_to_dict(usage):
    if not usage:
        return {}
    data = {}
    for attr in ("input_tokens", "output_tokens", "total_tokens"):
        if hasattr(usage, attr):
            data[attr] = getattr(usage, attr) or 0
    cached = get_cached_tokens(usage)
    data.setdefault("input_tokens_details", {})
    data["input_tokens_details"]["cached_tokens"] = cached
    return data


def compute_cost(model: str, usage):
    price = PRICING[model]
    in_tokens = getattr(usage, "input_tokens", 0) or 0
    out_tokens = getattr(usage, "output_tokens", 0) or 0
    cached_tokens = get_cached_tokens(usage)
    billable_in = max(in_tokens - cached_tokens, 0)
    cost_input = (billable_in / 1_000_000) * price["input"]
    cost_cached = (cached_tokens / 1_000_000) * price["cached_input"]
    cost_output = (out_tokens / 1_000_000) * price["output"]
    return {
        "input_tokens": in_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": out_tokens,
        "input_cost": cost_input,
        "cached_input_cost": cost_cached,
        "output_cost": cost_output,
        "total_cost": cost_input + cost_cached + cost_output,
        "rates_per_1m": price,
    }

def count_web_search_calls(output_items):
    count = 0
    for item in output_items or []:
        item_type = getattr(item, "type", None)
        if item_type == "web_search_call":
            count += 1
    return count


def build_prompt(company):
    name = (company.name or "").strip() or (company.ticker or "").strip() or "Unknown"
    return PROMPT_TEMPLATE.format(
        name=name,
    )


def parse_args():
    today = date.today().isoformat()
    default_out = BASE_DIR / "data" / f"generated_descriptions_{today}_v4.jsonl"
    parser = argparse.ArgumentParser(description="Generate 10 company descriptions via OpenAI API")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", type=str, default="gpt-5-mini")
    parser.add_argument("--reasoning", type=str, default="low")
    parser.add_argument("--output", type=Path, default=default_out)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_existing(output_path: Path):
    existing = {}
    if not output_path.exists():
        return existing
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = record.get("company_id")
        if key is not None:
            existing[key] = record
    return existing


def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    args = parse_args()
    if args.model not in PRICING:
        raise RuntimeError(f"Model {args.model} missing pricing config")

    client = OpenAI(api_key=api_key, timeout=120)

    companies = load_companies(args.limit)
    if not companies:
        print("No companies with blank descriptions found.")
        return

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing(output_path)

    total_cost = 0.0
    total_web_search_calls = 0
    total_web_search_cost = 0.0
    processed = 0

    with output_path.open("a", encoding="utf-8") as f:
        for company in companies:
            if company.id in existing and not args.overwrite:
                continue

            prompt = build_prompt(company)
            input_messages = [
                {"role": "developer", "content": DEV_MSG},
                {"role": "user", "content": prompt},
            ]

            response = client.responses.create(
                model=args.model,
                input=input_messages,
                tools=[{"type": "web_search"}],
                reasoning={"effort": args.reasoning},
                max_output_tokens=800,
            )

            output_text = response.output_text
            usage = response.usage
            cost = compute_cost(args.model, usage)
            total_cost += cost["total_cost"]
            processed += 1
            web_search_calls = count_web_search_calls(response.output)
            web_search_cost = (web_search_calls / 1000) * WEB_SEARCH_CALL_COST_PER_1K
            total_web_search_calls += web_search_calls
            total_web_search_cost += web_search_cost

            record = {
                "run_timestamp": datetime.utcnow().isoformat() + "Z",
                "company_id": company.id,
                "ticker": company.ticker,
                "name": company.name,
                "exchange": company.exchange,
                "model": args.model,
                "input_messages": input_messages,
                "output_text": output_text,
                "response_output": [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in (response.output or [])
                ],
                "response_status": response.status,
                "response_incomplete_details": (
                    response.incomplete_details.model_dump()
                    if hasattr(response.incomplete_details, "model_dump")
                    else response.incomplete_details
                ),
                "usage": usage_to_dict(usage),
                "cost": cost,
                "web_search_call_count": web_search_calls,
                "web_search_tool_call_cost": web_search_cost,
            }
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
            f.flush()

            print(f"{company.ticker} {company.name}: ${cost['total_cost']:.6f}")

    print(f"Generated {processed} descriptions. Total cost: ${total_cost:.6f}")
    print(
        f"Web search tool calls: {total_web_search_calls} | "
        f"Estimated tool call cost: ${total_web_search_cost:.6f}"
    )
    print(f"Cache file: {output_path}")


if __name__ == "__main__":
    main()
