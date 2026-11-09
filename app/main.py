"""OrderDesk API: customer support tickets for a restaurant's online orders, stored as events."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import events as ev
from app.db import get_session, init_db
from app.triage import triage


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="OrderDesk", lifespan=lifespan)


class TicketIn(BaseModel):
    customer_message: str = Field(min_length=3, max_length=2000)
    order_id: str | None = None


class StatusIn(BaseModel):
    status: str


def load_or_404(session: Session, ticket_id: str) -> dict:
    state = ev.rebuild(ev.history(session, ticket_id))
    if state is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return state


@app.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, session: Session = Depends(get_session)):
    ticket_id = ev.new_ticket_id()
    ev.append(session, ticket_id, ev.TICKET_CREATED, body.model_dump())
    result = triage(body.customer_message)
    ev.append(session, ticket_id, ev.TICKET_TRIAGED, result)
    if result["urgency"] == "high":
        ev.append(session, ticket_id, ev.ESCALATED, {"reason": "high urgency"})
    return load_or_404(session, ticket_id)


@app.get("/tickets")
def list_tickets(status: str | None = None, session: Session = Depends(get_session)):
    tickets = [load_or_404(session, tid) for tid in ev.all_ticket_ids(session)]
    if status:
        tickets = [t for t in tickets if t["status"] == status]
    return tickets


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, session: Session = Depends(get_session)):
    return load_or_404(session, ticket_id)


@app.get("/tickets/{ticket_id}/history")
def get_history(ticket_id: str, session: Session = Depends(get_session)):
    load_or_404(session, ticket_id)
    return [
        {"type": e.type, "data": e.data, "at": e.created_at.isoformat()}
        for e in ev.history(session, ticket_id)
    ]


@app.post("/tickets/{ticket_id}/status")
def change_status(ticket_id: str, body: StatusIn, session: Session = Depends(get_session)):
    if body.status not in ev.VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(ev.VALID_STATUSES)}")
    current = load_or_404(session, ticket_id)
    if current["status"] == body.status:
        return current  # no-op: we don't record events for changes that didn't happen
    ev.append(session, ticket_id, ev.STATUS_CHANGED, {"status": body.status})
    return load_or_404(session, ticket_id)


@app.post("/tickets/{ticket_id}/escalate")
def escalate(ticket_id: str, session: Session = Depends(get_session)):
    current = load_or_404(session, ticket_id)
    if not current["needs_human"]:
        ev.append(session, ticket_id, ev.ESCALATED, {"reason": "manual"})
    return load_or_404(session, ticket_id)
