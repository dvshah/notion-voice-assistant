import asyncio
import os
from fastapi.testclient import TestClient
from main import app, agent, notion

# Ensure integration tests always run safely against mock Notion & local fallback
# so running tests never modifies the user's real live Notion workspace!
notion.is_mock = True
agent.client = None

client = TestClient(app)


def test_health_always_open():
    os.environ["APP_ACCESS_PIN"] = "987654"
    try:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
    finally:
        os.environ.pop("APP_ACCESS_PIN", None)
    print("✓ /api/health unauthenticated check passed")


def test_pin_security_lock():
    os.environ["APP_ACCESS_PIN"] = "482910"
    try:
        # Unauthenticated status -> 401
        assert client.get("/api/status").status_code == 401
        assert client.get("/api/databases").status_code == 401
        assert client.post("/api/voice", json={"command": "What is on my shopping list?"}).status_code == 401

        # Auth check reports pin_required=True, authorized=False
        chk = client.get("/api/auth/check").json()
        assert chk["pin_required"] is True and chk["authorized"] is False

        # Wrong PIN -> 401
        assert client.post("/api/auth/verify", json={"pin": "000000"}).status_code == 401
        assert client.get("/api/status", headers={"X-Access-Pin": "000000"}).status_code == 401

        # Correct PIN via /api/auth/verify -> 200
        assert client.post("/api/auth/verify", json={"pin": "482910"}).status_code == 200

        # Correct PIN via X-Access-Pin header -> 200
        assert client.get("/api/status", headers={"X-Access-Pin": "482910"}).status_code == 200

        # Correct PIN via Bearer header -> 200
        assert client.get("/api/status", headers={"Authorization": "Bearer 482910"}).status_code == 200

        # Correct PIN via MacroDroid JSON body -> 200
        r_voice = client.post(
            "/api/voice",
            json={"command": "What is on my shopping list?", "pin": "482910"},
        )
        assert r_voice.status_code == 200
        assert "Shopping List" in r_voice.json()["speech"]
    finally:
        os.environ.pop("APP_ACCESS_PIN", None)
    print("✓ APP_ACCESS_PIN security tests (401 + Header + Bearer + Body PIN) passed!")


def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "Shopping List" in data["databases"]
    assert "To-Do List" in data["databases"]
    assert "Quick Notes" in data["databases"]
    print("✓ Status & multi-database discovery passed:", data["databases"])


def test_gemini_tool_declarations():
    tools = agent._get_tool_declarations()
    assert len(tools) == 1
    decls = tools[0].function_declarations
    names = [d.name for d in decls]
    for expected in [
        "list_notion_databases",
        "get_items",
        "add_items",
        "update_item",
        "delete_item",
        "get_random_items",
        "search_workspace",
    ]:
        assert expected in names, f"Missing tool declaration: {expected}"
    print(f"✓ All {len(names)} Gemini Function Declarations validated:", names)


def test_gemini_tool_execution_multi_db():
    async def run():
        dbs = await agent._execute_tool("list_notion_databases", {})
        assert len(dbs["databases"]) >= 3

        added = await agent._execute_tool(
            "add_items",
            {
                "database_name": "To-Do List",
                "items": [{"name": "Book dentist", "priority": "High", "due_date": "2026-11-22"}],
            },
        )
        assert added["added_count"] == 1
        assert added["database"] == "To-Do List"

        upd = await agent._execute_tool(
            "update_item",
            {"database_name": "To-Do List", "item_name": "Book dentist", "completed": True},
        )
        assert upd["updated"] is True
        assert upd["item"]["completed"] is True

        sample = await agent._execute_tool(
            "get_random_items", {"database_name": "Shopping List", "count": 2}
        )
        assert len(sample["sample"]) == 2

        hits = await agent._execute_tool("search_workspace", {"query": "pasta"})
        assert hits["count"] >= 1

        deleted = await agent._execute_tool(
            "delete_item", {"database_name": "To-Do List", "item_name": "Book dentist"}
        )
        assert deleted["deleted"] is True

    asyncio.run(run())
    print("✓ Direct Gemini tool execution across Shopping, To-Do, and Notes passed!")


def test_voice_shopping_and_todo_endpoints():
    r1 = client.post("/api/voice", json={"command": "Add milk and 2 dozen eggs to my shopping list"})
    assert r1.status_code == 200
    assert "Added" in r1.json()["speech"]
    print("✓ Shopping add:", r1.json()["speech"])

    r2 = client.post("/api/voice", json={"command": "What is currently on my shopping list?"})
    assert r2.status_code == 200
    assert "Shopping List" in r2.json()["speech"]
    print("✓ Shopping read:", r2.json()["speech"])

    r3 = client.post("/api/voice", json={"command": "Tell me any two items that I have"})
    assert r3.status_code == 200
    assert len(r3.json()["sample"]) == 2
    print("✓ Shopping sample 2:", r3.json()["speech"])

    r4 = client.post("/api/voice", json={"command": "Add a high priority to-do to renew passport"})
    assert r4.status_code == 200
    assert "To-Do List" in r4.json()["speech"]
    print("✓ To-Do add:", r4.json()["speech"])

    r5 = client.post("/api/voice", json={"command": "What is on my to-do list?"})
    assert r5.status_code == 200
    assert "Renew passport" in r5.json()["speech"]
    print("✓ To-Do read:", r5.json()["speech"])

    r6 = client.post("/api/voice", json={"command": "Mark pay rent as done on my to-do list"})
    assert r6.status_code == 200
    assert r6.json()["success"] is True
    print("✓ To-Do complete:", r6.json()["speech"])

    r7 = client.post("/api/voice", json={"command": "Search my notes for pasta"})
    assert r7.status_code == 200
    assert "Pasta recipe ideas" in r7.json()["speech"]
    print("✓ Workspace search:", r7.json()["speech"])


if __name__ == "__main__":
    test_health_always_open()
    test_pin_security_lock()
    test_api_status()
    test_gemini_tool_declarations()
    test_gemini_tool_execution_multi_db()
    test_voice_shopping_and_todo_endpoints()
    print("\nALL GEMINI + NOTION + PIN SECURITY TESTS PASSED! 🎉")
