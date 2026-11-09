# OrderDesk

A customer support backend for a restaurant's online orders, built so that an AI agent can work with it safely.

Customers send a message ("my order never arrived", "I ordered vegan and there is cheese in it"). OrderDesk stores it, sorts it by urgency and category (with the Claude API, validated, with a rule-based fallback), and hands anything urgent (allergens, orders that never arrived) to restaurant staff. An **MCP server** exposes the tickets to an AI agent as a small set of tools, and an **n8n workflow** connects incoming messages to the API.

![screenshot](docs/screenshot.png) <!-- TODO: add a screenshot of /docs or Claude Desktop using the tools -->

## Why I built it

<!-- TODO: 2-3 sentences in your own words. E.g. at Don Burrito you processed online orders and saw complaints pile up during busy shifts, with no way to tell the urgent ones (allergens) from the small ones. What you wanted to learn: FastAPI, event sourcing, MCP, n8n. -->

## Architecture

```
customer msg ──> n8n webhook ──> POST /tickets ──> FastAPI ──> events table (PostgreSQL)
                                                        │
                                                        └── triage: Claude API ─(validate)─> urgency/category
                                                                        └─ fallback: rules
AI agent (Claude Desktop) ──> MCP server ──> OrderDesk API (only the actions listed as tools)
```

## Design choices

- **Event sourcing.** Tickets are never updated in place. Every change (`TicketCreated`, `TicketTriaged`, `StatusChanged`, `EscalatedToHuman`) is appended to an `events` table, and the current state is rebuilt by replaying them. This gives a full audit trail of what happened and when, which matters when an AI agent is acting on customer cases.
- **LLM output is never trusted blindly.** The model must return JSON with allowed values only. Anything else (wrong value, chatty text, API error) falls back to rules, so the system keeps working on a bad day.
- **No-op changes are not recorded.** Setting a status that is already set adds no event.
- **Scoped agent access.** The MCP server exposes five tools and nothing else. The agent cannot delete tickets or touch the database directly.
- **Tests do not depend on the network.** Without an API key, triage uses rules, so CI is fast and deterministic.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/tickets` | Create a ticket from a customer message, triage it, escalate if urgent |
| GET | `/tickets?status=open` | List tickets, optionally filtered by status |
| GET | `/tickets/{id}` | Current state of a ticket |
| GET | `/tickets/{id}/history` | Every event for that ticket, in order |
| POST | `/tickets/{id}/status` | Move to `open`, `in_progress` or `resolved` |
| POST | `/tickets/{id}/escalate` | Hand to a human |

Interactive docs at `http://localhost:8000/docs` once running.

## Run it

```bash
docker compose up -d db                    # PostgreSQL
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://orderdesk:orderdesk@localhost:5432/orderdesk
export ANTHROPIC_API_KEY=...               # optional; without it triage uses rules
uvicorn app.main:app --reload
```

Tests: `pytest -v` (runs on SQLite, also runs in GitHub Actions on every push).

## MCP server (AI agent access)

Add this to Claude Desktop's config (`claude_desktop_config.json`), with the API running:

```json
{
  "mcpServers": {
    "orderdesk": {
      "command": "/full/path/to/.venv/bin/python",
      "args": ["/full/path/to/orderdesk/mcp_server/server.py"]
    }
  }
}
```

Tools: `list_open_tickets`, `get_ticket`, `get_ticket_history`, `update_status`, `escalate_to_human`.

Then ask Claude: *"Which open tickets are urgent, and what happened on the latest one?"*

## n8n workflow

`docker compose up -d n8n`, open `http://localhost:5678`, and import `n8n/workflow.json`.

Webhook (customer message) → HTTP Request `POST /tickets` → IF `needs_human` is true → notify staff / else → automatic reply to the customer.

<!-- TODO: build this in n8n, then export it to n8n/workflow.json -->

## Agent procedure: "My order never arrived"

<!-- TODO: write ~10 if-then steps the agent follows, using the MCP tools. Example start:
1. Call get_ticket. If the order is more than 30 minutes past its delivery time, ...
-->

## Next steps

- A read model (projection) so listing tickets doesn't replay every event
- A real `get_order` lookup against order data (items, delivery time, allergens)
- Evaluation set of real-looking messages to measure triage accuracy
