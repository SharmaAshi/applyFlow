# Google OAuth2 Setup Guide
## (One-time setup — completely free)

---

## Step 1: Create a Google Cloud Project

1. Go to https://console.cloud.google.com
2. Click **"New Project"** → name it anything (e.g. "AutoMailApp")
3. Select it as your active project

---

## Step 2: Enable the Gmail API

1. In the left menu → **APIs & Services → Library**
2. Search **"Gmail API"** → click it → click **Enable**

---

## Step 3: Configure OAuth Consent Screen

1. Left menu → **APIs & Services → OAuth consent screen**
2. Choose **External** → click Create
3. Fill in:
   - App name: `AI Auto-Mail`
   - User support email: your Gmail
   - Developer contact: your Gmail
4. Click **Save and Continue** through all steps
5. On the **"Test users"** step → click **Add Users** → add your Gmail address
   *(This lets you use the app while it's in "testing" mode — no approval needed)*

---

## Step 4: Create OAuth Credentials

1. Left menu → **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: `AutoMailApp`
5. Under **Authorised redirect URIs**, add:
   - Local: `http://localhost:5050/oauth/callback`
   - Render: `https://YOUR-APP-NAME.onrender.com/oauth/callback`
6. Click **Create**
7. Click **Download JSON** → rename the file to `client_secret.json`
8. Put `client_secret.json` in the root of your project folder

---

## Step 5: Set Environment Variables

Create a `.env` file (or set these in Render dashboard):

```
GROQ_API_KEY=gsk_your_groq_key_here
FLASK_SECRET=any_long_random_string_here
```

Get a free Groq key at: https://console.groq.com

---

## Step 6: Deploy on Render (Free)

1. Push your project to GitHub
2. Go to https://render.com → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** Free
5. Add environment variables:
   - `GROQ_API_KEY` = your key
   - `FLASK_SECRET` = any random string
6. Upload `client_secret.json` as a **Secret File** (Render → Environment → Secret Files)
   - Path: `client_secret.json`

---

## How it works for users

1. User visits your app
2. Clicks **"Sign in with Google"**
3. Google asks: *"Allow AI Auto-Mail to send emails on your behalf?"*
4. User clicks Allow
5. App can now send emails from their Gmail — no password needed!

---

## Project file structure

```
project/
├── app.py
├── mainGraph.py
├── client_secret.json     ← downloaded from Google Cloud (never commit to git!)
├── requirements.txt
├── .env
├── .gitignore             ← add client_secret.json and .env here
└── templates/
    ├── index.html
    └── settings.html      ← no longer needed (can remove)
static/
    └── style.css
```

Add to `.gitignore`:
```
client_secret.json
.env
__pycache__/
```
