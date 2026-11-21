# 📝 Notion Setup Guide: Shopping List Database & Integration

Follow these steps to connect your Notion account to the Voice Assistant.

---

## 1. Create a Notion Internal Integration Secret

1. Visit [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) in your browser.
2. Click **"+ New integration"**.
3. Fill in the basic info:
   - **Name**: `Shopping Voice Assistant`
   - **Associated workspace**: Select the workspace where your shopping list lives.
   - **Type**: `Internal`
4. Under **Capabilities**, make sure the following are checked:
   - Read content
   - Update content
   - Insert content
5. Click **Submit** / **Save**.
6. Copy the **Internal Integration Secret** (it starts with `ntn_` or `secret_`).
   Save this for your `.env` file as `NOTION_API_KEY`.

---

## 2. Set Up the Shopping List Database in Notion

You can create a new database or use an existing one!

1. In Notion, create a new page and select **Table** database (or Full page table).
2. Ensure you have the following columns:
   - **Name** (or **Item**) — Property Type: `Title` (the item name)
   - **Done** (or **Status**) — Property Type: `Checkbox` (or `Status`)
   - *(Optional)* **Category** — Property Type: `Select` (e.g. Dairy, Produce, Bakery)

> 💡 **Auto-detection**: The assistant automatically detects whatever property names you use! If you name your title column `Item` and your checkbox `Done`, it automatically recognizes them.

---

## 3. Connect Your Database to the Integration

**Crucial Step**: By default, Notion integrations cannot access any page unless you explicitly share it.

1. Open your Shopping List database page in Notion.
2. In the top-right corner, click the **three dots (`•••`)**.
3. Scroll down and click **"Connections"** (or **"Add connections"**).
4. Search for and select **`Shopping Voice Assistant`** (the integration you created in Step 1).
5. Click **Confirm** / **Allow access**.

---

## 4. Find Your Database ID

1. Open your database in your web browser.
2. Look at the URL in your address bar:
   ```
   https://www.notion.so/myworkspace/a8aec43384f447ed84390e8e42c2e089?v=b4...
   ```
3. The **Database ID** is the 32-character alphanumeric string right before the `?v=`:
   `a8aec43384f447ed84390e8e42c2e089`
4. Copy this string for your `.env` file as `NOTION_DATABASE_ID`.

---

## 5. Configure Your Environment

In the `notion-voice-assistant` directory:
1. Copy the example file:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your values:
   ```ini
   NOTION_API_KEY=ntn_your_secret_integration_token_here
   NOTION_DATABASE_ID=a8aec43384f447ed84390e8e42c2e089
   ```
3. Restart the server:
   ```bash
   python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```
4. Done! You will see `Live Notion Connected` in the dashboard!
