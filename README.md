# ✨ Gemini + Notion Voice Assistant (Android & Web PWA)

A full conversational voice assistant that bakes the **Google Gemini API** directly into your **Notion workspace** via native Function Calling. Manage your **Shopping List**, **To-Do List**, **Quick Notes**, or **any other Notion database** you share with your integration—completely hands-free.

---

## 🌟 What You Can Say

Because Gemini handles reasoning and multi-step tool calling, you can speak completely naturally and even combine multiple requests in one sentence:

- **Shopping List**:
  - *"What is currently on my shopping list?"*
  - *"Add 2 avocados, sourdough bread, and oat milk to my shopping list"*
  - *"Tell me any two items that I have on my shopping list"*
  - *"I'm making pasta tonight—check if I have tomatoes and add parmesan if not"*
- **To-Do List**:
  - *"Add a high-priority to-do to book the dentist tomorrow"*
  - *"What's on my to-do list?"*
  - *"Mark pay rent as done and tell me what's left"*
- **Notes & Any Custom Notion Database**:
  - *"Search my Notion notes for pasta recipe"*
  - *"Save a quick note about gift ideas for Alex"*
  - Share **any** other database (e.g., *Books*, *Watchlist*, *Expenses*) with your Notion integration and Gemini discovers and uses it automatically!
- **Follow-up Conversation Memory**:
  - *"What's on my to-do list?"* → *"Actually, mark the second one as done."*

---

## 🏛️ Architecture

```
[ Android Voice (PWA / MacroDroid / Hey Google) ]
                       ↓
       [ POST /api/voice {"command": "..."} ]
                       ↓
   [ Gemini API (gemini-2.5-flash + Function Calling) ]
      ├── list_notion_databases   (auto-discovers all shared DBs)
      ├── get_items               (reads Shopping, To-Do, Notes, etc.)
      ├── add_items               (adds items with priority/date/notes)
      ├── update_item             (marks done, renames, updates fields)
      ├── delete_item             (archives items)
      ├── get_random_items        ("any two items")
      └── search_workspace        (searches all Notion pages & DBs)
                       ↕
               [ Notion REST API ]
                       ↓
      [ Natural TTS-ready Spoken Reply ]
```

---

## ⚡ Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure `.env`
```bash
cp .env.example .env
```
Add your keys to `.env`:
```ini
# Free key from https://aistudio.google.com/apikey
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# From https://www.notion.so/my-integrations
NOTION_API_KEY=ntn_your_notion_secret_here
```
*(In Notion, open your Shopping List, To-Do List, Quick Notes, or any other database → click `•••` → **Connections** → connect your integration. No manual database IDs required!)*

### 3. Start the Server
```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Run Tests
```bash
python3 test_nlp.py && python3 test_api.py
```
