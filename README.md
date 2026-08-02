# Company Research Assistant

A focused research MVP: enter a company name, bare domain, or HTTP(S) URL; the backend resolves and safely crawls the official site, enriches evidence with Serper, asks the selected OpenRouter model for a validated report, and renders a downloadable PDF. The React/Vite SPA and FastAPI API share one origin in production.

This repository intentionally does **not** implement Discord. Discord is a post-core stretch feature and is not required for the MVP.

## Requirements

- Node.js 22 and npm (for the Vite frontend)
- Python 3.12
- A Serper API key and an OpenRouter API key for research requests
- Docker (optional, for the production-shaped local smoke check)

Provider credentials stay on the server. Do not put them in frontend source, browser storage, or a committed file.

## Local setup

1. Create a local environment file and fill in credentials outside version control:

   ```sh
   cp .env.example .env
   # Edit .env; do not commit it.
   ```

   Required keys are `SERPER_API_KEY`, `OPENROUTER_API_KEY`, and `OPENROUTER_DEFAULT_MODEL`. A compatible model ID must contain `/`, for example `openrouter/auto`.

2. Install backend dependencies in a virtual environment:

   ```sh
   python3.12 -m venv .venv
   . .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r backend/requirements.txt
   ```

3. Install frontend dependencies using the lockfile:

   ```sh
   cd frontend
   npm ci
   cd ..
   ```

4. Run the API and frontend in separate terminals:

   ```sh
   # Terminal 1
   . .venv/bin/activate
   uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 10000

   # Terminal 2
   cd frontend
   npm run dev
   ```

   Open the local Vite address printed by `npm run dev`. The Vite development configuration proxies `/api` to the local FastAPI process. In production, FastAPI serves the compiled SPA itself, so no CORS configuration is needed.

### Local API smoke checks

With FastAPI running, health does not contact either provider and should work even when credentials are missing:

```sh
curl -i http://127.0.0.1:10000/api/v1/health
curl -i http://127.0.0.1:10000/api/v1/config
```

A configured service can be exercised with a direct URL or company name. The response is newline-delimited JSON (NDJSON), so `-N` keeps progress visible:

```sh
curl -N -X POST http://127.0.0.1:10000/api/v1/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"https://example.com","model_id":"openrouter/auto"}'
```

Do not use a private, loopback, link-local, metadata, or otherwise unsafe URL as a test target. The crawler must reject it before making a network request. A missing provider key should produce an actionable configuration error rather than a provider call.

### Production-shaped Docker check

Build and run the same image shape used by Render:

```sh
docker build -t company-research-assistant .
docker run --rm --env-file .env -e PORT=10000 -p 10000:10000 company-research-assistant
curl -i http://127.0.0.1:10000/api/v1/health
```

The image builds the frontend with Node 22 Alpine, installs pinned Python dependencies and DejaVu fonts in Python 3.12 slim, copies `frontend/dist` into `backend/app/static`, and runs one Uvicorn worker as a non-root user. It binds `0.0.0.0` on `PORT` (default `10000`).

## Focused checks

Run the deterministic backend contract/crawler/provider/PDF tests and the frontend production build:

```sh
.venv/bin/python -m pytest -q
cd frontend && npm run build
```

The tests use mocked HTTP; no provider credentials or external research calls are required.

## Environment variables

`.env.example` lists every supported key with no secret values. The settings are:

| Key | Required | Purpose / default |
| --- | --- | --- |
| `SERPER_API_KEY` | Yes for research | Server-side Serper credential. |
| `OPENROUTER_API_KEY` | Yes for research | Server-side OpenRouter credential. |
| `OPENROUTER_DEFAULT_MODEL` | Yes for research | Exact default OpenRouter model ID; the submitted ID is not silently replaced. |
| `OPENROUTER_MODEL_SUGGESTIONS` | No | Comma-separated model IDs. Default: `openrouter/auto,openrouter/free,~openai/gpt-latest`. |
| `OPENROUTER_APP_URL` | No | Optional app URL sent as provider metadata; there is no repository-defined public URL. |
| `CRAWLER_USER_AGENT` | No | Crawler user agent. Default: `CompanyResearchAssistant/1.0 (+research crawler)`. |
| `DISCORD_ENABLED` | No | Defaults to `false`; Discord is not part of this core MVP. |
| `PORT` | No | Listening port. Defaults to `10000`; Render supplies its own port when deployed. |

The browser receives only readiness and model suggestions. It never receives provider keys.

## API

All JSON fields use `snake_case`.

### `GET /api/v1/health`

Returns `200` and `{"status":"ok"}` without contacting Serper or OpenRouter. Render uses this path for its health check. Provider configuration does not make health fail.

### `GET /api/v1/config`

Returns browser-safe configuration:

```json
{
  "ready": true,
  "default_model": "openrouter/auto",
  "model_suggestions": ["openrouter/auto", "openrouter/free", "~openai/gpt-latest"],
  "discord_enabled": false
}
```

`ready` is false if either required provider credential is absent. No secret is returned.

### `POST /api/v1/research`

Request:

```json
{"query":"Stripe","model_id":"openrouter/auto"}
```

`query` is trimmed and accepts a company name (2–120 characters), a URL (up to 2,048 characters), or a valid bare domain. `model_id` is trimmed, must be 3–160 characters, must contain `/`, and may not contain whitespace or control characters. The exact selected model ID is sent to OpenRouter.

A valid request returns `200 application/x-ndjson` with `Cache-Control: no-store`. Every line is one complete JSON event. Typical progress stages are `resolving` (10%), `crawling` (30%), `searching` (55%), `analyzing` (75%), and `finalizing` (95%), followed by a `result` event. A `heartbeat` event is emitted every ten seconds while external work is pending. A terminal `error` event has this shape:

```json
{"type":"error","error":{"code":"OPENROUTER_TIMEOUT","message":"The selected model did not respond in time.","retryable":true}}
```

The complete pipeline is bounded by 75 seconds. Validation/configuration errors discovered before streaming use an HTTP error status with the same inner error shape. A disconnected browser cancels its pipeline.

### Research report limits and fields

The result contains `company`, `summary`, `products_services`, `pain_points`, `competitors`, `sources`, `warnings`, `generated_at`, and `model_id`. Company information includes name, website, and nullable phone/address/country/industry. Unknown phone and address values remain `null` and are displayed as “Not publicly found.” Pain points are explicitly AI-inferred hypotheses, not asserted company facts.

Validation caps are:

- Summary: 2,500 characters
- Products/services: 12 entries
- Pain points: 6 entries
- Competitors: 5 entries
- Sources: 15 entries
- Every individual text field: an explicit maximum length

A report is not returned when model output remains invalid. Competitors must have a verified public website; unresolved or unsafe candidates are omitted.

### `POST /api/v1/pdf`

Accepts a complete structured report as `{"report":{...}}`. The backend revalidates it, rejects oversized input, and creates an in-memory ReportLab PDF—never arbitrary HTML or a filesystem-backed report. The response is `application/pdf` with a sanitized ASCII filename such as `<company>-research-report.pdf`. The PDF matches the validated report shown in the UI and includes the summary, products/services, AI-inference disclaimer, competitors, sources, and warnings.

## Provider and failure behavior

- Missing `SERPER_API_KEY` or `OPENROUTER_API_KEY`: research returns `503 CONFIG_MISSING`; `/health` remains available.
- A company name that cannot resolve to a credible official site: `404 OFFICIAL_SITE_NOT_FOUND`; submit a URL instead.
- Unsafe URL or unsafe redirect: `403 UNSAFE_URL`, before a network request.
- Optional Serper enrichment failure for a direct URL: continue from crawl evidence and add a warning.
- Insufficient evidence: `422 INSUFFICIENT_EVIDENCE`.
- Invalid/incompatible model ID: clear non-retryable model error; no silent model fallback.
- OpenRouter timeout or 429/5xx: retry once when the deadline allows, then return a retryable error.
- Invalid model JSON after the allowed correction attempt: `MODEL_OUTPUT_INVALID`.
- Overall deadline: `RESEARCH_TIMEOUT`.
- PDF failure: the report remains available so PDF can be retried.

## Exact research and cost limits

The crawler is deliberately bounded for a public Render Free service:

- HTTP(S) only, default ports 80/443, no embedded credentials, and no localhost/private/link-local/multicast/reserved/metadata addresses.
- DNS is checked before every request and redirect; redirects are disabled in HTTPX and followed manually up to 3 times.
- `robots.txt` is checked conservatively.
- Homepage plus at most 5 same-host depth-one pages; up to 3 concurrent page requests.
- Six-second page timeout and 15-second aggregate crawl budget.
- HTML content types only; response body limit 1 MB, including responses without `Content-Length`.
- At most 5,000 meaningful characters per page and 25,000 characters overall.
- Tracking parameters, fragments, duplicate URLs/text, assets, and irrelevant account/legal/blog paths are excluded.
- At most six Serper calls for name input and five for direct URL input; enrichment retains the knowledge graph and up to eight organic entries per search.
- OpenRouter uses low temperature and at most 2,000 output tokens, with at most one corrective call if time permits.
- Research has a 75-second overall deadline, a global concurrency limit of two jobs per instance, and a lightweight per-IP limit. Busy requests return `429 SERVER_BUSY` rather than queueing.

These limits reduce SSRF and quota risk; they do not make DNS rebinding impossible. A hardened future deployment would put crawling behind an egress proxy or network policy.

## Security boundaries

- Provider credentials are server environment variables only and are never included in browser responses, prompts shown to users, logs, or PDFs.
- Search snippets and crawled text are untrusted evidence. They are delimited for the model and are rendered as text, never as HTML or executable JavaScript.
- The API validates model output and report input with Pydantic. The PDF route accepts structured report data only.
- Production uses same-origin routes and restrictive security headers; production CORS is not enabled.
- There is no authentication, authorization, database, report history, persistent report file, RAG, queue, WebSocket, Playwright/Selenium, or arbitrary HTML rendering in this MVP.
- Render Free storage is ephemeral; all research and PDF work is in memory.

## Render deployment

`render.yaml` defines one free Docker web service and uses `/api/v1/health` for health checks. Set the three required provider/model environment variables in Render; optional settings may be left out to use defaults. Never paste credentials into source control or a Docker image layer.

Render Free services spin down after about 15 minutes without inbound traffic and may take about a minute to wake. The first request after idle can therefore be slow; the UI surfaces a waking-service state rather than treating that delay as a generic research failure. Retry after the service is warm. No public URL is assumed or documented here—the deployment URL is supplied by the Render service after deployment.

## Scope

The core MVP is one self-contained research turn with progress, a validated report, and PDF download. Discord integration is explicitly deferred and must not block core research, PDF generation, or deployment.
