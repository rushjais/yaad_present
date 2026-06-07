"""
B5 — Wander-safety module.
HARD GUARDRAIL: Yaad reassures + alerts a human. NEVER navigates.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .schemas import LocationAction, LocationPingResponse


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def handle_ping(lat: float, lng: float) -> LocationPingResponse:
    from .db import fetch_safe_zone, fetch_contacts_ordered, store_alert, store_interaction
    from .config import settings
    from supabase import create_client

    zone = await fetch_safe_zone()
    if not zone:
        return LocationPingResponse(
            inside_zone=True,
            nearest_place=None,
            action=LocationAction.none,
        )

    # Get home place coords
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    place_res = client.table("places").select("*").eq("id", zone["center_place_id"]).execute()
    places = place_res.data or []
    home = places[0] if places else None

    inside = True
    nearest_place = home["name"] if home else None
    if home and home.get("lat") and home.get("lng"):
        dist = _haversine_m(lat, lng, home["lat"], home["lng"])
        inside = dist <= float(zone["radius_m"])

    if inside:
        return LocationPingResponse(
            inside_zone=True,
            nearest_place=nearest_place,
            action=LocationAction.none,
        )

    # Outside zone — reassure + alert
    contacts = await fetch_contacts_ordered(zone.get("contact_ids_ordered", []))
    contact_names = [c["name"] for c in contacts]
    first_contact = contact_names[0] if contact_names else "your family"

    # Moss-personalized reassurance using nearest familiar place
    reassurance = (
        f"You're safe. I've let {first_contact} know and they're on their way. "
        f"Please stay where you are — {first_contact} will be there soon."
    )

    # Store alert
    try:
        await store_alert({
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": "wander",
            "lat": lat,
            "lng": lng,
            "contacts_notified": [c["id"] for c in contacts],
            "status": "active",
        })
    except Exception:
        pass

    # SMS via Twilio [CONFIRM push vs Twilio]
    try:
        _send_sms_alerts(contacts, lat, lng)
    except Exception:
        pass

    return LocationPingResponse(
        inside_zone=False,
        nearest_place=nearest_place,
        action=LocationAction.alert,
        reassurance_text=reassurance,
        contacts=contact_names,
    )


def _send_sms_alerts(contacts: list[dict], lat: float, lng: float) -> list[dict]:
    """Fire wander-alert SMS to each contact via Gmail SMTP → carrier
    email-to-SMS gateway. Returns a list of result dicts {contact, to,
    ok, error?} — used by the smoke test to verify e2e.

    Why not Twilio: trial toll-free numbers can't deliver SMS to US carriers
    without a 3-7 day Toll-Free Verification process. The email-to-SMS
    gateway path is instant, free, and bypasses all of that. Recipient sees
    a normal SMS on their phone.

    Address format: <number>@<carrier-gateway>. Google Fi uses
    @msg.fi.google.com; AT&T @txt.att.net; T-Mobile @tmomail.net.

    YAAD_DEMO_RECIPIENT_EMAIL override: when set, EVERY alert goes to that
    address regardless of contacts. Use during demo / smoke test so we
    don't need to populate phone+carrier on every contact row.
    """
    import os
    import smtplib
    import ssl
    from email.message import EmailMessage

    email_from = os.getenv("EMAIL_FROM", "").strip()
    app_password = os.getenv("EMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    demo_recipient = os.getenv("YAAD_DEMO_RECIPIENT_EMAIL", "").strip()
    if not (email_from and app_password):
        return [{"contact": None, "to": None, "ok": False,
                 "error": "EMAIL_FROM / EMAIL_APP_PASSWORD not set"}]

    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    ts = datetime.now(timezone.utc).strftime("%-I:%M %p UTC")

    # One SMTP connection, multiple sends. Use certifi's CA bundle —
    # macOS python.org Python sometimes ships without root certs, which
    # makes ssl.create_default_context() fail SSL handshake to Gmail.
    results: list[dict] = []
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=15)
        smtp.login(email_from, app_password)
    except Exception as e:
        return [{"contact": None, "to": None, "ok": False,
                 "error": f"SMTP login failed: {e!r}"}]

    try:
        for c in contacts:
            to = demo_recipient or (c.get("phone_email") or "").strip()
            if not to:
                results.append({"contact": c.get("name"), "to": None,
                                "ok": False, "error": "no phone_email"})
                continue
            msg = EmailMessage()
            # Keep body short — carrier gateways often truncate at ~160 chars
            # and prepend the from-address, so leave headroom.
            msg.set_content(
                f"Yaad alert ({ts}): Amma may have left her safe zone. "
                f"For {c.get('name', 'family')}. "
                f"Loc: {maps_link}"
            )
            msg["Subject"] = ""  # SMS gateways often drop subject; keep empty
            msg["From"] = email_from
            msg["To"] = to
            try:
                smtp.send_message(msg)
                results.append({"contact": c.get("name"), "to": to, "ok": True})
            except Exception as e:
                results.append({"contact": c.get("name"), "to": to,
                                "ok": False, "error": repr(e)})
    finally:
        try:
            smtp.quit()
        except Exception:
            pass
    return results
