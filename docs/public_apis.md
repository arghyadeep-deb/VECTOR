# VECTOR — Free Public APIs Catalog

Zero-key, zero-cost APIs used across VECTOR districts.
All require no authentication unless noted with `[key-optional]`.

---

## Research District (`agents/districts/research/research_hub.py`)

| Source | URL | What VECTOR uses it for |
|--------|-----|-------------------------|
| DuckDuckGo Instant Answer | `api.duckduckgo.com/?format=json` | Web search — 0 config |
| HackerNews Firebase | `hacker-news.firebaseio.com/v0/...` | Top/new/best stories |
| GitHub Search API | `api.github.com/search/repositories` | Trending repos (60 req/h unauth) |
| ProductHunt GraphQL | `api.producthunt.com/v2/api/graphql` | Daily product launches |
| DEV.to | `dev.to/api/articles` | Developer blog posts |
| ArXiv XML API | `export.arxiv.org/api/query` | Academic papers |
| CoinGecko | `api.coingecko.com/api/v3/...` | Crypto prices + market data |
| Econdb | `econdb.com/api/series/...` | Macroeconomic indicators |
| Crossref | `api.crossref.org/works` | Academic citation search |
| OpenAQ | `api.openaq.org/v2/...` | Air quality (PM2.5, PM10) |
| Yahoo Finance (NSE) | `query1.finance.yahoo.com/v8/finance/chart/` | Indian stock quotes |

---

## Investment District (`agents/districts/investment/stock_analyst.py`)

| Source | URL | What VECTOR uses it for |
|--------|-----|-------------------------|
| Yahoo Finance v8 | `query1.finance.yahoo.com/v8/finance/chart/{ticker}` | NSE/BSE price + OHLCV |
| Yahoo Finance v1 | `query1.finance.yahoo.com/v1/finance/quoteSummary/{ticker}` | Fundamentals + earnings |
| CoinGecko coins | `api.coingecko.com/api/v3/coins/{id}` | Single coin detail + 24h change |
| CoinGecko markets | `api.coingecko.com/api/v3/coins/markets` | Top-N coins by market cap |

**Tickers convention:** NSE stocks → append `.NS` (e.g., `RELIANCE.NS`); BSE → `.BO`

---

## News / Research Sources (`agents/districts/research/news_aggregator.py`)

| Source | URL | Notes |
|--------|-----|-------|
| HackerNews RSS | `news.ycombinator.com/rss` | Top 30 stories |
| DEV.to feed | `dev.to/feed` | Developer articles |
| ArXiv cs.AI | `export.arxiv.org/rss/cs.AI` | Daily AI papers |
| Reddit r/programming | `reddit.com/r/programming.json` | Public JSON, no auth |
| Reddit r/MachineLearning | `reddit.com/r/MachineLearning.json` | Public JSON, no auth |
| GitHub trending (unofficial) | `github-trending-api.wakatime.com/...` | Or scrape via Search API |

---

## Communications District (`agents/districts/communications/hermes_adapter.py`)

Routed through VectorCode (fully integrated).

| Platform | Notes |
|----------|-------|
| Telegram | Bot token via `.env` → `VECTORCODE_TELEGRAM_TOKEN` |
| Discord | Bot token via `.env` → `VECTORCODE_DISCORD_TOKEN` |
| Slack | App token via `.env` → `VECTORCODE_SLACK_TOKEN` |
| WhatsApp | Twilio sandbox (key-optional free tier) |
| Signal | signal-cli bridge (local) |
| Email | SMTP / Gmail (Google API — OAuth2) |
| Webhook | Any URL — no auth required |

---

## Content District (`agents/districts/content/comfyui_adapter.py`)

| Service | URL | Notes |
|---------|-----|-------|
| ComfyUI local | `http://127.0.0.1:8188` | Stable Diffusion — runs on RTX 5070 Ti |
| ComfyUI queue | `POST /prompt` | Workflow-based generation |
| ComfyUI history | `GET /history/{prompt_id}` | Poll for completion |
| ComfyUI models | `GET /object_info/CheckpointLoaderSimple` | List loaded checkpoints |

---

## Voice District (`core/voice/`)

| Service | Library | Notes |
|---------|---------|-------|
| Whisper STT | `openai-whisper` local | Audio never leaves device (RULE 5) |
| Kokoro TTS | `kokoro` local | Primary voice — bf_emma 0.85x |
| pyttsx3 TTS | `pyttsx3` | Fallback — always available |
| openwakeword | `openwakeword` | Wake word detection |

---

## Sensing / External Data (`core/sensing/`)

| Source | Notes |
|--------|-------|
| OpenWeatherMap | `[key-optional]` free 1000 calls/day via `OPENWEATHER_API_KEY` |
| IP-API (geolocation) | `ip-api.com/json` — no key, 45 req/min |
| WorldTimeAPI | `worldtimeapi.org/api/timezone/Asia/Kolkata` — no key |

---

## GitHub APIs (`agents/districts/coding/`)

All unauthenticated unless noted.

| Endpoint | Rate limit | Used by |
|----------|-----------|---------|
| `api.github.com/search/repositories` | 10 req/min unauth | ResearchHub trending |
| `api.github.com/repos/{owner}/{repo}` | 60 req/h unauth | ArchitectBot repo info |
| `api.github.com/users/{user}/repos` | 60 req/h unauth | GitBot user repos |
| GitHub GraphQL v4 | `[key-optional]` PAT → `GH_TOKEN` | 5000 req/h with token |

Set `GH_TOKEN` in `.env` for 5000 req/h on all GitHub endpoints.

---

## Adding New Sources

1. Add the function to the relevant district file.
2. No authentication = list here as-is.
3. Key-optional = note env var name; load via `CONFIG.get("api_keys", {}).get("key_name")`.
4. Never hardcode keys — always through `CONFIG` / `.env`.
