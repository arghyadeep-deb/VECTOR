"""
VECTOR OAuth Integration Registry.

118+ integrations ready for cloud deployment.
When VECTOR goes cloud, set VECTOR_CLOUD_API_URL and these integrations
will wire up automatically via the OAuth flow manager.

Categories: email, productivity, communication, cloud_storage,
            dev_tools, finance, social, analytics, automation
"""
from __future__ import annotations

__all__ = [
    "get_integration",
    "Integration",
    "list_integrations",
    "OAuthRegistry",
]

from dataclasses import dataclass, field


@dataclass
class Integration:
    name: str           # human-readable name
    slug: str           # machine slug (e.g. "gmail")
    category: str
    description: str
    scopes: list[str] = field(default_factory=list)
    docs_url: str = ""
    available: bool = True   # True = wired; False = stub (needs API key)


# ── 118+ Integration definitions ───────────────────────────────────────────────

_INTEGRATIONS: list[Integration] = [
    # ── Email ─────────────────────────────────────────────────────────────────
    Integration("Gmail", "gmail", "email", "Read/send Google Gmail", ["gmail.readonly", "gmail.send"]),
    Integration("Outlook", "outlook", "email", "Microsoft Outlook email", ["mail.read", "mail.send"]),
    Integration("Proton Mail", "protonmail", "email", "Privacy-focused email"),
    Integration("Apple Mail / iCloud", "icloud_mail", "email", "iCloud email integration"),
    Integration("Yahoo Mail", "yahoo_mail", "email", "Yahoo Mail"),
    Integration("Zoho Mail", "zoho_mail", "email", "Zoho Mail"),
    Integration("IMAP/SMTP", "imap_smtp", "email", "Any email via IMAP/SMTP"),

    # ── Productivity ──────────────────────────────────────────────────────────
    Integration("Google Calendar", "google_calendar", "productivity", "Calendar events & scheduling"),
    Integration("Google Docs", "google_docs", "productivity", "Read/write Google Docs"),
    Integration("Google Sheets", "google_sheets", "productivity", "Spreadsheet automation"),
    Integration("Google Drive", "google_drive", "productivity", "File storage & search"),
    Integration("Notion", "notion", "productivity", "Notion pages & databases"),
    Integration("Microsoft 365", "microsoft_365", "productivity", "Office suite integration"),
    Integration("OneDrive", "onedrive", "productivity", "Microsoft file storage"),
    Integration("Airtable", "airtable", "productivity", "Relational database sheets"),
    Integration("Coda", "coda", "productivity", "Coda docs & automations"),
    Integration("Monday.com", "monday", "productivity", "Project management"),
    Integration("Asana", "asana", "productivity", "Task & project tracking"),
    Integration("Trello", "trello", "productivity", "Kanban boards"),
    Integration("ClickUp", "clickup", "productivity", "All-in-one project tool"),
    Integration("Todoist", "todoist", "productivity", "Task management"),
    Integration("Things 3", "things3", "productivity", "Apple task manager", available=False),
    Integration("Obsidian", "obsidian", "productivity", "Local markdown vault — synced via watchdog"),
    Integration("Roam Research", "roam", "productivity", "Networked note-taking"),
    Integration("Evernote", "evernote", "productivity", "Note storage & search"),

    # ── Communication ─────────────────────────────────────────────────────────
    Integration("Slack", "slack", "communication", "Channels & direct messages"),
    Integration("Discord", "discord", "communication", "Servers & DMs"),
    Integration("Telegram", "telegram", "communication", "Bots & groups"),
    Integration("WhatsApp", "whatsapp", "communication", "Messages & groups"),
    Integration("Signal", "signal", "communication", "Encrypted messaging"),
    Integration("Matrix", "matrix", "communication", "Federated messaging"),
    Integration("Mattermost", "mattermost", "communication", "Self-hosted team chat"),
    Integration("Lark / Feishu", "lark", "communication", "Bytedance enterprise chat"),
    Integration("DingTalk", "dingtalk", "communication", "Alibaba enterprise chat"),
    Integration("WeChat", "wechat", "communication", "Chinese super-app"),
    Integration("Line", "line", "communication", "Asian messaging platform"),
    Integration("IRC", "irc", "communication", "Internet Relay Chat"),
    Integration("Twilio SMS", "twilio_sms", "communication", "SMS/voice via Twilio"),
    Integration("Microsoft Teams", "ms_teams", "communication", "Enterprise team chat"),
    Integration("Zoom", "zoom", "communication", "Video calls & recordings"),
    Integration("Google Meet", "google_meet", "communication", "Google video meetings"),

    # ── Developer Tools ───────────────────────────────────────────────────────
    Integration("GitHub", "github", "dev_tools", "Repos, issues, PRs, actions"),
    Integration("GitLab", "gitlab", "dev_tools", "Self-hosted git & CI/CD"),
    Integration("Bitbucket", "bitbucket", "dev_tools", "Atlassian git hosting"),
    Integration("Linear", "linear", "dev_tools", "Issue tracking for engineering"),
    Integration("Jira", "jira", "dev_tools", "Atlassian project management"),
    Integration("Confluence", "confluence", "dev_tools", "Atlassian wiki & docs"),
    Integration("Vercel", "vercel", "dev_tools", "Deploy & monitor web projects"),
    Integration("Railway", "railway", "dev_tools", "Cloud deployments"),
    Integration("Fly.io", "flyio", "dev_tools", "Container deployments"),
    Integration("AWS", "aws", "dev_tools", "Amazon Web Services"),
    Integration("GCP", "gcp", "dev_tools", "Google Cloud Platform"),
    Integration("Azure", "azure", "dev_tools", "Microsoft Azure"),
    Integration("Cloudflare", "cloudflare", "dev_tools", "CDN, DNS, Workers"),
    Integration("Supabase", "supabase", "dev_tools", "Open-source Firebase"),
    Integration("PlanetScale", "planetscale", "dev_tools", "Serverless MySQL"),
    Integration("Neon", "neon", "dev_tools", "Serverless Postgres"),
    Integration("Docker Hub", "dockerhub", "dev_tools", "Container registry"),
    Integration("npm", "npm", "dev_tools", "JavaScript package registry"),
    Integration("PyPI", "pypi", "dev_tools", "Python package index"),
    Integration("Sentry", "sentry", "dev_tools", "Error tracking & performance"),
    Integration("Datadog", "datadog", "dev_tools", "Infrastructure monitoring"),
    Integration("PagerDuty", "pagerduty", "dev_tools", "On-call & incident management"),

    # ── Finance ───────────────────────────────────────────────────────────────
    Integration("Stripe", "stripe", "finance", "Payments & subscriptions"),
    Integration("Razorpay", "razorpay", "finance", "Indian payments gateway"),
    Integration("PayPal", "paypal", "finance", "Digital payments"),
    Integration("Coinbase", "coinbase", "finance", "Crypto exchange"),
    Integration("Binance", "binance", "finance", "Crypto exchange (analysis only)"),
    Integration("NSE/BSE", "nse_bse", "finance", "Indian stock market data"),
    Integration("Yahoo Finance", "yahoo_finance", "finance", "Stock & crypto data"),
    Integration("Alpha Vantage", "alpha_vantage", "finance", "Financial market data API"),
    Integration("CoinGecko", "coingecko", "finance", "Crypto market data"),
    Integration("QuickBooks", "quickbooks", "finance", "Accounting & invoicing"),
    Integration("Notion Finance", "notion_finance", "finance", "Budget tracking in Notion"),

    # ── Social & Content ──────────────────────────────────────────────────────
    Integration("Twitter / X", "twitter", "social", "Tweets, DMs, analytics"),
    Integration("LinkedIn", "linkedin", "social", "Professional networking"),
    Integration("Instagram", "instagram", "social", "Posts, stories, DMs"),
    Integration("YouTube", "youtube", "social", "Videos, analytics, comments"),
    Integration("TikTok", "tiktok", "social", "Short-form video"),
    Integration("Reddit", "reddit", "social", "Subreddits & posts"),
    Integration("Hacker News", "hackernews", "social", "Tech news & discussions"),
    Integration("Product Hunt", "producthunt", "social", "Product launches"),
    Integration("Medium", "medium", "social", "Long-form publishing"),
    Integration("Substack", "substack", "social", "Newsletter platform"),
    Integration("WordPress", "wordpress", "social", "Blog platform"),
    Integration("Ghost", "ghost", "social", "Publishing platform"),

    # ── Analytics ─────────────────────────────────────────────────────────────
    Integration("Google Analytics", "google_analytics", "analytics", "Web traffic analytics"),
    Integration("Mixpanel", "mixpanel", "analytics", "Product analytics"),
    Integration("Amplitude", "amplitude", "analytics", "Behavioral analytics"),
    Integration("Hotjar", "hotjar", "analytics", "Heatmaps & recordings"),
    Integration("PostHog", "posthog", "analytics", "Open-source product analytics"),
    Integration("Plausible", "plausible", "analytics", "Privacy-first analytics"),

    # ── Automation / Integration Platforms ────────────────────────────────────
    Integration("Zapier", "zapier", "automation", "No-code workflow automation"),
    Integration("Make (Integromat)", "make", "automation", "Visual workflow builder"),
    Integration("n8n", "n8n", "automation", "Self-hosted workflow automation"),
    Integration("IFTTT", "ifttt", "automation", "Simple trigger-action flows"),
    Integration("Pipedream", "pipedream", "automation", "Code-based workflows"),
    Integration("Apify", "apify", "automation", "Web scraping & automation"),
    Integration("Composio", "composio", "automation", "Managed OAuth for 150+ SaaS"),
    Integration("Webhooks", "webhooks", "automation", "Inbound/outbound webhook handling"),

    # ── AI & Research ─────────────────────────────────────────────────────────
    Integration("OpenAI", "openai", "ai", "GPT models via API"),
    Integration("Anthropic", "anthropic", "ai", "Claude models — build sessions only"),
    Integration("Ollama", "ollama", "ai", "Local models — primary VECTOR runtime"),
    Integration("HuggingFace", "huggingface", "ai", "Model hub & inference API"),
    Integration("Replicate", "replicate", "ai", "Cloud AI model hosting"),
    Integration("ArXiv", "arxiv", "ai", "Research paper search"),
    Integration("Semantic Scholar", "semantic_scholar", "ai", "Academic paper search"),
    Integration("Perplexity", "perplexity", "ai", "AI-powered search"),
    Integration("ElevenLabs", "elevenlabs", "ai", "AI voice synthesis for content"),

    # ── IoT / Personal Devices ────────────────────────────────────────────────
    Integration("Android ADB", "android_adb", "devices", "Phone control via ADB"),
    Integration("Apple Shortcuts", "apple_shortcuts", "devices", "iOS/macOS automation"),
    Integration("Raspberry Pi", "raspberry_pi", "devices", "GPIO & sensors"),
    Integration("Arduino", "arduino", "devices", "Microcontroller integration"),
    Integration("Philips Hue", "philips_hue", "devices", "Smart lighting"),
    Integration("Home Assistant", "home_assistant", "devices", "Home automation hub"),

    # ── Indian-specific ───────────────────────────────────────────────────────
    Integration("KIIT Portal", "kiit_portal", "education", "KIIT university portal — Playwright scraper"),
    Integration("UPI/BHIM", "upi", "finance", "UPI transaction parsing via SMS ADB"),
    Integration("DigiLocker", "digilocker", "education", "Indian document wallet"),
    Integration("IRCTC", "irctc", "travel", "Indian railway booking"),
]

_REGISTRY: dict[str, Integration] = {i.slug: i for i in _INTEGRATIONS}


class OAuthRegistry:
    """Registry of all VECTOR-supported OAuth integrations."""

    def get(self, slug: str) -> Integration | None:
        return _REGISTRY.get(slug)

    def list_by_category(self, category: str) -> list[Integration]:
        return [i for i in _INTEGRATIONS if i.category == category]

    def search(self, query: str) -> list[Integration]:
        q = query.lower()
        return [i for i in _INTEGRATIONS
                if q in i.name.lower() or q in i.slug or q in i.description.lower()]

    def available(self) -> list[Integration]:
        return [i for i in _INTEGRATIONS if i.available]

    def categories(self) -> list[str]:
        return sorted({i.category for i in _INTEGRATIONS})

    def count(self) -> int:
        return len(_INTEGRATIONS)


def get_integration(slug: str) -> Integration | None:
    return _REGISTRY.get(slug)


def list_integrations(category: str | None = None) -> list[Integration]:
    if category:
        return [i for i in _INTEGRATIONS if i.category == category]
    return list(_INTEGRATIONS)


if __name__ == "__main__":
    reg = OAuthRegistry()
    assert reg.count() >= 100, f"Expected 100+ integrations, got {reg.count()}"
    gmail = reg.get("gmail")
    assert gmail is not None
    cats = reg.categories()
    assert "email" in cats and "dev_tools" in cats
    print(f"OK oauth/registry.py — {reg.count()} integrations across {len(cats)} categories")
