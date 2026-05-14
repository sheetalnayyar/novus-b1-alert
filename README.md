# 🏠 Novus Westshore B1 Availability Monitor

Automatically checks the **B1 floorplan** at Novus Westshore (Tampa) daily and emails you when new units appear.

## How it works

- Runs every day at **8:00 AM Eastern** via GitHub Actions (free)
- Queries the RealPage leasing API for available B1 units
- Compares with yesterday's results
- Sends you a **rich HTML email** listing every new unit (unit #, rent, floor, available date)

---

## ⚙️ One-time Setup (10 minutes)

### Step 1 — Create a free GitHub account
Go to [github.com](https://github.com) and sign up if you don't have one.

### Step 2 — Create a new repository
1. Click **+** → **New repository**
2. Name it `novus-b1-alert` (or anything you like)
3. Set it to **Private** (your email credentials will be stored here)
4. Click **Create repository**

### Step 3 — Upload these files
Upload all files from this zip into the root of your new repo, keeping the folder structure:
```
novus-b1-alert/
├── check_apartments.py
├── known_units.json
└── .github/
    └── workflows/
        └── check_apartments.yml
```

You can drag-and-drop files in the GitHub web UI, or use Git.

### Step 4 — Get a Gmail App Password
> You need this so the script can send email without exposing your real password.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Make sure **2-Step Verification** is ON
3. Search for **"App passwords"** → click it
4. Select **Mail** + **Windows Computer** → click **Generate**
5. Copy the 16-character password shown

### Step 5 — Add Secrets to GitHub
1. In your repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** for each:

| Secret name      | Value                          |
|------------------|-------------------------------|
| `GMAIL_USER`     | your Gmail address             |
| `GMAIL_PASSWORD` | the 16-char App Password       |
| `NOTIFY_EMAIL`   | email to receive alerts (can be same as GMAIL_USER) |

### Step 6 — Enable Actions & do a test run
1. Click the **Actions** tab in your repo
2. If prompted, click **"I understand my workflows, enable them"**
3. Click **"Novus Westshore B1 Availability Check"** → **"Run workflow"** → **Run**
4. Watch the logs — if it finds units, you'll get an email instantly!

---

## 📬 What the alert email looks like

You'll receive a styled HTML email with:
- Unit number(s)
- Monthly rent
- Available date
- Floor level
- A big red **"View & Apply Now"** button linking directly to the listing

---

## 🔧 Customisation

| What to change | Where |
|----------------|-------|
| Alert time | `cron: "0 12 * * *"` in `check_apartments.yml` (currently 8 AM ET) |
| Notify a different email | Change `NOTIFY_EMAIL` secret |
| Monitor a different floorplan | Change `FLOORPLAN_KEY` and `FLOORPLAN_NAME` in `check_apartments.py` |

---

## Troubleshooting

- **No email received on first run** — this is normal if no units are currently available. The script saves the current state and will alert on the *next new* unit.
- **Workflow fails** — check the Actions log for the error. Most common: incorrect App Password.
- **"Unit DATA_FOUND" in logs** — the API is reachable but returned data in an unexpected format. Open an issue or adjust `parse_units()` in the script.
