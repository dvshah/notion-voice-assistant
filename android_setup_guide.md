# 📱 Android Voice Integration Guide: Notion Shopping List

This guide walks you through setting up native voice control on your Android phone using **Google Assistant** ("Hey Google") and **MacroDroid** (or Tasker).

When you finish, you can say:
> 🗣️ *"Hey Google, shopping list"*  
> 🤖 Android asks: *"What would you like to do?"*  
> 🗣️ *"Add milk, eggs, and sourdough bread"*  
> 🔊 Phone speaks: *"Added Milk, Eggs, and Sourdough Bread to your shopping list."*

Or:
> 🗣️ *"Hey Google, shopping list"*  
> 🗣️ *"Tell me any two items that I have"*  
> 🔊 Phone speaks: *"Two items currently on your shopping list are Milk and Sourdough Bread."*

---

## 🚀 Architecture Overview

```
[ Your Voice: "Hey Google" ] 
          ↓
[ Google Assistant / MacroDroid on Android ]
          ↓ (Speech-to-Text)
[ POST /api/voice {"command": "..."} ]
          ↓
[ FastAPI Voice Service ] ↔ [ Notion API Database ]
          ↓
[ JSON {"speech": "Added milk and eggs..."} ]
          ↓
[ Android Text-To-Speech (Speaks aloud) ]
```

---

## Step 1: Host / Expose the Voice API

To allow your Android phone to call your assistant server from anywhere (even on mobile data outside your home Wi-Fi), your backend needs a public URL.

### Option A: Free Cloudflare Tunnel (Zero port-forwarding, 100% Free)
If running on your computer, server, or Raspberry Pi:
1. Install cloudflared:
   ```bash
   # Linux / Mac / Windows
   cloudflared tunnel --url http://localhost:8000
   ```
2. Cloudflare gives you a free HTTPS URL: `https://your-unique-name.trycloudflare.com`.
3. Your webhook URL is: `https://your-unique-name.trycloudflare.com/api/voice`

### Option B: Free Cloud Hosting (Render / Railway / Fly.io)
Deploy this repository to [Render.com](https://render.com) or [Railway.app](https://railway.app):
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Set Environment Variables: `NOTION_API_KEY` and `NOTION_DATABASE_ID`.
- You will get a permanent free HTTPS URL like: `https://my-notion-voice.onrender.com`.

---

## Step 2: Configure MacroDroid on Android

**MacroDroid** is a free Android automation app available directly in the [Google Play Store](https://play.google.com/store/apps/details?id=com.arlosoft.macrodroid).

### Creating the Macro:

1. Open **MacroDroid** and tap **"Add Macro"**.
2. Name it: `Notion Shopping Voice`.

#### 🔴 Trigger:
- Tap `+` under **Triggers**.
- Select **Assistant / Voice Shortcuts** > **Google Assistant Shortcut** (or choose **Home Screen Shortcut** / **Volume Button Long Press**).
- Alternatively, select **Connectivity** > **Webhook** or use Google Assistant Routine.

#### 🔵 Actions:
Add these 3 actions in order:

1. **Action 1: Prompt for Voice Input**
   - Tap `+` under **Actions**.
   - Select **User Input** > **Voice Input**.
   - Prompt message: `What would you like to do?`
   - Save result to string variable: `voice_command`.

2. **Action 2: Send to Notion Assistant Webhook**
   - Tap `+` under **Actions**.
   - Select **Applications** > **HTTP Request**.
   - Request Type: `POST`
   - URL: `https://YOUR-URL/api/voice`
   - Content Type: `application/json`
   - Request Body:
     ```json
     {"command": "{v=voice_command}"}
     ```
   - Check **"Block next action until complete"**.
   - Save response to string variable: `api_response`.

3. **Action 3: Extract Speech & Speak Aloud**
   - Tap `+` under **Actions**.
   - Select **Macrodroid Specific** > **Set Variable**.
     - Variable: `speech_text`
     - Extract with JSON path or regex: `"speech":"(.*?)"` from `{v=api_response}`.
   - Select **Device Actions** > **Speak Text**.
     - Text to speak: `{v=speech_text}`
     - Engine: Google Text-to-Speech.

4. Tap the save checkmark (✓) at the bottom right.

---

## Step 3: Connect with "Hey Google" Routine

1. Open the **Google Assistant** app or Google app on your Android.
2. Tap your profile picture > **Assistant Settings** > **Routines**.
3. Tap **+ New Routine**.
4. **Starter (Voice Command):**
   - Say: *"Shopping list"* or *"My shopping list"*.
5. **Action:**
   - Tap **Add Action** > **Adjust Home Devices / Open apps** > **Run MacroDroid Macro** > Select `Notion Shopping Voice`.
6. Save the routine.

Now whenever you say:
> **"Hey Google, shopping list"**  
Your phone triggers the macro, listens to what you need, updates Notion, and speaks back!

---

## Step 4: 1-Tap Home Screen Voice App (PWA)

If you also want a quick 1-tap floating icon on your phone:
1. Open Chrome on your Android phone.
2. Navigate to your server URL: `https://YOUR-URL/`.
3. Tap Chrome's three dots menu (⋮) in the top-right corner.
4. Select **"Add to Home screen"** or **"Install app"**.
5. An icon called **"Notion Voice"** will appear on your home screen. Tap it anytime to press the big microphone button and talk!
