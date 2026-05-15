#!/usr/bin/env python3
import json, os, smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

PROPERTY_CODE    = "2962833"
FLOORPLAN_KEY    = "53643"
FLOORPLAN_NAME   = "B1"
PROPERTY_NAME    = "Novus Westshore"
PROPERTY_URL     = "https://2962833.onlineleasing.realpage.com/#k=53643"
KNOWN_UNITS_FILE = "known_units.json"

GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")
NOTIFY_EMAIL   = os.environ.get("NOTIFY_EMAIL", GMAIL_USER)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"https://{PROPERTY_CODE}.onlineleasing.realpage.com/",
    "Origin": f"https://{PROPERTY_CODE}.onlineleasing.realpage.com",
}

def now():
    return datetime.now(timezone.utc)

def fetch_available_units():
    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1 — get the floorplans list and find B1
    fp_url = f"https://capi.myleasestar.com/v2/property/{PROPERTY_CODE}/floorplans"
    print(f"  Fetching floorplans: {fp_url}")
    try:
        resp = session.get(fp_url, timeout=15)
        print(f"  Status: {resp.status_code}")
        data = resp.json()

        floorplans = data.get("floorplans", [])
        print(f"  Found {len(floorplans)} floorplan(s) total")

        b1_fp = None
        for fp in floorplans:
            name = str(fp.get("name", fp.get("Name", "")))
            fp_key = str(fp.get("id", fp.get("floorplanKey", fp.get("key", ""))))
            print(f"    Floorplan: name={name!r}, id={fp_key}, keys={list(fp.keys())}")
            if name.strip().upper() == FLOORPLAN_NAME.upper() or fp_key == FLOORPLAN_KEY:
                b1_fp = fp
                print(f"    ✓ Matched B1 floorplan!")

        if b1_fp:
            # Print full B1 floorplan data so we can see its structure
            print(f"  B1 data: {json.dumps(b1_fp, indent=2)[:2000]}")

            # Try to get units from inline data first
            units_inline = b1_fp.get("units", b1_fp.get("Units", []))
            if units_inline:
                print(f"  ✓ Found {len(units_inline)} unit(s) inline in floorplan")
                return [extract_unit_info(u) for u in units_inline if extract_unit_info(u)]

            # Try dedicated units endpoint using the floorplan's own id
            fp_id = b1_fp.get("id", b1_fp.get("floorplanKey", FLOORPLAN_KEY))
            for units_url in [
                f"https://capi.myleasestar.com/v2/floorplan/{fp_id}/units",
                f"https://capi.myleasestar.com/v2/property/{PROPERTY_CODE}/floorplan/{fp_id}/units",
                f"https://capi.myleasestar.com/v2/property/{PROPERTY_CODE}/units?floorplanId={fp_id}",
            ]:
                try:
                    print(f"  Trying units endpoint: {units_url}")
                    r = session.get(units_url, timeout=15)
                    print(f"  Status: {r.status_code}")
                    if r.status_code == 200:
                        udata = r.json()
                        print(f"  Units response: {json.dumps(udata)[:500]}")
                        parsed = parse_units(udata)
                        if parsed:
                            return parsed
                except Exception as e:
                    print(f"  Error: {e}")

    except Exception as e:
        print(f"  Error fetching floorplans: {e}")

    print("⚠ No unit data found. Check logs above for API structure clues.")
    return []

def parse_units(data):
    units = []
    if isinstance(data, list):
        for item in data:
            u = extract_unit_info(item)
            if u: units.append(u)
        return units
    if isinstance(data, dict):
        for key in ("units","Units","availableUnits","AvailableUnits","items","Items"):
            if key in data and isinstance(data[key], list) and data[key]:
                for item in data[key]:
                    u = extract_unit_info(item)
                    if u: units.append(u)
                if units: return units
    return []

def extract_unit_info(item):
    if not isinstance(item, dict): return None

    unit_id = (item.get("unitId") or item.get("UnitId") or
               item.get("unit") or item.get("Unit") or
               item.get("unitNumber") or item.get("UnitNumber") or
               item.get("id") or item.get("Id"))
    if not unit_id: return None

def load_known_units():
    try:
        if os.path.exists(KNOWN_UNITS_FILE):
            with open(KNOWN_UNITS_FILE) as f:
                content = f.read().strip()
                if content:
                    return set(json.loads(content).get("unit_ids", []))
    except Exception as e:
        print(f"  ⚠ Could not read known_units.json ({e}), starting fresh.")
    return set()

def save_known_units(units):
    with open(KNOWN_UNITS_FILE, "w") as f:
        json.dump({"unit_ids": [u["unit"] for u in units],
                   "last_checked": now().isoformat(),
                   "count": len(units)}, f, indent=2)

def send_email(new_units, all_units):
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("⚠ Email credentials missing.")
        return
    rows = "".join(
        f"<tr><td style='padding:8px 12px;border-bottom:1px solid #eee;font-weight:bold'>#{u['unit']}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{u['rent']}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{u['available_date']}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{u['floor']}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{u['sqft']} sqft</td></tr>"
        for u in new_units)
    html = f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#2c3e50;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">🏠 New B1 Unit Alert!</h2>
        <p style="margin:4px 0 0;opacity:0.8">{PROPERTY_NAME} · Tampa, FL</p></div>
      <div style="background:#f9f9f9;padding:20px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px">
        <p><strong>{len(new_units)} new B1 unit(s)</strong> just became available:</p>
        <table style="border-collapse:collapse;width:100%;background:white">
          <thead><tr style="background:#2c3e50;color:white">
            <th style="padding:10px 12px;text-align:left">Unit</th>
            <th style="padding:10px 12px;text-align:left">Rent</th>
            <th style="padding:10px 12px;text-align:left">Available</th>
            <th style="padding:10px 12px;text-align:left">Floor</th>
            <th style="padding:10px 12px;text-align:left">Size</th>
          </tr></thead><tbody>{rows}</tbody></table>
        <p style="margin-top:20px">
          <a href="{PROPERTY_URL}" style="background:#e74c3c;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold">👉 View &amp; Apply Now</a></p>
        <p style="color:#888;font-size:12px">Checked: {now().strftime('%Y-%m-%d %H:%M UTC')}</p>
      </div></body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 {len(new_units)} New B1 Unit(s) at {PROPERTY_NAME}!"
    msg["From"] = GMAIL_USER
    msg["To"]   = NOTIFY_EMAIL
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_PASSWORD)
        s.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
    print(f"✉ Email sent to {NOTIFY_EMAIL}")

def main():
    print(f"[{now().isoformat()}] Checking {PROPERTY_NAME} B1...")
    current_units = fetch_available_units()
    print(f"  Found {len(current_units)} unit(s)")
    known_ids = load_known_units()
    new_units = [u for u in current_units if u["unit"] not in known_ids]
    if new_units:
        print(f"  🆕 New: {[u['unit'] for u in new_units]}")
        send_email(new_units, current_units)
    else:
        print("  No new units.")
    save_known_units(current_units)
    print("  Done.")

if __name__ == "__main__":
    main()
