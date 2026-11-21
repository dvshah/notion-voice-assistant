import hmac
import os
from typing import Dict, Any, List, Optional
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from notion_service import NotionService
from gemini_agent import GeminiNotionAgent

load_dotenv()

app = FastAPI(title="Gemini + Notion Voice Assistant", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

notion = NotionService()
agent = GeminiNotionAgent(notion=notion)


def get_configured_pin() -> str:
    return os.getenv("APP_ACCESS_PIN", "").strip()


def _extract_pin(request: Request, body_pin: Optional[str] = None) -> str:
    header_pin = request.headers.get("X-Access-Pin", "").strip()
    if header_pin:
        return header_pin
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    query_pin = request.query_params.get("pin", "").strip()
    if query_pin:
        return query_pin
    if body_pin:
        return body_pin.strip()
    return ""


def _check_pin_value(provided: str) -> bool:
    expected = get_configured_pin()
    if not expected:
        return True
    return bool(provided) and hmac.compare_digest(provided, expected)


async def require_pin(request: Request):
    """Protect API endpoints when APP_ACCESS_PIN is configured."""
    if not get_configured_pin():
        return
    provided = _extract_pin(request)
    if not _check_pin_value(provided):
        raise HTTPException(status_code=401, detail="Invalid or missing access PIN")


class PinVerifyRequest(BaseModel):
    pin: str = ""


class VoiceRequest(BaseModel):
    command: Optional[str] = None
    text: Optional[str] = None
    query: Optional[str] = None
    session_id: str = "default"
    pin: Optional[str] = None


class AddItemRequest(BaseModel):
    name: str
    priority: Optional[str] = ""
    due_date: Optional[str] = ""
    category: Optional[str] = ""
    notes: Optional[str] = ""


class UpdateItemRequest(BaseModel):
    new_name: Optional[str] = None
    completed: Optional[bool] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/health")
async def health_check():
    """Unauthenticated health check endpoint for Render / Google Cloud Run."""
    return {"status": "ok"}


@app.get("/api/auth/check")
async def auth_check(request: Request):
    """Tell the frontend whether a PIN is required and if the caller is authorized."""
    pin_required = bool(get_configured_pin())
    authorized = True if not pin_required else _check_pin_value(_extract_pin(request))
    return {"pin_required": pin_required, "authorized": authorized}


@app.post("/api/auth/verify")
async def auth_verify(req: PinVerifyRequest):
    """Verify a PIN submitted from the Mobile PWA lock screen."""
    if not _check_pin_value(req.pin.strip()):
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    return {"authorized": True}


@app.get("/api/status", dependencies=[Depends(require_pin)])
async def get_status():
    dbs = await notion.discover_databases()
    return {
        "status": "online",
        "gemini_enabled": agent.is_gemini_enabled,
        "gemini_model": agent.model if agent.is_gemini_enabled else None,
        "notion_configured": not notion.is_mock,
        "mock_mode": notion.is_mock,
        "pin_protected": bool(get_configured_pin()),
        "databases": [d["name"] for d in dbs],
    }


@app.get("/api/databases", dependencies=[Depends(require_pin)])
async def list_all_databases(include_completed: bool = True, refresh: bool = False):
    """Return all discovered Notion databases and pages along with their items."""
    dbs = await notion.discover_databases(force=refresh)
    payload = []
    for db in dbs:
        resolved_name, items = await notion.get_items(db["name"], include_completed=include_completed)
        active_count = sum(1 for it in items if not it.get("completed"))
        payload.append({
            "id": db["id"],
            "name": resolved_name,
            "active_count": active_count,
            "total_count": len(items),
            "items": items,
        })
    return {
        "databases": payload,
        "mock_mode": notion.is_mock,
        "gemini_enabled": agent.is_gemini_enabled,
    }


@app.get("/api/items", dependencies=[Depends(require_pin)])
async def list_items(database: str = "Shopping List", include_completed: bool = False):
    resolved, items = await notion.get_items(database, include_completed=include_completed)
    return {
        "database": resolved,
        "items": items,
        "count": len(items),
        "mock_mode": notion.is_mock,
    }


@app.post("/api/databases/{db_name}/items", dependencies=[Depends(require_pin)])
async def add_item_direct(db_name: str, req: AddItemRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Item name is required")
    resolved, added = await notion.add_items(db_name, [req.model_dump()])
    return {"database": resolved, "added": added}


@app.patch("/api/databases/{db_name}/items/{item_id}", dependencies=[Depends(require_pin)])
async def update_item_direct(db_name: str, item_id: str, req: UpdateItemRequest):
    resolved, updated = await notion.update_item(
        database_name=db_name,
        item_query=item_id,
        new_name=req.new_name,
        completed=req.completed,
        priority=req.priority,
        due_date=req.due_date,
        notes=req.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"database": resolved, "item": updated}


@app.delete("/api/items/{item_id}", dependencies=[Depends(require_pin)])
async def delete_item(item_id: str):
    success = await notion.delete_item(item_id)
    return {"success": success}


@app.post("/api/chat/reset", dependencies=[Depends(require_pin)])
async def reset_chat(session_id: str = "default"):
    agent.reset_session(session_id)
    return {"status": "reset", "session_id": session_id}


@app.post("/api/voice")
async def handle_voice_command(req: VoiceRequest, request: Request):
    """
    Main conversational voice endpoint powered by Gemini API + Notion Function Calling.
    Accepts APP_ACCESS_PIN via X-Access-Pin header, Bearer token, ?pin= query, or JSON body 'pin'.
    """
    if get_configured_pin():
        provided = _extract_pin(request, body_pin=req.pin)
        if not _check_pin_value(provided):
            raise HTTPException(status_code=401, detail="Invalid or missing access PIN")

    raw_query = (req.command or req.text or req.query or "").strip()
    return await agent.process_command(raw_query, session_id=req.session_id)


# Mount static frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Gemini + Notion Voice Assistant API is running"}
