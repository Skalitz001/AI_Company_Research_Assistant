# Company Research Assistant

An AI-assisted company research application for producing evidence-backed company reports from a company name, bare domain, or HTTP(S) URL. The application resolves the official website, gathers bounded public evidence, uses an OpenRouter model to generate a validated report, and provides an in-memory PDF download.

The production stack is a React/Vite single-page application served by FastAPI from one Docker container. The API and frontend use the same origin in production.

## Capabilities

- Accepts company names, bare domains, and HTTP(S) URLs.
- Resolves a credible official website for company-name input through Serper.
- Crawls important static HTML pages with SSRF protections, deduplication, and strict size/time limits.
- Enriches research with public search evidence when Serper is available.
- Generates structured summaries, products or services, inferred pain points, competitors, sources, and warnings.
- Supports selectable free OpenRouter models with bounded fallback behavior.
- Streams truthful progress and heartbeat events over NDJSON.
- Validates model output and report data with Pydantic before rendering.
- Generates a downloadable ReportLab PDF from the validated report.
- Provides a responsive ChatGPT-style research workspace.

## Architecture

```text
React/Vite SPA
        |
        | same-origin HTTP and NDJSON
        v
FastAPI application
  |-- configuration and health routes
  |-- research streaming route
  |-- SSRF-safe static HTML crawler
  |-- Serper adapter
  |-- OpenRouter adapter
  |-- Pydantic report contracts
  `-- ReportLab PDF renderer
        |
        +--> Serper API
        +--> OpenRouter API
```

### Research pipeline

1. Classify the input as a company name or website.
2. For a company name, query Serper and select a credible official site. For a URL, validate and normalize the supplied site.
3. Validate every outbound target and redirect before the request.
4. Crawl the homepage and relevant same-host pages.
5. Enrich the evidence with public search results and competitor discovery where configured.
6. Ask the selected free OpenRouter model for schema-shaped JSON bounded by the collected evidence.
7. Validate, normalize, and deduplicate the report.
8. Stream the result to the browser and make the same validated report available for PDF generation.

### Technology

| Layer | Implementation |
| --- | --- |
| Frontend | React 19, Vite 6, JavaScript |
| Backend | Python 3.12, FastAPI, Uvicorn |
| Validation | Pydantic 2 |
| HTTP client | HTTPX |
| HTML extraction | BeautifulSoup 4, lxml |
| PDF generation | ReportLab |
| Deployment | Multi-stage Docker image, Render Web Service |

## Project layout

```text
backend/
  app/
    main.py                 FastAPI application and SPA serving
    config.py               Environment-backed settings
    schemas.py              Shared API and report contracts
    routers/                Health, configuration, research, and PDF routes
    services/               Crawler, Serper, OpenRouter, research, and PDF logic
    security/               URL inspection and SSRF safeguards
frontend/
  src/
    App.jsx                 Application orchestration
    api.js                  Browser API client
    state.js                UI state model
    components/             Composer, progress, report, and layout components
tests/
  test_api.py               HTTP contract and streaming behavior
  test_research.py          Pipeline, evidence, timeout, and model behavior
  test_crawler.py           Extraction, limits, and page scoring
  test_pdf.py               PDF contract and filename behavior
  test_urls.py              URL and SSRF validation
Dockerfile                  Production image definition
render.yaml                 Render service configuration
```

## Requirements

- Node.js 22 and npm
- Python 3.12
- Serper API credentials for company-name research
- OpenRouter API credentials for AI analysis
- Docker for the production-shaped local check

Provider credentials are server-side configuration. Do not place them in frontend source, browser storage, committed files, or Docker image layers.

## Local development

### 1. Configure the environment

```sh
cp .env.example .env
```

Set the provider credentials in `.env`. The default model is a free OpenRouter model; only free model IDs are enabled by the current deployment configuration.

### 2. Install backend dependencies

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

### 3. Install frontend dependencies

```sh
cd frontend
npm ci
cd ..
```

### 4. Start the development servers

Run FastAPI in one terminal:

```sh
. .venv/bin/activate
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 10000
```

Run Vite in another terminal:

```sh
cd frontend
npm run dev
```

The Vite development server proxies `/api` to FastAPI. In production, FastAPI serves the compiled frontend from the same origin.

## API

All JSON fields use `snake_case`.

### `GET /api/v1/health`

Returns `200` and `{"status":"ok"}` without contacting external providers. Render uses this route for health checks.

### `GET /api/v1/config`

Returns browser-safe runtime configuration. No provider credential is returned.

```json
{
  "ready": true,
  "default_model": "openai/gpt-oss-20b:free",
  "model_suggestions": [
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
    "openrouter/free"
  ],
  "discord_enabled": false
}
```

### `POST /api/v1/research`

Request:

```json
{
  "query": "Stripe",
  "model_id": "openai/gpt-oss-20b:free"
}
```

The query accepts a company name up to 120 characters, a URL up to 2,048 characters, or a valid bare domain. The model ID must be an exact provider ID containing `/` and must be a free model (`openrouter/free` or an ID ending in `:free`).

Successful requests return `200 application/x-ndjson` with `Cache-Control: no-store`. Each line is a complete JSON event:

```json
{"type":"progress","stage":"crawling","percent":30,"message":"Reading important website pages"}
{"type":"heartbeat","message":"Still working…"}
{"type":"result","report":{}}
```

Progress stages are `resolving`, `crawling`, `searching`, `analyzing`, and `finalizing`. The research deadline is 75 seconds. A disconnected browser cancels the active pipeline.

### `POST /api/v1/pdf`

Accepts a complete structured report as `{"report":{...}}`. The backend revalidates the report and returns an in-memory `application/pdf` response with a sanitized filename. Arbitrary HTML is not accepted.

The PDF includes the company information, summary, products or services, AI-inference disclaimer, competitors, sources, and warnings displayed in the report view.

## Environment variables

`.env.example` lists every supported variable without secret values.

| Variable | Required | Description |
| --- | --- | --- |
| `SERPER_API_KEY` | Company names | Server-side Serper credential. Direct URL research can proceed without Serper. |
| `OPENROUTER_API_KEY` | Research | Server-side OpenRouter credential. |
| `OPENROUTER_DEFAULT_MODEL` | No | Free model ID used by default. Defaults to `openai/gpt-oss-20b:free`. |
| `OPENROUTER_MODEL_SUGGESTIONS` | No | Comma-separated free model IDs. |
| `OPENROUTER_APP_URL` | No | Optional application URL sent as OpenRouter metadata. |
| `CRAWLER_USER_AGENT` | No | Crawler user agent. |
| `DISCORD_ENABLED` | No | Reserved configuration flag; Discord delivery is not enabled in this release. |
| `PORT` | No | Listening port. Defaults to `10000`; Render supplies its own port. |

## Security and reliability

- Only HTTP and HTTPS targets on default ports are accepted.
- Embedded URL credentials, localhost, private/link-local, multicast, reserved, and cloud metadata addresses are rejected.
- DNS is checked before each request and redirect; redirects are followed manually up to three times.
- The crawler checks `robots.txt` conservatively and accepts HTML responses only.
- Crawling is limited to six pages, six-second page timeouts, a 15-second aggregate budget, 1 MB response bodies, and 25,000 total extracted characters.
- Search calls, concurrent jobs, and per-IP activity are bounded to control quota and resource usage.
- Search snippets and crawled content are treated as untrusted evidence and are never rendered as HTML.
- Model output is validated before it becomes a report.
- Provider secrets are never returned to the browser, included in prompts shown to users, logged, or embedded in PDFs.
- Research and PDF generation are in memory; no database, report history, or persistent report files are used.

## Verification

Run the deterministic backend suite:

```sh
.venv/bin/python -m pytest -q
```

Build the frontend:

```sh
cd frontend
npm run build
```

The tests use mocked HTTP responses and do not require provider credentials or external research calls.

## Production-shaped Docker check

Build the same multi-stage image used for deployment:

```sh
docker build -t company-research-assistant .
```

Run it with local environment variables:

```sh
docker run --rm \
  --env-file .env \
  -e PORT=10000 \
  -p 10000:10000 \
  company-research-assistant
```

Verify the health endpoint:

```sh
curl -i http://127.0.0.1:10000/api/v1/health
```

The runtime image uses Python 3.12, DejaVu fonts for PDF rendering, a non-root application user, and one Uvicorn worker. The frontend is compiled with Node 22 Alpine and copied into FastAPI's static directory.

## Render deployment

`render.yaml` defines a single free Docker web service with `/api/v1/health` as its health check.

Configure these values in the Render environment settings:

- `SERPER_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENROUTER_DEFAULT_MODEL`

Optional variables can remain unset to use application defaults. Never commit provider credentials or place them in a Docker build argument.

Render Free services sleep after periods of inactivity and may take approximately one minute to wake. The first request after an idle period can therefore be slower than normal.

## Current scope

The current release is intentionally a focused, single-turn research workflow. It does not include authentication, authorization, persistent history, a database, a queue, WebSockets, browser automation for JavaScript-only sites, arbitrary HTML rendering, or Discord delivery. Static HTML plus public search evidence is the supported research input.
