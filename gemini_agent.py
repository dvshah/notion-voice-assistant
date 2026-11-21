import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from google import genai
from google.genai import types

from notion_service import NotionService
from nlp_parser import parse_voice_command

logger = logging.getLogger("gemini_agent")


def format_natural_list(items: List[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def clean_for_tts(text: str) -> str:
    """Strip markdown symbols so Android / browser TTS sounds completely natural."""
    cleaned = re.sub(r"[*_`#]+", "", text)
    cleaned = re.sub(r"\n\s*[-•]\s*", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class GeminiNotionAgent:
    """
    Voice-first AI agent powered by the Google Gemini API with native Function Calling
    directly against the user's Notion workspace (Shopping List, To-Do List, Quick Notes,
    and any other shared Notion databases).
    """

    def __init__(self, notion: NotionService, api_key: Optional[str] = None, model: Optional[str] = None):
        self.notion = notion
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = (model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")).strip()
        self.fallback_models = [
            m for m in [
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite",
                "gemini-3.8-flash",
                "gemini-3.7-flash",
            ]
            if m != self.model
        ]
        self.client: Optional[genai.Client] = genai.Client(api_key=self.api_key) if self.api_key else None

        # Short-term conversation history per session_id (list of types.Content)
        self._sessions: Dict[str, List[types.Content]] = {}
        self.max_history_turns = 12

    @property
    def is_gemini_enabled(self) -> bool:
        return self.client is not None

    def reset_session(self, session_id: str = "default"):
        self._sessions.pop(session_id, None)

    def _build_system_instruction(self, db_names: List[str]) -> str:
        today = datetime.now().strftime("%Y-%m-%d (%A)")
        if db_names:
            dbs_str = ", ".join(db_names)
        else:
            dbs_str = "NONE YET (tell the user no Notion pages or databases are shared with their integration yet, and remind them to open their Shopping List or To-Do List in Notion, tap the three dots menu, click Connections, and connect their integration)"
        return (
            f"You are a fast, friendly, voice-controlled Notion assistant on the user's Android phone. "
            f"Today's date is {today}.\n\n"
            f"Connected Notion databases: {dbs_str}.\n\n"
            "Rules:\n"
            "1. ALWAYS use the provided Notion tools to read, add, update, check, sample, search, or delete items. "
            "Never make up items or claim an action succeeded unless the tool returned success.\n"
            "2. You can call multiple tools in one turn (for example, check the Shopping List before adding missing "
            "ingredients, or add a shopping item AND a to-do task in the same request).\n"
            "3. When the user mentions relative dates like 'tomorrow' or 'Friday', convert them into YYYY-MM-DD "
            "format based on today's date.\n"
            "4. When the user asks for 'any two items' or 'some items', use get_random_items.\n"
            "5. Output ONLY natural, concise, spoken English optimized for Text-to-Speech. "
            "Do NOT use markdown, bullet points, asterisks, emojis, or technical IDs in your reply."
        )

    def _get_tool_declarations(self) -> List[types.Tool]:
        declarations = [
            types.FunctionDeclaration(
                name="list_notion_databases",
                description="List all Notion databases available in the user's workspace (e.g., Shopping List, To-Do List, Quick Notes, or custom databases).",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="get_items",
                description="Read items from a Notion database such as 'Shopping List', 'To-Do List', or 'Quick Notes'.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "database_name": types.Schema(
                            type=types.Type.STRING,
                            description="Name of the Notion database (e.g., 'Shopping List', 'To-Do List', 'Quick Notes').",
                        ),
                        "include_completed": types.Schema(
                            type=types.Type.BOOLEAN,
                            description="Whether to include already completed/bought items. Default false.",
                        ),
                    },
                    required=["database_name"],
                ),
            ),
            types.FunctionDeclaration(
                name="add_items",
                description="Add one or more new items, tasks, or notes to a Notion database.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "database_name": types.Schema(
                            type=types.Type.STRING,
                            description="Target Notion database name (e.g., 'Shopping List', 'To-Do List', 'Quick Notes').",
                        ),
                        "items": types.Schema(
                            type=types.Type.ARRAY,
                            description="List of items to add.",
                            items=types.Schema(
                                type=types.Type.OBJECT,
                                properties={
                                    "name": types.Schema(type=types.Type.STRING, description="Item or task title."),
                                    "priority": types.Schema(type=types.Type.STRING, description="Optional priority: High, Medium, or Low."),
                                    "due_date": types.Schema(type=types.Type.STRING, description="Optional due date in YYYY-MM-DD format."),
                                    "category": types.Schema(type=types.Type.STRING, description="Optional category or grocery aisle."),
                                    "notes": types.Schema(type=types.Type.STRING, description="Optional extra details or note body."),
                                },
                                required=["name"],
                            ),
                        ),
                    },
                    required=["database_name", "items"],
                ),
            ),
            types.FunctionDeclaration(
                name="update_item",
                description="Update an existing item in a Notion database: mark it completed/uncompleted, rename it, or change its priority, due date, or notes.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "database_name": types.Schema(type=types.Type.STRING, description="Notion database name."),
                        "item_name": types.Schema(type=types.Type.STRING, description="Current name (or partial name) of the item to update."),
                        "new_name": types.Schema(type=types.Type.STRING, description="Optional new title for the item."),
                        "completed": types.Schema(type=types.Type.BOOLEAN, description="Set true to mark as done/bought, false to reopen."),
                        "priority": types.Schema(type=types.Type.STRING, description="Optional new priority (High, Medium, Low)."),
                        "due_date": types.Schema(type=types.Type.STRING, description="Optional new due date in YYYY-MM-DD format."),
                        "notes": types.Schema(type=types.Type.STRING, description="Optional updated notes."),
                    },
                    required=["database_name", "item_name"],
                ),
            ),
            types.FunctionDeclaration(
                name="delete_item",
                description="Permanently archive/remove an item from a Notion database.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "database_name": types.Schema(type=types.Type.STRING, description="Notion database name."),
                        "item_name": types.Schema(type=types.Type.STRING, description="Name (or partial name) of the item to delete."),
                    },
                    required=["database_name", "item_name"],
                ),
            ),
            types.FunctionDeclaration(
                name="get_random_items",
                description="Pick N random active items from a Notion database (e.g., when user asks 'tell me any two items I have').",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "database_name": types.Schema(type=types.Type.STRING, description="Notion database name."),
                        "count": types.Schema(type=types.Type.INTEGER, description="How many random items to return. Default 2."),
                    },
                    required=["database_name"],
                ),
            ),
            types.FunctionDeclaration(
                name="search_workspace",
                description="Search across all Notion databases and pages for a keyword or topic.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(type=types.Type.STRING, description="Search keyword or phrase."),
                    },
                    required=["query"],
                ),
            ),
        ]
        return [types.Tool(function_declarations=declarations)]

    async def _execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a Gemini function call to NotionService."""
        try:
            if name == "list_notion_databases":
                dbs = await self.notion.discover_databases()
                return {"databases": dbs}

            elif name == "get_items":
                db_name = args.get("database_name", "Shopping List")
                include_completed = bool(args.get("include_completed", False))
                resolved, items = await self.notion.get_items(db_name, include_completed=include_completed)
                return {"database": resolved, "count": len(items), "items": items}

            elif name == "add_items":
                db_name = args.get("database_name", "Shopping List")
                raw_items = args.get("items", [])
                resolved, added = await self.notion.add_items(db_name, raw_items)
                return {"database": resolved, "added_count": len(added), "added_items": added}

            elif name == "update_item":
                db_name = args.get("database_name", "Shopping List")
                item_name = args.get("item_name", "")
                resolved, updated = await self.notion.update_item(
                    database_name=db_name,
                    item_query=item_name,
                    new_name=args.get("new_name") or None,
                    completed=args.get("completed") if "completed" in args else None,
                    priority=args.get("priority") or None,
                    due_date=args.get("due_date") or None,
                    notes=args.get("notes") or None,
                )
                if updated:
                    return {"database": resolved, "updated": True, "item": updated}
                return {"database": resolved, "updated": False, "error": f"Could not find '{item_name}' in {resolved}."}

            elif name == "delete_item":
                db_name = args.get("database_name", "Shopping List")
                item_name = args.get("item_name", "")
                resolved, removed = await self.notion.delete_item_by_name(db_name, item_name)
                if removed:
                    return {"database": resolved, "deleted": True, "removed_name": removed}
                return {"database": resolved, "deleted": False, "error": f"Could not find '{item_name}' in {resolved}."}

            elif name == "get_random_items":
                db_name = args.get("database_name", "Shopping List")
                count = int(args.get("count", 2))
                resolved, sample = await self.notion.sample_items(db_name, count=count)
                return {"database": resolved, "count": len(sample), "sample": sample}

            elif name == "search_workspace":
                query = args.get("query", "")
                hits = await self.notion.search_workspace(query)
                return {"query": query, "count": len(hits), "results": hits}

            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.exception(f"Tool execution error ({name}): {e}")
            return {"error": str(e)}

    async def process_command(self, user_text: str, session_id: str = "default") -> Dict[str, Any]:
        """
        Process a voice command using Gemini Function Calling (if GEMINI_API_KEY is configured),
        or fall back to the local multi-list NLP parser.
        """
        text = user_text.strip()
        if not text:
            return {
                "speech": "I didn't hear anything. Try asking about your shopping list, to-do list, or notes.",
                "actions_taken": [],
                "engine": "gemini" if self.is_gemini_enabled else "local_fallback",
                "mock_notion": self.notion.is_mock,
                "success": False,
            }

        if not self.is_gemini_enabled:
            return await self._process_local_fallback(text)

        return await self._process_with_gemini(text, session_id)

    async def _generate_with_fallback(self, history: List[types.Content], config: types.GenerateContentConfig):
        assert self.client is not None
        models_to_try = [self.model] + self.fallback_models
        last_err: Optional[Exception] = None
        for m in models_to_try:
            try:
                resp = await self.client.aio.models.generate_content(
                    model=m,
                    contents=history,
                    config=config,
                )
                return m, resp
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "404" in err_str or "UNAVAILABLE" in err_str or "NOT_FOUND" in err_str:
                    logger.warning(f"Model {m} unavailable ({err_str[:120]}), trying next fallback...")
                    last_err = e
                    continue
                raise
        if last_err:
            raise last_err
        raise RuntimeError("No Gemini models configured")

    async def _process_with_gemini(self, text: str, session_id: str) -> Dict[str, Any]:
        assert self.client is not None
        dbs = await self.notion.discover_databases()
        db_names = [d["name"] for d in dbs]

        history = list(self._sessions.get(session_id, []))
        history.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))

        config = types.GenerateContentConfig(
            system_instruction=self._build_system_instruction(db_names),
            tools=self._get_tool_declarations(),
            temperature=0.3,
        )

        actions_taken: List[Dict[str, Any]] = []
        max_tool_rounds = 6
        active_model = self.model

        try:
            final_text = ""
            for _ in range(max_tool_rounds):
                active_model, response = await self._generate_with_fallback(history, config)

                candidate = response.candidates[0] if response.candidates else None
                if not candidate or not candidate.content:
                    break

                # Append model turn to history
                history.append(candidate.content)

                # Check for function calls
                fn_calls = response.function_calls
                if fn_calls:
                    fn_response_parts = []
                    for fc in fn_calls:
                        fn_name = fc.name
                        fn_args = dict(fc.args) if fc.args else {}
                        result = await self._execute_tool(fn_name, fn_args)
                        actions_taken.append({"tool": fn_name, "args": fn_args, "result": result})
                        fn_response_parts.append(
                            types.Part.from_function_response(name=fn_name, response=result)
                        )
                    history.append(types.Content(role="user", parts=fn_response_parts))
                else:
                    final_text = response.text or ""
                    break

            # Trim conversation history to keep token usage light
            if len(history) > self.max_history_turns * 2:
                history = history[-(self.max_history_turns * 2):]
            self._sessions[session_id] = history

            speech = clean_for_tts(final_text) if final_text else "Done! I updated your Notion workspace."
            return {
                "speech": speech,
                "actions_taken": actions_taken,
                "engine": "gemini",
                "model": active_model,
                "mock_notion": self.notion.is_mock,
                "success": True,
            }

        except Exception as e:
            logger.exception(f"Gemini API error: {e}")
            # Gracefully fall back if API call fails (e.g. invalid key or quota)
            fallback = await self._process_local_fallback(text)
            fallback["gemini_error"] = str(e)
            return fallback

    async def _process_local_fallback(self, text: str) -> Dict[str, Any]:
        """
        Multi-list local rule-based fallback so the assistant works seamlessly
        even before a GEMINI_API_KEY is added.
        """
        parsed = parse_voice_command(text)
        intent = parsed.get("intent")
        target_db = parsed.get("database", "Shopping List")
        actions_taken: List[Dict[str, Any]] = []

        if intent == "add_items":
            items = parsed.get("items", [])
            priority = parsed.get("priority", "")
            item_dicts = [{"name": i, "priority": priority} for i in items]
            resolved, added = await self.notion.add_items(target_db, item_dicts)
            names = [a["name"] for a in added]
            actions_taken.append({"tool": "add_items", "args": {"database_name": resolved, "items": item_dicts}})
            speech = f"Added {format_natural_list(names)} to your {resolved}."
            return {"intent": intent, "database": resolved, "items": names, "speech": speech, "actions_taken": actions_taken, "engine": "local_fallback", "mock_notion": self.notion.is_mock, "success": True}

        elif intent == "read_list":
            resolved, current = await self.notion.get_items(target_db, include_completed=False)
            actions_taken.append({"tool": "get_items", "args": {"database_name": resolved}})
            if not current:
                speech = f"Your {resolved} is currently empty."
            elif len(current) == 1:
                speech = f"You have 1 item on your {resolved}: {current[0]['name']}."
            else:
                names = [it["name"] for it in current]
                speech = f"You have {len(names)} items on your {resolved}: {format_natural_list(names)}."
            return {"intent": intent, "database": resolved, "items": current, "speech": speech, "actions_taken": actions_taken, "engine": "local_fallback", "mock_notion": self.notion.is_mock, "success": True}

        elif intent == "sample_items":
            count = parsed.get("count", 2)
            resolved, sample = await self.notion.sample_items(target_db, count=count)
            actions_taken.append({"tool": "get_random_items", "args": {"database_name": resolved, "count": count}})
            if not sample:
                speech = f"Your {resolved} is currently empty."
            elif len(sample) < count:
                speech = f"You only have {len(sample)} items on your {resolved}: {format_natural_list(sample)}."
            else:
                word = "Two" if count == 2 else ("Three" if count == 3 else str(count))
                speech = f"{word} items currently on your {resolved} are {format_natural_list(sample)}."
            return {"intent": intent, "database": resolved, "sample": sample, "count": count, "speech": speech, "actions_taken": actions_taken, "engine": "local_fallback", "mock_notion": self.notion.is_mock, "success": True}

        elif intent == "check_item":
            item_q = parsed.get("item", "")
            exists, matched = await self.notion.check_item(item_q, database_name=target_db)
            actions_taken.append({"tool": "get_items", "args": {"database_name": target_db, "check": item_q}})
            speech = f"Yes, {matched} is on your {target_db}." if exists else f"No, {item_q} is not on your {target_db}."
            return {"intent": intent, "database": target_db, "item": item_q, "exists": exists, "matched_name": matched, "speech": speech, "actions_taken": actions_taken, "engine": "local_fallback", "mock_notion": self.notion.is_mock, "success": True}

        elif intent == "complete_item":
            item_q = parsed.get("item", "")
            resolved, updated = await self.notion.update_item(target_db, item_q, completed=True)
            actions_taken.append({"tool": "update_item", "args": {"database_name": resolved, "item_name": item_q, "completed": True}})
            if updated:
                speech = f"Marked {updated['name']} as done on your {resolved}."
                ok = True
            else:
                speech = f"I couldn't find {item_q} on your {resolved}."
                ok = False
            return {"intent": intent, "database": resolved, "item": item_q, "speech": speech, "actions_taken": actions_taken, "engine": "local_fallback", "mock_notion": self.notion.is_mock, "success": ok}

        elif intent == "search":
            q = parsed.get("query", "")
            hits = await self.notion.search_workspace(q)
            actions_taken.append({"tool": "search_workspace", "args": {"query": q}})
            if hits:
                names = [f"{h['name']} in {h.get('database', 'Notion')}" for h in hits[:4]]
                speech = f"I found {len(hits)} matches: {format_natural_list(names)}."
            else:
                speech = f"I couldn't find anything matching {q} in your Notion workspace."
            return {"intent": intent, "results": hits, "speech": speech, "actions_taken": actions_taken, "engine": "local_fallback", "mock_notion": self.notion.is_mock, "success": True}

        else:
            speech = (
                "You can ask me to manage your shopping list, to-do list, or notes. "
                "For full natural conversations, add your Gemini API key in the .env file."
            )
            return {"intent": "help", "speech": speech, "actions_taken": [], "engine": "local_fallback", "mock_notion": self.notion.is_mock, "success": True}
