"""
Mock tools for the Lyft multi-agent customer support system.

Each tool is a LangChain @tool that can be bound to any subagent.
In-memory state is reset between tests via clear_state().
"""
from __future__ import annotations

import uuid
from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# In-memory state (mock Lyft backend)
# ---------------------------------------------------------------------------

_RIDERS = {
    "rider_001": {"name": "Alice Johnson", "email": "alice@example.com", "status": "active", "member_since": "2022-01"},
    "rider_002": {"name": "Bob Williams",  "email": "bob@example.com",   "status": "active", "member_since": "2021-06"},
    "rider_003": {"name": "Carol Davis",   "email": "carol@example.com", "status": "suspended", "member_since": "2023-03"},
}

_DRIVERS = {
    "driver_001": {"name": "Carlos Rivera",  "email": "carlos@example.com", "status": "active", "rating": 4.85, "vehicle": "Toyota Prius 2022"},
    "driver_002": {"name": "Diana Chen",     "email": "diana@example.com",  "status": "active", "rating": 4.92, "vehicle": "Honda Accord 2023"},
    "driver_003": {"name": "Evan Thompson",  "email": "evan@example.com",   "status": "deactivated", "rating": 4.20, "vehicle": "Ford Fusion 2020"},
}

_TRIPS = {
    "trip_001": {"rider_id": "rider_001", "driver_id": "driver_001", "amount": 24.50, "base_fare": 15.00, "surge": 0.0,  "status": "completed", "date": "2026-06-01", "pickup": "123 Main St", "dropoff": "456 Oak Ave"},
    "trip_002": {"rider_id": "rider_002", "driver_id": "driver_001", "amount": 15.75, "base_fare": 12.50, "surge": 3.25, "status": "completed", "date": "2026-06-02", "pickup": "789 Pine Rd", "dropoff": "321 Elm St"},
    "trip_003": {"rider_id": "rider_001", "driver_id": "driver_002", "amount": 35.00, "base_fare": 22.00, "surge": 13.00,"status": "completed", "date": "2026-06-05", "pickup": "555 Market St", "dropoff": "888 Broadway"},
    "trip_004": {"rider_id": "rider_003", "driver_id": "driver_002", "amount": 18.00, "base_fare": 18.00, "surge": 0.0,  "status": "completed", "date": "2026-06-06", "pickup": "100 First St", "dropoff": "200 Second St"},
}

_EARNINGS = {
    "driver_001": {"week": "2026-W23", "gross": 842.50, "net": 720.00, "trips": 32, "online_hours": 28.5, "bonuses": 50.00},
    "driver_002": {"week": "2026-W23", "gross": 1120.00, "net": 960.00, "trips": 45, "online_hours": 36.0, "bonuses": 75.00},
    "driver_003": {"week": "2026-W23", "gross": 210.00,  "net": 180.00, "trips": 8,  "online_hours": 10.0, "bonuses": 0.0},
}

_DAMAGE_CLAIMS: list[dict] = []
_TICKETS: list[dict] = []
_REFUNDS: list[dict] = []


# ---------------------------------------------------------------------------
# Rider tools
# ---------------------------------------------------------------------------

@tool
def get_rider_info(rider_id: str) -> dict:
    """Get rider account information by rider ID."""
    rider = _RIDERS.get(rider_id)
    if not rider:
        return {"error": f"Rider '{rider_id}' not found"}
    return {"rider_id": rider_id, **rider}


@tool
def get_trip_info(trip_id: str) -> dict:
    """Get full trip details including fare breakdown, pickup/dropoff, and participants."""
    trip = _TRIPS.get(trip_id)
    if not trip:
        return {"error": f"Trip '{trip_id}' not found"}
    return {"trip_id": trip_id, **trip}


@tool
def process_refund(rider_id: str, trip_id: str, amount: float, reason: str) -> dict:
    """
    Process a refund for a rider for a specific trip.
    Args:
        rider_id: The rider's ID.
        trip_id: The trip to refund.
        amount: Dollar amount to refund.
        reason: Reason for the refund (overcharge, service_failure, safety_incident, cancellation).
    """
    trip = _TRIPS.get(trip_id)
    if not trip:
        return {"error": f"Trip '{trip_id}' not found"}
    if trip["rider_id"] != rider_id:
        return {"error": "This trip does not belong to the specified rider"}
    if amount > trip["amount"]:
        return {"error": f"Refund amount ${amount:.2f} exceeds trip amount ${trip['amount']:.2f}"}

    refund = {
        "refund_id": f"REF-{uuid.uuid4().hex[:8].upper()}",
        "rider_id": rider_id,
        "trip_id": trip_id,
        "amount": amount,
        "reason": reason,
        "status": "approved",
        "processing_days": 3,
    }
    _REFUNDS.append(refund)
    return refund


# ---------------------------------------------------------------------------
# Driver tools
# ---------------------------------------------------------------------------

@tool
def get_driver_info(driver_id: str) -> dict:
    """Get driver account information, vehicle details, and rating."""
    driver = _DRIVERS.get(driver_id)
    if not driver:
        return {"error": f"Driver '{driver_id}' not found"}
    return {"driver_id": driver_id, **driver}


@tool
def get_driver_earnings(driver_id: str, period: str = "current_week") -> dict:
    """
    Get driver earnings for a period.
    Args:
        driver_id: The driver's ID.
        period: "current_week", "last_week", or "last_month".
    """
    earnings = _EARNINGS.get(driver_id)
    if not earnings:
        return {"error": f"No earnings found for driver '{driver_id}'"}
    return {"driver_id": driver_id, "period": period, **earnings}


@tool
def submit_damage_claim(driver_id: str, trip_id: str, description: str, estimated_cost: float) -> dict:
    """
    Submit a vehicle damage claim for a driver after a trip.
    Args:
        driver_id: The driver's ID.
        trip_id: The trip where damage occurred.
        description: Description of the damage.
        estimated_cost: Estimated repair cost in dollars.
    """
    trip = _TRIPS.get(trip_id)
    if not trip:
        return {"error": f"Trip '{trip_id}' not found"}
    if trip["driver_id"] != driver_id:
        return {"error": "This trip was not driven by the specified driver"}

    claim = {
        "claim_id": f"DMG-{uuid.uuid4().hex[:8].upper()}",
        "driver_id": driver_id,
        "trip_id": trip_id,
        "rider_id": trip["rider_id"],
        "description": description,
        "estimated_cost": estimated_cost,
        "status": "under_review",
        "review_days": 5,
    }
    _DAMAGE_CLAIMS.append(claim)
    return claim


# ---------------------------------------------------------------------------
# Shared tools
# ---------------------------------------------------------------------------

@tool
def create_support_ticket(user_id: str, user_type: str, issue_type: str, description: str) -> dict:
    """
    Create a support ticket for issues requiring follow-up.
    Args:
        user_id: rider_id or driver_id.
        user_type: "rider" or "driver".
        issue_type: Category (e.g. lost_item, billing, safety, account_access).
        description: Full description of the issue.
    """
    ticket = {
        "ticket_id": f"TKT-{uuid.uuid4().hex[:8].upper()}",
        "user_id": user_id,
        "user_type": user_type,
        "issue_type": issue_type,
        "description": description,
        "status": "open",
        "priority": "urgent" if "safety" in issue_type.lower() else "normal",
    }
    _TICKETS.append(ticket)
    return ticket


@tool
def escalate_to_human(user_id: str, reason: str, priority: str = "normal") -> dict:
    """
    Escalate the conversation to a human support agent.
    Args:
        user_id: rider_id or driver_id.
        reason: Why escalation is needed.
        priority: "normal" or "urgent" (for safety issues).
    """
    return {
        "escalation_id": f"ESC-{uuid.uuid4().hex[:8].upper()}",
        "user_id": user_id,
        "reason": reason,
        "priority": priority,
        "status": "queued",
        "estimated_wait_minutes": 3 if priority == "urgent" else 12,
    }


@tool
def send_notification(user_id: str, message: str, channel: str = "push") -> dict:
    """
    Send a notification to the user.
    Args:
        user_id: rider_id or driver_id.
        message: Notification message text.
        channel: "push", "email", or "sms".
    """
    return {
        "notification_id": f"NTF-{uuid.uuid4().hex[:8].upper()}",
        "user_id": user_id,
        "channel": channel,
        "status": "sent",
    }


@tool
def update_account(user_id: str, field: str, value: str) -> dict:
    """
    Update a field on a user account (e.g., email, phone, payment method).
    Args:
        user_id: rider_id or driver_id.
        field: Field name to update.
        value: New value.
    """
    return {"status": "updated", "user_id": user_id, "field": field, "value": value}


# ---------------------------------------------------------------------------
# Tool registry and test helpers
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    get_rider_info,
    get_trip_info,
    process_refund,
    get_driver_info,
    get_driver_earnings,
    submit_damage_claim,
    create_support_ticket,
    escalate_to_human,
    send_notification,
    update_account,
]

TOOL_REGISTRY = {t.name: t for t in ALL_TOOLS}


def get_refunds() -> list[dict]:
    return list(_REFUNDS)


def get_tickets() -> list[dict]:
    return list(_TICKETS)


def get_damage_claims() -> list[dict]:
    return list(_DAMAGE_CLAIMS)


def clear_state() -> None:
    _REFUNDS.clear()
    _TICKETS.clear()
    _DAMAGE_CLAIMS.clear()
