# CelebrAI — Your Personal AI Celebration Planner

A lightweight, responsive React + TypeScript application for turning birthdays, weddings, anniversaries, festivals, and community gatherings into thoughtful, affordable plans. Core features run immediately in a clearly labelled local demo mode, without an API key.

## Get started

Requirements: Node.js 20+ and npm. For the optional AI integration, Python 3.10+.

```bash
npm install
npm run dev
```

Open the local address printed by Vite. Add a name, date, place, guest count, budget, theme, and priorities, then choose **Plan my celebration**. The interactive dashboard contains an INR budget breakdown, budget rescue, editable vendor shortlist, a completion-tracked checklist, celebration ideas, local save and reopen, and print-to-PDF export. Plans are stored in this browser's local storage.

## Optional AI mode

The FastAPI server loads `GROQ_API_KEY` from the repository-root `.env` file (or the process environment). The key is never embedded in frontend assets. The event creation screen reports whether Groq is configured, demo mode is active, or the backend is unavailable.

```bash
# In a separate terminal:
python -m venv .venv
# Activate .venv, then:
pip install -r requirements.txt
```

Add `GROQ_API_KEY` to the repository-root `.env` file (the existing `.env` is loaded automatically) or the backend process environment, then start `uvicorn backend.main:app --reload --port 8000`. Vite proxies `/api` requests to the server during local development. The Vercel production build reads `VITE_API_URL` from `.env.production` and sends the same `/api/health`, `/api/plan`, and `/api/rescue` routes to the Render service. The default `openai/gpt-oss-120b` model is configurable using `GROQ_MODEL`. Both event planning and Budget Rescue Mode send requests to Groq. If no key is configured, the status endpoint reports demo mode and the app deliberately uses its local planner. When Groq is configured but unavailable, slow, rate-limited, misconfigured, or returns invalid data, the app displays a clear error and does not silently substitute demo content. FastAPI permits `https://celebr-ai-kappa.vercel.app`, `https://celebr-ai.vercel.app`, and local Vite origins by default. Set `FRONTEND_ORIGINS` to add extra origins; the required production domains remain allowed. API keys should be kept out of the repository and browser.

## Small, private by default

The repository excludes dependencies, build products, caches, virtual environments, secrets, local databases, and generated files. No event details are uploaded when operating in demo mode. Saved plans live in the user's browser and can be removed from **My plans**. Vendor entries are user supplied; the app does not claim to verify businesses or invent their contact details.

```bash
npm run build
```

## Automated tests

The frontend behavior tests use Node's built-in test runner and require no API key or extra packages. Backend tests use `pytest` and mock Groq responses, so they do not make network requests or incur API costs.

```bash
npm run test:frontend
python -m pip install -r requirements-dev.txt
npm run test:backend
```

To deploy, host the generated `dist/` static site and run the optional FastAPI service behind the same origin or configure a production API proxy.
