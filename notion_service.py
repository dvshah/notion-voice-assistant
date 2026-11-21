import os
import logging
import random
from typing import Dict, Any, List, Optional, Tuple
import httpx

logger = logging.getLogger("notion_service")


class NotionService:
    """
    Multi-database Notion client with automatic workspace discovery,
    schema detection (Title, Checkbox/Status, Priority/Select, Date, Rich Text),
    and full in-memory Mock Mode for instant testing.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or os.getenv("NOTION_API_KEY", "")).strip()
        self.notion_version = "2022-06-28"
        self.base_url = "https://api.notion.com/v1"

        # Optional explicitly configured database IDs
        self.explicit_dbs: Dict[str, str] = {}
        shopping_id = os.getenv("NOTION_SHOPPING_DB_ID") or os.getenv("NOTION_DATABASE_ID", "")
        todo_id = os.getenv("NOTION_TODO_DB_ID", "")
        notes_id = os.getenv("NOTION_NOTES_DB_ID", "")

        if shopping_id.strip():
            self.explicit_dbs["Shopping List"] = self._extract_id(shopping_id)
        if todo_id.strip():
            self.explicit_dbs["To-Do List"] = self._extract_id(todo_id)
        if notes_id.strip():
            self.explicit_dbs["Quick Notes"] = self._extract_id(notes_id)

        self.is_mock = not bool(self.api_key)

        # Discovered database metadata cache: {db_id: {id, name, schema: {...}}}
        self._db_cache: Dict[str, Dict[str, Any]] = {}
        self._discovered = False

        # Rich in-memory mock workspace when NOTION_API_KEY is not set
        self.mock_databases: Dict[str, List[Dict[str, Any]]] = {
            "Shopping List": [
                {"id": "shop-1", "name": "Organic Milk", "completed": False, "category": "Dairy", "priority": "", "due_date": "", "notes": ""},
                {"id": "shop-2", "name": "Free-range Eggs", "completed": False, "category": "Dairy", "priority": "", "due_date": "", "notes": ""},
                {"id": "shop-3", "name": "Sourdough Bread", "completed": False, "category": "Bakery", "priority": "", "due_date": "", "notes": ""},
                {"id": "shop-4", "name": "Apples", "completed": False, "category": "Produce", "priority": "", "due_date": "", "notes": ""},
                {"id": "shop-5", "name": "Oat Milk", "completed": True, "category": "Dairy", "priority": "", "due_date": "", "notes": ""},
            ],
            "To-Do List": [
                {"id": "todo-1", "name": "Pay rent", "completed": False, "priority": "High", "due_date": "2026-11-25", "category": "Finance", "notes": ""},
                {"id": "todo-2", "name": "Call mom", "completed": False, "priority": "Medium", "due_date": "2026-11-22", "category": "Personal", "notes": ""},
                {"id": "todo-3", "name": "Finish quarterly report", "completed": False, "priority": "High", "due_date": "2026-11-24", "category": "Work", "notes": ""},
                {"id": "todo-4", "name": "Water the plants", "completed": True, "priority": "Low", "due_date": "", "category": "Home", "notes": ""},
            ],
            "Quick Notes": [
                {"id": "note-1", "name": "Pasta recipe ideas", "completed": False, "priority": "", "due_date": "", "category": "Cooking", "notes": "Use fresh basil, cherry tomatoes, garlic, and parmesan."},
                {"id": "note-2", "name": "Gift ideas for Alex", "completed": False, "priority": "", "due_date": "", "category": "Personal", "notes": "Mechanical keyboard or pour-over coffee maker."},
            ],
        }

    def _extract_id(self, raw: str) -> str:
        """Extract 32-char hex Notion ID from URL or dashed UUID."""
        if not raw:
            return ""
        cleaned = raw.strip().split("?")[0].split("/")[-1]
        # Handle Notion page slugs like "Shopping-List-a8aec433..."
        if "-" in cleaned:
            tail = cleaned.split("-")[-1]
            if len(tail) == 32:
                return tail
        return cleaned.replace("-", "")

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }

    def _parse_schema(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-detect title, status/checkbox, priority, category, due_date, and notes columns."""
        schema: Dict[str, Any] = {
            "title": "Name",
            "status": None,
            "status_type": None,
            "priority": None,
            "priority_type": None,
            "category": None,
            "category_type": None,
            "due_date": None,
            "notes": None,
            "all_properties": list(properties.keys()),
        }

        for prop_name, prop_data in properties.items():
            p_type = prop_data.get("type")
            lower = prop_name.lower()

            if p_type == "title":
                schema["title"] = prop_name
            elif p_type == "checkbox":
                if not schema["status"] or any(k in lower for k in ["done", "complete", "bought", "check"]):
                    schema["status"] = prop_name
                    schema["status_type"] = "checkbox"
            elif p_type == "status":
                if not schema["status"]:
                    schema["status"] = prop_name
                    schema["status_type"] = "status"
            elif p_type == "date":
                if not schema["due_date"] or any(k in lower for k in ["due", "date", "deadline", "when"]):
                    schema["due_date"] = prop_name
            elif p_type in ("select", "multi_select"):
                if any(k in lower for k in ["priority", "urgency", "importance"]):
                    schema["priority"] = prop_name
                    schema["priority_type"] = p_type
                elif any(k in lower for k in ["category", "tag", "aisle", "type", "group"]):
                    schema["category"] = prop_name
                    schema["category_type"] = p_type
                elif not schema["category"]:
                    schema["category"] = prop_name
                    schema["category_type"] = p_type
            elif p_type == "rich_text":
                if not schema["notes"] or any(k in lower for k in ["note", "desc", "detail", "comment"]):
                    schema["notes"] = prop_name

        return schema

    async def discover_databases(self, force: bool = False) -> List[Dict[str, Any]]:
        """Discover all Notion databases AND standalone checklist pages shared with this integration."""
        if self.is_mock:
            return [
                {
                    "id": f"mock-{name.lower().replace(' ', '-')}",
                    "name": name,
                    "kind": "database",
                    "properties": ["Name", "Done", "Priority", "Due Date", "Category", "Notes"],
                }
                for name in self.mock_databases.keys()
            ]

        if self._discovered and not force and self._db_cache:
            return [
                {"id": db["id"], "name": db["name"], "kind": db.get("kind", "database"), "properties": db["schema"]["all_properties"]}
                for db in self._db_cache.values()
            ]

        if force:
            self._db_cache.clear()

        async with httpx.AsyncClient(timeout=12.0) as client:
            # 1. Auto-discover ALL shared databases and top-level pages via Notion search API
            try:
                res = await client.post(
                    f"{self.base_url}/search",
                    headers=self.headers,
                    json={"page_size": 50},
                )
                if res.status_code == 200:
                    raw_results = res.json().get("results", [])
                    # Track parent pages that merely wrap inline databases so we don't duplicate them
                    db_parent_page_ids = set()
                    for obj in raw_results:
                        if obj.get("object") == "database":
                            parent = obj.get("parent", {})
                            if parent.get("type") == "page_id" and parent.get("page_id"):
                                db_parent_page_ids.add(parent["page_id"].replace("-", ""))

                    for obj in raw_results:
                        otype = obj.get("object")
                        obj_id = obj["id"].replace("-", "")
                        if otype == "database":
                            title_parts = obj.get("title", [])
                            db_name = "".join([t.get("plain_text", "") for t in title_parts]).strip() or "Untitled Database"
                            schema = self._parse_schema(obj.get("properties", {}))
                            self._db_cache[obj_id] = {"id": obj["id"], "name": db_name, "kind": "database", "schema": schema}
                        elif otype == "page":
                            # Skip database row pages and container pages that hold inline databases
                            parent_type = obj.get("parent", {}).get("type")
                            if parent_type == "database_id" or obj_id in db_parent_page_ids:
                                continue
                            page_title = ""
                            for prop in obj.get("properties", {}).values():
                                if prop.get("type") == "title":
                                    page_title = "".join([t.get("plain_text", "") for t in prop.get("title", [])]).strip()
                                    break
                            page_title = page_title or "Untitled Page"
                            self._db_cache[obj_id] = {
                                "id": obj["id"],
                                "name": page_title,
                                "kind": "page",
                                "schema": {"all_properties": ["to_do blocks"]},
                            }
                else:
                    logger.warning(f"Notion search failed: {res.status_code} {res.text}")
            except Exception as e:
                logger.error(f"Error discovering Notion databases/pages: {e}")

            # 2. Ensure any explicitly configured DBs are loaded
            for alias, db_id in self.explicit_dbs.items():
                if db_id and db_id not in self._db_cache:
                    try:
                        res = await client.get(f"{self.base_url}/databases/{db_id}", headers=self.headers)
                        if res.status_code == 200:
                            db = res.json()
                            title_parts = db.get("title", [])
                            db_name = "".join([t.get("plain_text", "") for t in title_parts]).strip() or alias
                            schema = self._parse_schema(db.get("properties", {}))
                            self._db_cache[db_id] = {"id": db["id"], "name": db_name, "kind": "database", "alias": alias, "schema": schema}
                    except Exception as e:
                        logger.error(f"Error loading explicit database {alias}: {e}")

        self._discovered = True
        return [
            {"id": db["id"], "name": db["name"], "kind": db.get("kind", "database"), "properties": db["schema"]["all_properties"]}
            for db in self._db_cache.values()
        ]

    def _match_db_name(self, requested: str, available_names: List[str]) -> Optional[str]:
        """Fuzzy-match a user's database name (e.g., 'groceries' -> 'Shopping List', 'tasks' -> 'To-Do List')."""
        if not available_names:
            return None
        req = requested.strip().lower()

        # Direct exact match
        for name in available_names:
            if name.lower() == req:
                return name

        # Partial substring match
        for name in available_names:
            if req in name.lower() or name.lower() in req:
                return name

        # Common synonym matching
        synonym_groups = [
            ["shopping", "grocery", "groceries", "market", "buy", "store"],
            ["to-do", "todo", "to do", "task", "tasks", "checklist", "chore", "chores"],
            ["note", "notes", "memo", "memos", "idea", "ideas", "journal"],
        ]
        for group in synonym_groups:
            if any(word in req for word in group):
                for name in available_names:
                    if any(word in name.lower() for word in group):
                        return name

        return None

    async def _resolve_live_db(self, database_name: str) -> Optional[Dict[str, Any]]:
        await self.discover_databases()
        if not self._db_cache:
            return None

        # Match by explicit alias first
        req_lower = database_name.strip().lower()
        for db in self._db_cache.values():
            if db.get("alias", "").lower() == req_lower:
                return db

        # Match by ID directly
        clean_req = self._extract_id(database_name)
        if clean_req in self._db_cache:
            return self._db_cache[clean_req]

        # Fuzzy match by name
        names = [db["name"] for db in self._db_cache.values()]
        matched_name = self._match_db_name(database_name, names)
        if matched_name:
            for db in self._db_cache.values():
                if db["name"] == matched_name:
                    return db
        return None

    async def get_items(self, database_name: str = "Shopping List", include_completed: bool = False) -> Tuple[str, List[Dict[str, Any]]]:
        """Fetch items from a named database. Returns (resolved_db_name, items)."""
        if self.is_mock:
            matched = self._match_db_name(database_name, list(self.mock_databases.keys()))
            if not matched:
                # Auto-create custom mock database if requested
                matched = database_name.strip().title()
                self.mock_databases.setdefault(matched, [])
            items = self.mock_databases[matched]
            if include_completed:
                return matched, [dict(it) for it in items]
            return matched, [dict(it) for it in items if not it.get("completed")]

        db = await self._resolve_live_db(database_name)
        if not db:
            return database_name, []

        # Standalone Notion Page (e.g., checklist with to_do or bullet blocks)
        if db.get("kind") == "page":
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.get(
                    f"{self.base_url}/blocks/{db['id']}/children?page_size=100",
                    headers=self.headers,
                )
                if res.status_code != 200:
                    logger.error(f"Notion page blocks read failed ({db['name']}): {res.status_code} {res.text}")
                    return db["name"], []
                items = []
                for blk in res.json().get("results", []):
                    btype = blk.get("type")
                    if btype in ("to_do", "bulleted_list_item", "numbered_list_item", "paragraph"):
                        bdata = blk.get(btype, {})
                        text_val = "".join(t.get("plain_text", "") for t in bdata.get("rich_text", [])).strip()
                        if not text_val:
                            continue
                        completed = bool(bdata.get("checked", False)) if btype == "to_do" else False
                        if not include_completed and completed:
                            continue
                        items.append({
                            "id": blk["id"],
                            "name": text_val,
                            "completed": completed,
                            "priority": "",
                            "category": "",
                            "due_date": "",
                            "notes": "",
                            "block_type": btype,
                        })
                return db["name"], items

        schema = db["schema"]
        async with httpx.AsyncClient(timeout=12.0) as client:
            url = f"{self.base_url}/databases/{db['id']}/query"
            payload: Dict[str, Any] = {"page_size": 100}

            if not include_completed and schema["status"]:
                if schema["status_type"] == "checkbox":
                    payload["filter"] = {"property": schema["status"], "checkbox": {"equals": False}}
                elif schema["status_type"] == "status":
                    payload["filter"] = {"property": schema["status"], "status": {"does_not_equal": "Done"}}

            res = await client.post(url, headers=self.headers, json=payload)
            if res.status_code != 200:
                logger.error(f"Notion query failed ({db['name']}): {res.status_code} {res.text}")
                return db["name"], []

            items = []
            for page in res.json().get("results", []):
                props = page.get("properties", {})
                title_parts = props.get(schema["title"], {}).get("title", [])
                name = "".join([t.get("plain_text", "") for t in title_parts]).strip()
                if not name:
                    continue

                completed = False
                if schema["status"] and schema["status"] in props:
                    sp = props[schema["status"]]
                    if schema["status_type"] == "checkbox":
                        completed = bool(sp.get("checkbox", False))
                    elif schema["status_type"] == "status":
                        s_val = (sp.get("status") or {}).get("name", "").lower()
                        completed = s_val in ("done", "completed", "bought", "complete")

                if not include_completed and completed:
                    continue

                priority = ""
                if schema["priority"] and schema["priority"] in props:
                    pp = props[schema["priority"]]
                    if schema["priority_type"] == "select":
                        priority = (pp.get("select") or {}).get("name", "")
                    elif schema["priority_type"] == "multi_select":
                        priority = ", ".join([o.get("name", "") for o in pp.get("multi_select", [])])

                category = ""
                if schema["category"] and schema["category"] in props:
                    cp = props[schema["category"]]
                    if schema["category_type"] == "select":
                        category = (cp.get("select") or {}).get("name", "")
                    elif schema["category_type"] == "multi_select":
                        category = ", ".join([o.get("name", "") for o in cp.get("multi_select", [])])

                due_date = ""
                if schema["due_date"] and schema["due_date"] in props:
                    dp = props[schema["due_date"]].get("date")
                    if dp:
                        due_date = dp.get("start", "")

                notes = ""
                if schema["notes"] and schema["notes"] in props:
                    rt = props[schema["notes"]].get("rich_text", [])
                    notes = "".join([t.get("plain_text", "") for t in rt]).strip()

                items.append({
                    "id": page["id"],
                    "name": name,
                    "completed": completed,
                    "priority": priority,
                    "category": category,
                    "due_date": due_date,
                    "notes": notes,
                })
            return db["name"], items

    async def add_items(self, database_name: str, items: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        """Add one or more items (dicts with 'name' and optional metadata) to a database."""
        added: List[Dict[str, Any]] = []

        if self.is_mock:
            matched = self._match_db_name(database_name, list(self.mock_databases.keys()))
            if not matched:
                matched = database_name.strip().title()
                self.mock_databases.setdefault(matched, [])

            for item in items:
                raw_name = item.get("name", "") if isinstance(item, dict) else str(item)
                clean_name = raw_name.strip()
                if not clean_name:
                    continue
                # Capitalize first letter nicely without lowercasing acronyms
                clean_name = clean_name[0].upper() + clean_name[1:]
                entry = {
                    "id": f"mock-{random.randint(10000, 99999)}",
                    "name": clean_name,
                    "completed": False,
                    "priority": (item.get("priority") or "").strip() if isinstance(item, dict) else "",
                    "due_date": (item.get("due_date") or "").strip() if isinstance(item, dict) else "",
                    "category": (item.get("category") or "").strip() if isinstance(item, dict) else "",
                    "notes": (item.get("notes") or "").strip() if isinstance(item, dict) else "",
                }
                self.mock_databases[matched].append(entry)
                added.append(entry)
            return matched, added

        db = await self._resolve_live_db(database_name)
        if not db:
            return database_name, []

        # Standalone Notion Page: append to_do checkbox blocks
        if db.get("kind") == "page":
            children = []
            clean_names = []
            for item in items:
                raw_name = item.get("name", "") if isinstance(item, dict) else str(item)
                clean_name = raw_name.strip()
                if not clean_name:
                    continue
                clean_name = clean_name[0].upper() + clean_name[1:]
                # Append optional metadata inline for checklist pages
                if isinstance(item, dict):
                    extras = []
                    if item.get("priority"):
                        extras.append(f"[{item['priority']}]")
                    if item.get("due_date"):
                        extras.append(f"(due {item['due_date']})")
                    if extras:
                        clean_name = f"{clean_name} {' '.join(extras)}"
                clean_names.append(clean_name)
                children.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": clean_name}}],
                        "checked": False,
                    },
                })
            if not children:
                return db["name"], []
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.patch(
                    f"{self.base_url}/blocks/{db['id']}/children",
                    headers=self.headers,
                    json={"children": children},
                )
                if res.status_code == 200:
                    for blk, nm in zip(res.json().get("results", []), clean_names):
                        added.append({
                            "id": blk["id"],
                            "name": nm,
                            "completed": False,
                            "priority": "",
                            "due_date": "",
                            "category": "",
                            "notes": "",
                        })
                else:
                    logger.error(f"Failed appending to_do blocks to page {db['name']}: {res.status_code} {res.text}")
            return db["name"], added

        schema = db["schema"]
        async with httpx.AsyncClient(timeout=12.0) as client:
            for item in items:
                raw_name = item.get("name", "") if isinstance(item, dict) else str(item)
                clean_name = raw_name.strip()
                if not clean_name:
                    continue
                clean_name = clean_name[0].upper() + clean_name[1:]

                props: Dict[str, Any] = {
                    schema["title"]: {"title": [{"text": {"content": clean_name}}]}
                }

                if schema["status"]:
                    if schema["status_type"] == "checkbox":
                        props[schema["status"]] = {"checkbox": False}
                    elif schema["status_type"] == "status":
                        props[schema["status"]] = {"status": {"name": "Not started"}}

                if isinstance(item, dict):
                    if item.get("priority") and schema["priority"]:
                        val = item["priority"].strip().capitalize()
                        if schema["priority_type"] == "select":
                            props[schema["priority"]] = {"select": {"name": val}}
                        elif schema["priority_type"] == "multi_select":
                            props[schema["priority"]] = {"multi_select": [{"name": val}]}

                    if item.get("category") and schema["category"]:
                        val = item["category"].strip().capitalize()
                        if schema["category_type"] == "select":
                            props[schema["category"]] = {"select": {"name": val}}
                        elif schema["category_type"] == "multi_select":
                            props[schema["category"]] = {"multi_select": [{"name": val}]}

                    if item.get("due_date") and schema["due_date"]:
                        props[schema["due_date"]] = {"date": {"start": item["due_date"].strip()}}

                    if item.get("notes") and schema["notes"]:
                        props[schema["notes"]] = {"rich_text": [{"text": {"content": item["notes"].strip()}}]}

                res = await client.post(
                    f"{self.base_url}/pages",
                    headers=self.headers,
                    json={"parent": {"database_id": db["id"]}, "properties": props},
                )
                if res.status_code == 200:
                    page = res.json()
                    added.append({
                        "id": page["id"],
                        "name": clean_name,
                        "completed": False,
                        "priority": item.get("priority", "") if isinstance(item, dict) else "",
                        "due_date": item.get("due_date", "") if isinstance(item, dict) else "",
                        "category": item.get("category", "") if isinstance(item, dict) else "",
                        "notes": item.get("notes", "") if isinstance(item, dict) else "",
                    })
                else:
                    logger.error(f"Failed adding '{clean_name}' to {db['name']}: {res.status_code} {res.text}")
        return db["name"], added

    async def update_item(
        self,
        database_name: str,
        item_query: str,
        new_name: Optional[str] = None,
        completed: Optional[bool] = None,
        priority: Optional[str] = None,
        due_date: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Find an item by name (or ID) in a database and update its fields."""
        target = item_query.strip().lower()

        if self.is_mock:
            matched_db = self._match_db_name(database_name, list(self.mock_databases.keys()))
            if not matched_db:
                return database_name, None
            for it in self.mock_databases[matched_db]:
                if it["id"] == item_query or target in it["name"].lower() or it["name"].lower() in target:
                    if new_name:
                        it["name"] = new_name.strip()
                    if completed is not None:
                        it["completed"] = completed
                    if priority:
                        it["priority"] = priority.strip().capitalize()
                    if due_date:
                        it["due_date"] = due_date.strip()
                    if notes:
                        it["notes"] = notes.strip()
                    return matched_db, dict(it)
            return matched_db, None

        db = await self._resolve_live_db(database_name)
        if not db:
            return database_name, None

        _, all_items = await self.get_items(db["name"], include_completed=True)
        matched_item = None
        for it in all_items:
            if it["id"] == item_query or target in it["name"].lower() or it["name"].lower() in target:
                matched_item = it
                break

        if not matched_item:
            return db["name"], None

        # Standalone Notion Page: update the block directly
        if db.get("kind") == "page":
            btype = matched_item.get("block_type", "to_do")
            payload_data: Dict[str, Any] = {}
            if new_name:
                payload_data["rich_text"] = [{"type": "text", "text": {"content": new_name.strip()}}]
            if completed is not None and btype == "to_do":
                payload_data["checked"] = completed
            if not payload_data:
                return db["name"], matched_item
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.patch(
                    f"{self.base_url}/blocks/{matched_item['id']}",
                    headers=self.headers,
                    json={btype: payload_data},
                )
                if res.status_code == 200:
                    if new_name:
                        matched_item["name"] = new_name.strip()
                    if completed is not None:
                        matched_item["completed"] = completed
                    return db["name"], matched_item
                logger.error(f"Failed updating block {matched_item['id']}: {res.status_code} {res.text}")
                return db["name"], None

        schema = db["schema"]
        props: Dict[str, Any] = {}
        if new_name:
            props[schema["title"]] = {"title": [{"text": {"content": new_name.strip()}}]}
        if completed is not None and schema["status"]:
            if schema["status_type"] == "checkbox":
                props[schema["status"]] = {"checkbox": completed}
            elif schema["status_type"] == "status":
                props[schema["status"]] = {"status": {"name": "Done" if completed else "Not started"}}
        if priority and schema["priority"]:
            val = priority.strip().capitalize()
            if schema["priority_type"] == "select":
                props[schema["priority"]] = {"select": {"name": val}}
            elif schema["priority_type"] == "multi_select":
                props[schema["priority"]] = {"multi_select": [{"name": val}]}
        if due_date and schema["due_date"]:
            props[schema["due_date"]] = {"date": {"start": due_date.strip()}}
        if notes and schema["notes"]:
            props[schema["notes"]] = {"rich_text": [{"text": {"content": notes.strip()}}]}

        async with httpx.AsyncClient(timeout=12.0) as client:
            if props:
                res = await client.patch(
                    f"{self.base_url}/pages/{matched_item['id']}",
                    headers=self.headers,
                    json={"properties": props},
                )
            elif completed is True:
                # If no status column exists, archive completed item
                res = await client.patch(
                    f"{self.base_url}/pages/{matched_item['id']}",
                    headers=self.headers,
                    json={"archived": True},
                )
            else:
                return db["name"], matched_item

            if res.status_code == 200:
                if new_name:
                    matched_item["name"] = new_name.strip()
                if completed is not None:
                    matched_item["completed"] = completed
                if priority:
                    matched_item["priority"] = priority.strip().capitalize()
                if due_date:
                    matched_item["due_date"] = due_date.strip()
                if notes:
                    matched_item["notes"] = notes.strip()
                return db["name"], matched_item

            logger.error(f"Failed updating item {matched_item['id']}: {res.status_code} {res.text}")
            return db["name"], None

    async def delete_item_by_name(self, database_name: str, item_query: str) -> Tuple[str, Optional[str]]:
        """Delete/archive an item by fuzzy name match."""
        target = item_query.strip().lower()
        if self.is_mock:
            matched_db = self._match_db_name(database_name, list(self.mock_databases.keys()))
            if not matched_db:
                return database_name, None
            items = self.mock_databases[matched_db]
            for idx, it in enumerate(items):
                if target in it["name"].lower() or it["name"].lower() in target:
                    removed = items.pop(idx)
                    return matched_db, removed["name"]
            return matched_db, None

        db = await self._resolve_live_db(database_name)
        if not db:
            return database_name, None

        _, all_items = await self.get_items(db["name"], include_completed=True)
        for it in all_items:
            if target in it["name"].lower() or it["name"].lower() in target:
                ok = await self.delete_item(it["id"])
                return db["name"], it["name"] if ok else None
        return db["name"], None

    async def delete_item(self, page_id: str) -> bool:
        """Archive/delete a database row page OR a checklist block by ID."""
        if self.is_mock:
            for db_name, items in self.mock_databases.items():
                before = len(items)
                self.mock_databases[db_name] = [it for it in items if it["id"] != page_id]
                if len(self.mock_databases[db_name]) < before:
                    return True
            return False

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.patch(
                f"{self.base_url}/pages/{page_id}",
                headers=self.headers,
                json={"archived": True},
            )
            if res.status_code == 200:
                return True
            # Fallback for standalone checklist page blocks
            res_blk = await client.delete(f"{self.base_url}/blocks/{page_id}", headers=self.headers)
            return res_blk.status_code == 200

    async def search_workspace(self, query: str) -> List[Dict[str, Any]]:
        """Search across all mock or live Notion databases and pages."""
        q = query.strip().lower()
        results: List[Dict[str, Any]] = []

        if self.is_mock:
            for db_name, items in self.mock_databases.items():
                for it in items:
                    haystack = f"{it['name']} {it.get('notes', '')} {it.get('category', '')}".lower()
                    if q in haystack:
                        results.append({
                            "database": db_name,
                            "id": it["id"],
                            "name": it["name"],
                            "completed": it["completed"],
                            "notes": it.get("notes", ""),
                            "due_date": it.get("due_date", ""),
                            "priority": it.get("priority", ""),
                        })
            return results

        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.post(
                f"{self.base_url}/search",
                headers=self.headers,
                json={"query": query, "page_size": 20},
            )
            if res.status_code != 200:
                return []

            for obj in res.json().get("results", []):
                obj_type = obj.get("object")
                title = ""
                if obj_type == "database":
                    title = "".join([t.get("plain_text", "") for t in obj.get("title", [])]).strip()
                elif obj_type == "page":
                    for prop in obj.get("properties", {}).values():
                        if prop.get("type") == "title":
                            title = "".join([t.get("plain_text", "") for t in prop.get("title", [])]).strip()
                            break
                if title:
                    results.append({"type": obj_type, "id": obj["id"], "name": title})
            return results

    async def sample_items(self, database_name: str = "Shopping List", count: int = 2) -> Tuple[str, List[str]]:
        """Sample N random active items from a database."""
        resolved_db, items = await self.get_items(database_name, include_completed=False)
        if not items:
            return resolved_db, []
        names = [it["name"] for it in items]
        if len(names) <= count:
            return resolved_db, names
        return resolved_db, random.sample(names, count)

    async def check_item(self, query_name: str, database_name: str = "Shopping List") -> Tuple[bool, Optional[str]]:
        """Check if an item exists in the active items of a database."""
        target = query_name.strip().lower()
        _, items = await self.get_items(database_name, include_completed=False)
        for it in items:
            if target in it["name"].lower() or it["name"].lower() in target:
                return True, it["name"]
        return False, None
