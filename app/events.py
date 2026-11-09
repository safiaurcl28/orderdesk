"""Event sourcing core: append events, and rebuild ticket state from them."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Event

# Event types
TICKET_CREATED = "TicketCreated"
TICKET_TRIAGED = "TicketTriaged"
STATUS_CHANGED = "StatusChanged"
ESCALATED = "EscalatedToHuman"

VALID_STATUSES = {"open", "in_progress", "resolved"}


def new_ticket_id() -> str:
    return str(uuid.uuid4())


def append(session: Session, ticket_id: str, event_type: str, data: dict) -> Event:
    event = Event(ticket_id=ticket_id, type=event_type, data=data)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def history(session: Session, ticket_id: str) -> list[Event]:
    stmt = select(Event).where(Event.ticket_id == ticket_id).order_by(Event.id)
    return list(session.scalars(stmt))


def apply(state: dict, event: Event) -> dict:
    """Apply one event to the current state. This is the heart of event sourcing."""
    if event.type == TICKET_CREATED:
        return {
            "id": event.ticket_id,
            "customer_message": event.data["customer_message"],
            "order_id": event.data.get("order_id"),
            "status": "open",
            "urgency": None,
            "category": None,
            "needs_human": False,
            "created_at": event.created_at.isoformat(),
        }
    if event.type == TICKET_TRIAGED:
        return {**state, "urgency": event.data["urgency"], "category": event.data["category"]}
    if event.type == STATUS_CHANGED:
        return {**state, "status": event.data["status"]}
    if event.type == ESCALATED:
        return {**state, "needs_human": True}
    return state  # unknown events are ignored, so old code can read newer histories


def rebuild(events: list[Event]) -> dict | None:
    state: dict | None = None
    for event in events:
        state = apply(state or {}, event)
    return state


def all_ticket_ids(session: Session) -> list[str]:
    stmt = select(Event.ticket_id).where(Event.type == TICKET_CREATED).order_by(Event.id)
    return list(session.scalars(stmt))
