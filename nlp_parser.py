import re
from typing import Dict, Any, List

WORD_TO_NUMBER = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def clean_text(text: str) -> str:
    """Lowercase and remove trailing punctuation."""
    t = text.strip().lower()
    t = re.sub(r"[?!.]+$", "", t)
    return t.strip()


def detect_target_database(text: str) -> str:
    """Detect whether the user is talking about To-Do List, Quick Notes, or Shopping List."""
    if re.search(r"\b(to[\s-]?do|task|tasks|chore|chores|reminder|reminders)\b", text):
        return "To-Do List"
    if re.search(r"\b(note|notes|memo|idea|ideas)\b", text):
        return "Quick Notes"
    return "Shopping List"


def detect_priority(text: str) -> str:
    if re.search(r"\bhigh[\s-]?priority\b|\burgent\b|\bimportant\b", text):
        return "High"
    if re.search(r"\blow[\s-]?priority\b", text):
        return "Low"
    if re.search(r"\bmedium[\s-]?priority\b", text):
        return "Medium"
    return ""


def split_items(items_text: str) -> List[str]:
    """
    Split items separated by commas, 'and', 'plus', or '&'.
    e.g. 'milk, eggs and two bananas' -> ['milk', 'eggs', 'two bananas']
    """
    cleaned = re.sub(
        r"\b(to|on|into|in)\s+(?:the\s+|my\s+)?(?:shopping|grocery|to[\s-]?do|tasks?|quick\s+notes?|notes?)\s*(?:list)?\b.*$",
        "",
        items_text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(to|on|into)\s+(?:the\s+|my\s+)?list\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(please|thanks|thank you)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(a\s+)?(high|medium|low)[\s-]?priority\s+(to[\s-]?do|task|item)?\s*(to\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:a\s+)?(?:to[\s-]?do|task|note)\s*(?:to|about|:)?\s*", "", cleaned, flags=re.IGNORECASE).strip()

    normalized = re.sub(r"\s+(?:and|&|plus)\s+", ",", cleaned, flags=re.IGNORECASE)
    parts = [p.strip() for p in normalized.split(",") if p.strip()]
    final_items = []
    for p in parts:
        p = re.sub(r"^(some|a couple of)\s+", "", p, flags=re.IGNORECASE).strip()
        if p and p not in ["to", "on", "my", "the", "shopping list", "to-do list", "todo list", "list"]:
            final_items.append(p)
    return final_items


def parse_voice_command(query: str) -> Dict[str, Any]:
    """
    Parse a raw speech-to-text transcript into an intent, target database, and parameters.
    Used as an instant zero-key fallback when GEMINI_API_KEY is not configured.
    """
    text = clean_text(query)
    if not text:
        return {"intent": "help", "database": "Shopping List", "raw": query}

    database = detect_target_database(text)
    priority = detect_priority(text)

    # 1. Search workspace
    search_match = re.search(r"^(?:search|find|look\s+up)\s+(?:notion\s+|my\s+notes\s+)?(?:for\s+)?(.+)$", text)
    if search_match:
        q = search_match.group(1).strip()
        if q:
            return {"intent": "search", "query": q, "database": database, "raw": query}

    # 2. Clear / Empty list
    if re.search(r"^(clear|empty|delete all|wipe)\s+(?:my\s+|the\s+)?(?:shopping|to[\s-]?do|task)?\s*list\b", text):
        return {"intent": "clear_list", "database": database, "raw": query}

    # 3. Read list / what's on my list
    if re.search(
        r"^(?:what(?:'s|\s+is|\s+are)\s+(?:currently\s+)?(?:on\s+)?(?:my\s+|the\s+)?(?:shopping|to[\s-]?do|tasks?|notes?)?\s*(?:list|tasks?|notes?)|"
        r"read\s+(?:out\s+)?(?:my\s+|the\s+)?(?:shopping|to[\s-]?do|tasks?|notes?)?\s*(?:list|tasks?|notes?)|"
        r"tell\s+me\s+what(?:'s|\s+is|\s+are)\s+(?:currently\s+)?(?:on\s+)?(?:my\s+|the\s+)?(?:shopping|to[\s-]?do|tasks?|notes?)?\s*(?:list|tasks?|notes?)|"
        r"what\s+(?:items\s+|tasks\s+)?do\s+i\s+(?:need|have)(?:\s+(?:to\s+(?:buy|do)|on\s+(?:my|the)\s+(?:shopping\s+|to[\s-]?do\s+)?list))?|"
        r"show\s+(?:me\s+)?(?:my\s+|the\s+)?(?:shopping|to[\s-]?do|tasks?|notes?)?\s*(?:list|tasks?|notes?)|"
        r"(?:shopping|to[\s-]?do|todo)\s+list$|"
        r"my\s+(?:tasks|notes)$|"
        r"list\s+items$)",
        text,
    ):
        return {"intent": "read_list", "database": database, "raw": query}

    # 4. Sample items (e.g., "tell me any two items that i have")
    sample_match = re.search(
        r"(?:tell\s+me|give\s+me|what\s+are|show\s+me|name)?\s*(?:any|some)?\s*(\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a couple of)\b)\s*(?:random\s+)?(?:items?|tasks?)(?:\s+(?:that\s+)?i\s+have|\s+(?:on|from)\s+(?:my\s+|the\s+)?(?:shopping\s+|to[\s-]?do\s+)?list)?",
        text,
    )
    if sample_match:
        count_str = sample_match.group(1).strip()
        if count_str == "a couple of":
            count = 2
        elif count_str.isdigit():
            count = int(count_str)
        else:
            count = WORD_TO_NUMBER.get(count_str, 2)
        return {"intent": "sample_items", "count": count, "database": database, "raw": query}

    short_sample = re.search(r"^(?:any\s+)?(\b(?:\d+|one|two|three|four|five)\b)\s+(?:items?|tasks?)$", text)
    if short_sample:
        c_str = short_sample.group(1)
        count = int(c_str) if c_str.isdigit() else WORD_TO_NUMBER.get(c_str, 2)
        return {"intent": "sample_items", "count": count, "database": database, "raw": query}

    # 5. Check specific item
    check_match = re.search(
        r"^(?:do\s+(?:i|we)\s+have|is\s+there|is|check\s+(?:if\s+we\s+have|if\s+there\s+is|if)?)\s+(.+)$",
        text,
    )
    if check_match:
        target = check_match.group(1).strip()
        target = re.sub(r"\s+(?:on|in)\s+(?:the|my)\s+(?:shopping\s+|to[\s-]?do\s+)?list.*$", "", target).strip()
        target = re.sub(r"\s+already$", "", target).strip()
        target = re.sub(r"^(any|some|a|an)\s+", "", target).strip()
        if target and target not in ["my shopping list", "shopping list", "the list", "my to-do list", "to-do list"]:
            return {"intent": "check_item", "item": target, "database": database, "raw": query}

    # 6. Remove / Complete item
    complete_match = re.search(
        r"^(?:remove|delete|bought|i\s+bought|i\s+got|got|check\s+off|cross\s+off|mark\s+off|mark|finish|finished|completed|done\s+with)\s+(.+?)(?:\s+(?:from|off|on)\s+(?:my\s+|the\s+)?(?:shopping\s+|to[\s-]?do\s+|task\s+)?list|\s+as\s+(?:done|finished|bought|complete|completed))?$",
        text,
    )
    if complete_match:
        item_text = complete_match.group(1).strip()
        item_text = re.sub(r"\s+(?:from|off|on)\s+(?:my\s+|the\s+)?(?:shopping\s+|to[\s-]?do\s+|task\s+)?list.*$", "", item_text).strip()
        item_text = re.sub(r"\s+as\s+(?:done|finished|bought|complete|completed)$", "", item_text).strip()
        item_text = re.sub(r"^(the|some|a|an)\s+", "", item_text).strip()
        return {"intent": "complete_item", "item": item_text, "database": database, "raw": query}

    # 7. Add items / tasks / notes
    add_match = re.search(
        r"^(?:add|put|create|save|note|remind\s+me\s+to|need|we\s+need|i\s+need|buy|remember\s+to\s+buy|remember\s+to\s+get|remember\s+to|get)\s+(.+)$",
        text,
    )
    if add_match:
        items_raw = add_match.group(1).strip()
        if re.match(r"^(?:remind\s+me\s+to|remember\s+to(?!\s+(?:buy|get)))", text):
            database = "To-Do List"
        items_raw = re.sub(r"^(?:to\s+buy|to\s+get)\s+", "", items_raw).strip()
        items = split_items(items_raw)
        if items:
            return {"intent": "add_items", "items": items, "database": database, "priority": priority, "raw": query}

    # 8. Help
    if "help" in text or "what can you do" in text:
        return {"intent": "help", "database": database, "raw": query}

    # 9. Short phrase fallback
    if not any(text.startswith(w) for w in ["why", "how", "where", "who", "when"]):
        items = split_items(text)
        if items and len(items) <= 5:
            return {"intent": "add_items", "items": items, "database": database, "priority": priority, "raw": query}

    return {"intent": "unknown", "database": database, "raw": query}
