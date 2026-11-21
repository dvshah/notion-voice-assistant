# 🚀 24/7 Free Cloud Hosting Guide (Android + Notion Voice Assistant)

Follow either option below to host your assistant online so it keeps running 24/7 — even when Antigravity is closed or your Android phone restarts.

---

## Option 1: Render.com (Easiest, 100% Free, No Credit Card)

1. **Push this folder to a Private GitHub Repository**:
   ```bash
   cd notion-voice-assistant
   git init
   git add .
   git commit -m "Initial Gemini + Notion Voice Assistant"
   # Create a private repo on github.com, then:
   git remote add origin https://github.com/YOUR_USERNAME/notion-voice-assistant.git
   git push -u origin main
   ```
   *(Your `.env` file is automatically excluded by `.gitignore` so your keys are never uploaded to GitHub.)*

2. **Deploy on Render**:
   - Go to [https://dashboard.render.com](https://dashboard.render.com) → click **New +** → **Blueprint** (or **Web Service**).
   - Connect your private `notion-voice-assistant` GitHub repository.
   - Render automatically reads `render.yaml`!
   - When prompted for secret Environment Variables, paste:
     - `GEMINI_API_KEY` = your Gemini key
     - `GEMINI_MODEL` = `gemini-3.5-flash-lite`
     - `NOTION_API_KEY` = your Notion `ntn_...` secret
     - `APP_ACCESS_PIN` = choose any personal PIN (e.g. `482910`) so only your phone can access it!
   - Click **Apply / Deploy**.

3. **Copy your permanent HTTPS URL** (e.g., `https://notion-voice-assistant-xxxx.onrender.com`).

---

## Option 2: Google Cloud Run (Fastest Wake-Up ~1-2s, Free Tier)

If you have the `gcloud` CLI installed:

```bash
cd notion-voice-assistant

gcloud run deploy notion-voice-assistant \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=YOUR_GEMINI_KEY,GEMINI_MODEL=gemini-3.5-flash-lite,NOTION_API_KEY=YOUR_NOTION_KEY,APP_ACCESS_PIN=YOUR_PIN"
```

Cloud Run builds the included `Dockerfile` automatically and gives you a permanent HTTPS URL like `https://notion-voice-assistant-xxxxx.a.run.app`.

---

## 📱 Connect Your Android Phone (One-Time Setup)

### A. 1-Tap Voice App on Home Screen (PWA)
1. Open Chrome on your Android phone and go to your deployed `https://...` URL.
2. Enter your `APP_ACCESS_PIN` once (your phone remembers it automatically).
3. Tap Chrome's **`⋮`** menu → **Add to Home screen** / **Install app**.
4. You now have a permanent voice app on your home screen!

### B. Hands-Free via MacroDroid / "Hey Google"
In MacroDroid's **HTTP Request** action:
- **Method:** `POST`
- **URL:** `https://YOUR-DEPLOYED-URL/api/voice`
- **Content Type:** `application/json`
- **Request Body:**
  ```json
  {
    "command": "{v=voice_command}",
    "pin": "YOUR_PIN"
  }
  ```
- **Next Action:** Speak Text → extract `speech` from the response!
