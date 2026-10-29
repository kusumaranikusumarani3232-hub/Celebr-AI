import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend import main


def run_immediate(coroutine):
    """Run mocked coroutines whose awaits complete without yielding I/O."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("Mocked coroutine unexpectedly performed asynchronous I/O")


@pytest.fixture
def routes(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    # Invoke the FastAPI route handlers directly. The mocked Groq coroutine
    # completes synchronously, so these tests need neither an event loop nor I/O.
    class RouteHandlers:
        @staticmethod
        def invoke(coroutine):
            return run_immediate(coroutine)

        def get(self, path):
            assert path == "/api/health"
            return self.invoke(main.health())

        def post(self, path, json):
            if path == "/api/plan":
                request = main.PlanRequest(**json)
                return self.invoke(main.create_plan(request))
            if path == "/api/rescue":
                request = main.RescueRequest(**json)
                return self.invoke(main.rescue_budget(request))
            raise AssertionError(f"Unexpected API path: {path}")

    return RouteHandlers()


def test_api_route_paths_are_registered():
    registered = {
        (route.path, method)
        for route in main.app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/api/health", "GET") in registered
    assert ("/api/plan", "POST") in registered
    assert ("/api/rescue", "POST") in registered


def planning_payload(**overrides):
    return {
        "event_type": "Birthday",
        "name": "Mira's birthday",
        "date": "2027-05-10",
        "location": "Pune",
        "guests": 30,
        "budget": 25000,
        "theme": "Garden",
        "preferences": "Vegetarian options",
        **overrides,
    }


def groq_plan():
    return {
        "themes": ["Garden brunch", "Golden hour", "Flower market"],
        "decor": ["Seasonal flowers", "Warm lights", "Handwritten cards"],
        "menu": ["Chaat", "Veg pulao", "Fruit tart"],
        "games": ["Memory circle", "Playlist quiz", "Photo hunt"],
        "caption": "A little more lovely together.",
        "tasks": [{"title": f"Prepare step {i}", "days_before": i * 5} for i in range(1, 7)],
    }


def rescue_plan():
    return {
        "costs": {
            "Venue": 6000,
            "Food": 9000,
            "Decorations": 2500,
            "Photography": 2500,
            "Entertainment": 2000,
            "Gifts": 1500,
            "Miscellaneous": 1500,
        },
        "alternatives": ["Use seasonal flowers", "Choose a buffet", "Borrow table décor"],
    }


def test_groq_json_sends_configured_key_model_and_parses_response(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "mocked-secret")
    captured = {}
    payload = {"themes": ["Garden"]}

    class Response:
        status_code = 200
        is_error = False

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"themes": ["Garden"]}'}}]}

        @staticmethod
        def raise_for_status():
            return None

    class MockAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, headers, json):
            captured.update(url=url, headers=headers, body=json)
            return Response()

    monkeypatch.setattr(main.httpx, "AsyncClient", MockAsyncClient)
    assert run_immediate(main.groq_json("test prompt")) == payload
    assert captured["url"] == main.GROQ_URL
    assert captured["headers"]["Authorization"] == "Bearer mocked-secret"
    assert captured["body"]["model"] == main.DEFAULT_MODEL


def test_groq_json_maps_rate_limit_to_clear_api_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "mocked-secret")

    class Response:
        status_code = 429
        is_error = True

        @staticmethod
        def json():
            return {}

        @staticmethod
        def raise_for_status():
            raise AssertionError("Rate-limit responses should be handled before raise_for_status")

    class MockAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(main.httpx, "AsyncClient", MockAsyncClient)
    with pytest.raises(HTTPException) as error:
        run_immediate(main.groq_json("test prompt"))
    assert error.value.status_code == 429
    assert "rate limit" in error.value.detail


def test_health_reports_groq_mode(routes):
    response = routes.get("/api/health")
    assert response["mode"] == "groq"
    assert response["ai_available"] is True


def test_health_reports_demo_when_key_is_absent(routes, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    assert routes.get("/api/health")["mode"] == "demo"


def test_plan_uses_groq_result_and_returns_six_tasks(routes, monkeypatch):
    async def mocked_groq(prompt):
        assert "Mira's birthday" in prompt
        return groq_plan()

    monkeypatch.setattr(main, "groq_json", mocked_groq)
    result = routes.post("/api/plan", json=planning_payload())
    assert result["demo"] is False
    assert result["plan"]["ideas"]["themes"][0] == "Garden brunch"
    assert len(result["plan"]["tasks"]) == 6


@pytest.mark.parametrize("invalid", [{"guests": 0}, {"guests": 50001}, {"budget": 0}, {"budget": -1}])
def test_plan_rejects_invalid_guest_count_and_budget(routes, invalid):
    with pytest.raises(ValidationError):
        routes.post("/api/plan", json=planning_payload(**invalid))


def test_plan_requires_groq_configuration(routes, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(HTTPException) as error:
        routes.post("/api/plan", json=planning_payload())
    assert error.value.status_code == 503
    assert "Groq is not configured" in error.value.detail


def test_plan_surfaces_groq_api_errors_without_demo_fallback(routes, monkeypatch):
    async def failed_groq(_prompt):
        raise HTTPException(status_code=502, detail="Groq returned an unavailable or invalid response.")

    monkeypatch.setattr(main, "groq_json", failed_groq)
    with pytest.raises(HTTPException) as error:
        routes.post("/api/plan", json=planning_payload())
    assert error.value.status_code == 502
    assert "unavailable or invalid" in error.value.detail


def test_rescue_returns_groq_costs_within_budget(routes, monkeypatch):
    async def mocked_groq(prompt):
        assert '"Keep food generous"' in prompt
        return rescue_plan()

    monkeypatch.setattr(main, "groq_json", mocked_groq)
    result = routes.post("/api/rescue", json={
        "event_type": "Birthday", "guests": 30, "budget": 30000,
        "costs": {category: 6000 for category in main.CATEGORIES},
        "priorities": "Keep food generous",
    })
    assert result["demo"] is False
    costs = result["plan"]["costs"]
    assert set(costs) == set(main.CATEGORIES)
    assert sum(costs.values()) <= 27000
    assert len(result["plan"]["rescueAlternatives"]) == 3


def test_rescue_rejects_missing_or_negative_categories(routes):
    base = {"event_type": "Wedding", "guests": 50, "budget": 10000, "costs": {c: 1 for c in main.CATEGORIES}}
    with pytest.raises(HTTPException) as missing:
        routes.post("/api/rescue", json={**base, "costs": {"Venue": 1}})
    with pytest.raises(HTTPException) as negative:
        routes.post("/api/rescue", json={**base, "costs": {**base["costs"], "Food": -1}})
    assert missing.value.status_code == 422
    assert negative.value.status_code == 422


def test_rescue_requires_groq_configuration(routes, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(HTTPException) as error:
        routes.post("/api/rescue", json={
            "event_type": "Birthday", "guests": 10, "budget": 5000,
            "costs": {category: 100 for category in main.CATEGORIES},
        })
    assert error.value.status_code == 503
