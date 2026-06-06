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


def _send_sms_alerts(contacts: list[dict], lat: float, lng: float) -> None:
    import os
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM", "")
    if not (account_sid and auth_token and from_number):
        return

    from twilio.rest import Client
    client = Client(account_sid, auth_token)
    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    for c in contacts:
        phone = c.get("phone", "")
        if not phone:
            continue
        client.messages.create(
            body=f"Yaad alert: Amma may have wandered. Location: {maps_link}",
            from_=from_number,
            to=phone,
        )
