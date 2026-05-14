#!/usr/bin/env python3
"""
Novus Westshore B1 Floorplan Availability Monitor
Checks daily for new available units and sends email alerts.
"""

import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ─── Configuration ────────────────────────────────────────────────────────────
PROPERTY_CODE   = "2962833"
FLOORPLAN_KEY   = "53643"   # B1 floorplan key from the URL
FLOORPLAN_NAME  = "B1"
PROPERTY_NAME   = "Novus Westshore"
PROPERTY_URL    = "https://2962833.onlineleasing.realpage.com/#k=53643"
KNOWN_UNITS_FILE = "known_units.json"

# RealPage / LeaseStar API endpoints to try (in order)
API_ENDPOINTS = [
    f"https://capi.myleasestar.com/v2/floorplan/{FLOORPLAN_KEY}/units",
    f"https://capi.myleasestar.com/v2/property/{PROPERTY_CODE}/floorplans/{FLOORPLAN_KEY}/units",
    f"https://capi.myleasestar.com/v2/property/{PROPERTY_CODE}/availableunits?floorplanKey={FLOORPLAN_KEY}",
    f"https://capi.myleasestar.com/v2/floorplans?propertyCode={PROPERTY_CODE}",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": f"https://{PROPERTY_CODE}.onlineleasing.realpage.com/",
    "Origin": f"https://{PROPERTY_CODE}.onlineleasing.realpage.com",
}

# ─── Email settings (set via GitHub Secrets) ──────────────────────────────────
GMAIL_USER     = os.environ.get("GMAIL_USER", "")      # your Gmail address
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")  # Gmail App Password
NOTIFY_EMAIL   = os.environ.get("NOTIFY_EMAIL", GMAIL_USER)  # who to alert


def fetch_available_units() -> list[dict]:
    """Try multiple RealPage API endpoints to find B1 available units."""
    session = requests.Session()
    session.headers.update(HEADERS)

    for url in API_ENDPOINTS:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                units = parse_units(data)
                if units is not None:
                    print(f"✓ Got data from: {url}")
                    return units
        except Exception as e:
            print(f"  Endpoint failed ({url}): {e}")

    # Fallback: check if the property page itself contains JSON data
    try:
        fallback_url = f"https://capi.myleasestar.com/v2/property/{PROPERTY_CODE}"
        resp = session.get(fallback_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Got property data, searching for B1 units...")
            return parse_units_from_property(data)
    except Exception as e:
        print(f"  Fallback failed: {e}")

    print("⚠ Could not reach any API endpoint. Will retry next run.")
    return []


def parse_units(data) -> list[dict] | None:
    """Parse unit data from various API response shapes."""
    units = []

    # Shape 1: direct list of units
    if isinstance(data, list):
        for item in data:
            unit = extract_unit_info(item)
            if unit:
                units.append(unit)
        return units if units else None

    # Shape 2: {units: [...]}
    if isinstance(data, dict):
        for key in ("units", "Units", "availableUnits", "AvailableUnits", "items"):
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    unit = extract_unit_info(item)
                    if unit:
                        units.append(unit)
                return units if units else None

        # Shape 3: {floorplans: [{..., units: [...]}]}
        for key in ("floorplans", "FloorPlans"):
            if key in data and isinstance(data[key], list):
                for fp in data[key]:
                    fp_name = fp.get("name", fp.get("Name", fp.get("floorplanName", "")))
                    if FLOORPLAN_NAME.lower() in str(fp_name).lower():
                        for item in fp.get("units", fp.get("Units", [])):
                            unit = extract_unit_info(item)
                            if unit:
                                units.append(unit)
                return units if units else None

    return None


def parse_units_from_property(data) -> list[dict]:
    """Dig through property-level data to find B1 units."""
    units = []
    raw = json.dumps(data)
    # If "B1" appears in the payload, we might still extract something
    if FLOORPLAN_NAME in raw:
        # Best-effort: return a sentinel so we know the property is reachable
        return [{"unit": "DATA_FOUND", "note": "B1 floorplan found in property data"}]
    return units


def extract_unit_info(item: dict) -> dict | None:
    """Normalise a unit record to a simple dict."""
    if not isinstance(item, dict):
        return None

    unit_id = (
        item.get("unitId") or item.get("UnitId") or
        item.get("unit") or item.get("Unit") or
        item.get("unitNumber") or item.get("UnitNumber") or
        item.get("id") or str(item)
    )

    available = (
        item.get("available") or item.get("Available") or
        item.get("isAvailable") or item.get("IsAvailable") or
        item.get("availableDate") or item.get("AvailableDate") or
        True  # if it's in the list, assume available
    )

    rent = (
        item.get("rent") or item.get("Rent") or
        item.get("price") or item.get("Price") or
        item.get("marketRent") or item.get("MarketRent") or
        "N/A"
    )

    avail_date = (
        item.get("availableDate") or item.get("AvailableDate") or
        item.get("moveInDate") or item.get("MoveInDate") or
        "N/A"
    )

    floor = (
        item.get("floor") or item.get("Floor") or
        item.get("floorLevel") or "N/A"
    )

    return {
        "unit": str(unit_id),
        "rent": str(rent),
        "available_date": str(avail_date),
        "floor": str(floor),
    }


def load_known_units() -> set[str]:
    """Load previously seen unit IDs from file."""
    if os.path.exists(KNOWN_UNITS_FILE):
        with open(KNOWN_UNITS_FILE) as f:
            data = json.load(f)
            return set(data.get("unit_ids", []))
    return set()


def save_known_units(units: list[dict]):
    """Persist current unit IDs to file."""
    with open(KNOWN_UNITS_FILE, "w") as f:
        json.dump({
            "unit_ids": [u["unit"] for u in units],
            "last_checked": datetime.utcnow().isoformat() + "Z",
            "count": len(units),
        }, f, indent=2)


def send_email(new_units: list[dict], all_units: list[dict]):
    """Send an email notification listing new B1 units."""
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("⚠ Email credentials not set — skipping email.")
        print("New units found:", new_units)
        return

    subject = f"🏠 New {FLOORPLAN_NAME} Unit(s) Available at {PROPERTY_NAME}!"

    # Build HTML body
    rows = ""
    for u in new_units:
        rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:bold">#{u['unit']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{u['rent']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{u['available_date']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{u['floor']}</td>
        </tr>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#2c3e50;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">🏠 New B1 Unit Alert!</h2>
        <p style="margin:4px 0 0;opacity:0.8">{PROPERTY_NAME} · Tampa, FL</p>
      </div>
      <div style="background:#f9f9f9;padding:20px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px">
        <p><strong>{len(new_units)} new {FLOORPLAN_NAME} unit(s)</strong> just became available:</p>
        <table style="border-collapse:collapse;width:100%;background:white;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1)">
          <thead>
            <tr style="background:#2c3e50;color:white">
              <th style="padding:10px 12px;text-align:left">Unit</th>
              <th style="padding:10px 12px;text-align:left">Rent</th>
              <th style="padding:10px 12px;text-align:left">Available</th>
              <th style="padding:10px 12px;text-align:left">Floor</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <p style="margin-top:20px">
          <a href="{PROPERTY_URL}"
             style="background:#e74c3c;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold">
            👉 View & Apply Now
          </a>
        </p>
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0">
        <p style="color:#888;font-size:12px">
          Total available B1 units: {len(all_units)} &nbsp;·&nbsp;
          Checked: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
        </p>
      </div>
    </html></body>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"✉ Alert email sent to {NOTIFY_EMAIL}")


def main():
    print(f"[{datetime.utcnow().isoformat()}] Checking {PROPERTY_NAME} B1 availability...")

    current_units = fetch_available_units()
    print(f"  Found {len(current_units)} available B1 unit(s)")

    known_ids   = load_known_units()
    current_ids = {u["unit"] for u in current_units}

    new_units = [u for u in current_units if u["unit"] not in known_ids]

    if new_units:
        print(f"  🆕 {len(new_units)} NEW unit(s) detected: {[u['unit'] for u in new_units]}")
        send_email(new_units, current_units)
    else:
        print("  No new units since last check.")

    save_known_units(current_units)
    print("  State saved.")

    # Exit with code 1 if new units found (makes GitHub Actions log prominent)
    if new_units:
        sys.exit(0)  # still success so workflow completes normally


if __name__ == "__main__":
    main()
