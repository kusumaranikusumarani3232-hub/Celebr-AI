"""Lightweight optional Groq AI endpoint. Demo mode works without credentials."""
import asyncio
import json
import logging
import math
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="CelebrAI optional AI service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["POST", "GET"], allow_headers=["*"])
logger = logging.getLogger("celebrai.groq")

# Read the repository-root .env explicitly; Uvicorn does not load it automatically.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
CATEGORIES = ("Venue", "Food", "Decorations", "Photography", "Entertainment", "Gifts", "Miscellaneous")


class PlanRequest(BaseModel):
    event_type: str = Field(max_length=50)
    name: str = Field(default="", max_length=120)
    date: str
    location: str = Field(default="", max_length=160)
    guests: int = Field(ge=1, le=50000)
    budget: float = Field(gt=0)
    theme: str = Field(default="", max_length=180)
    preferences: str = Field(default="", max_length=500)


class RescueRequest(BaseModel):
    event_type: str = Field(max_length=50)
    guests: int = Field(ge=1, le=50000)
    budget: float = Field(gt=0)
    costs: dict[str, float]
    priorities: str = Field(default="", max_length=500)


async def groq_json(prompt: str) -> dict:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Groq is not configured.")
    model = re.sub(r"[^a-zA-Z0-9._/-]", "", os.getenv("GROQ_MODEL", DEFAULT_MODEL))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0)) as client:
            response = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are CelebrAI, a thoughtful, culturally considerate celebration planner. Follow the user's constraints. Return only valid JSON matching the requested shape."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.65,
                    "max_completion_tokens": 1400,
                    "response_format": {"type": "json_object"},
                },
            )
        if response.status_code == 429:
            logger.warning("Groq rate limit reached for model %s", model)
            raise HTTPException(status_code=429, detail="Groq rate limit reached; please try again shortly.")
        if response.status_code in (400, 401, 403, 404):
            logger.error("Groq rejected request for model %s with HTTP %s", model, response.status_code)
            raise HTTPException(status_code=502, detail="The configured Groq model or API key is unavailable. Check the server configuration.")
        if response.is_error:
            logger.error("Groq request failed for model %s with HTTP %s", model, response.status_code)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return data
    except HTTPException:
        raise
    except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
        logger.warning("Groq request timed out (%s)", type(exc).__name__)
        raise HTTPException(status_code=504, detail="Groq took too long to respond. Please try again.") from exc
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        logger.error("Groq response could not be processed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Groq returned an unavailable or invalid response.") from exc


@app.get("/api/health")
async def health():
    configured = bool(os.getenv("GROQ_API_KEY", "").strip())
    model = re.sub(r"[^a-zA-Z0-9._/-]", "", os.getenv("GROQ_MODEL", DEFAULT_MODEL))
    return {
        "ok": True,
        "mode": "groq" if configured else "demo",
        "provider": "Groq" if configured else "Demo",
        "model": model if configured else None,
        "ai_available": configured,
    }


@app.post("/api/plan")
async def create_plan(request: PlanRequest):
    if not os.getenv("GROQ_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="Groq is not configured. Check the backend .env file and restart the server.")
    prompt = (
        "Return ONLY valid JSON with exactly these keys: themes (array of 3 short strings), "
        "decor (array of 3 practical strings), menu (array of 3 affordable menu suggestions), "
        "games (array of 3 accessible activity ideas), caption (string). All suggestions must respect "
        "the given INR total budget and stated priorities. Never invent vendor names, availability, or contact details. "
        "Also return tasks (array of exactly 6 objects with title and days_before, an integer from 0 to 90). "
        "Make checklist tasks practical for this event; days_before is the number of days before the event date. "
        "Be warm, culturally thoughtful, specific, and practical. Event brief: "
        + json.dumps(request.model_dump(), ensure_ascii=False)
    )
    data = await groq_json(prompt)
    if not all(isinstance(data.get(key), list) and len(data[key]) == 3 and all(isinstance(x, str) for x in data[key]) for key in ("themes", "decor", "menu", "games")) or not isinstance(data.get("caption"), str):
        logger.error("Groq returned an invalid planning response schema")
        raise HTTPException(status_code=502, detail="Groq returned an invalid planning response.")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 6 or not all(
        isinstance(task, dict) and isinstance(task.get("title"), str) and task["title"].strip()
        and isinstance(task.get("days_before"), int) and not isinstance(task["days_before"], bool)
        and 0 <= task["days_before"] <= 90
        for task in tasks
    ):
        logger.error("Groq returned an invalid event checklist schema")
        raise HTTPException(status_code=502, detail="Groq returned an invalid event checklist.")
    ideas = {key: data[key] for key in ("themes", "decor", "menu", "games", "caption")}
    return {"demo": False, "plan": {"ideas": ideas, "tasks": tasks}}


@app.post("/api/rescue")
async def rescue_budget(request: RescueRequest):
    if not os.getenv("GROQ_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="Groq is not configured. Check the backend .env file and restart the server.")
    if set(request.costs) != set(CATEGORIES) or any(not math.isfinite(value) or value < 0 for value in request.costs.values()):
        raise HTTPException(status_code=422, detail="The budget categories are invalid.")
    original_total = sum(request.costs.values())
    target = min(request.budget, original_total) * 0.9
    prompt = (
        "Return JSON with exactly these keys: costs (object with numeric amounts for every category below), "
        "alternatives (array of exactly 3 short, actionable savings ideas). Revise this event budget to a total "
        "no greater than the target, reducing less important expenses first and protecting the user's stated priorities. "
        "Do not invent vendors. Keep every amount nonnegative. Use INR. Categories: "
        + json.dumps({"categories": CATEGORIES, "target_total": round(target, 2), "current_budget": request.budget,
                      "current_costs": request.costs, "event_type": request.event_type,
                      "guests": request.guests, "priorities": request.priorities}, ensure_ascii=False)
    )
    data = await groq_json(prompt)
    costs = data.get("costs")
    alternatives = data.get("alternatives")
    if not isinstance(costs, dict) or set(costs) != set(CATEGORIES) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in costs.values()):
        logger.error("Groq returned invalid budget amounts")
        raise HTTPException(status_code=502, detail="Groq returned invalid budget amounts.")
    if not isinstance(alternatives, list) or len(alternatives) != 3 or not all(isinstance(v, str) for v in alternatives):
        logger.error("Groq returned invalid budget rescue suggestions")
        raise HTTPException(status_code=502, detail="Groq returned invalid savings suggestions.")
    total = sum(costs.values())
    if total <= 0:
        logger.error("Groq returned an empty revised budget")
        raise HTTPException(status_code=502, detail="Groq returned an empty revised budget.")
    # Enforce the budget server-side even if the model's arithmetic is slightly off.
    if total > target:
        factor = target / total
        costs = {key: round(value * factor, 2) for key, value in costs.items()}
        costs[CATEGORIES[0]] = round(costs[CATEGORIES[0]] + target - sum(costs.values()), 2)
    return {"demo": False, "plan": {"costs": costs, "rescueAlternatives": alternatives}}
