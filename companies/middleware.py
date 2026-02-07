import re
from django.http import HttpResponse

# Known AI/LLM crawler user-agent patterns
AI_BOT_PATTERNS = [
    r"GPTBot",
    r"ChatGPT-User",
    r"Google-Extended",
    r"CCBot",
    r"anthropic-ai",
    r"ClaudeBot",
    r"Claude-Web",
    r"Bytespider",
    r"Diffbot",
    r"FacebookBot",
    r"PerplexityBot",
    r"YouBot",
    r"Applebot-Extended",
    r"cohere-ai",
    r"AI2Bot",
    r"Ai2Bot-Dolma",
    r"Scrapy",
    r"PetalBot",
    r"Amazonbot",
    r"OAI-SearchBot",
    r"Meta-ExternalAgent",
    r"meta-externalagent",
    r"ImagesiftBot",
    r"Omgilibot",
    r"Timpibot",
    r"VelenpublicBot",
    r"Webzio-Extended",
    r"iaskspider",
]

_AI_BOT_RE = re.compile("|".join(AI_BOT_PATTERNS), re.IGNORECASE)


class BlockAIBotsMiddleware:
    """Return 403 for requests from known AI/LLM crawlers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ua = request.META.get("HTTP_USER_AGENT", "")
        if ua and _AI_BOT_RE.search(ua):
            bot_key = (
                request.GET.get("bot_key", "")
                or request.META.get("HTTP_X_BOT_KEY", "")
            )
            if bot_key != "shut it clunker":
                return HttpResponse("Forbidden", status=403, content_type="text/plain")
        return self.get_response(request)
