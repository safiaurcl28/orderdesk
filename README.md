# OrderDesk

A support backend for a restaurant's online orders, where an AI agent can help handle customer complaints without being trusted blindly.

A customer sends a message like "my order never arrived" or "I ordered vegan and there's cheese in it". OrderDesk saves it as a ticket, sorts it by urgency and category, and sends the urgent ones (allergens, orders that never showed up) straight to staff. Sorting is done by the Claude API, but every answer is checked, and if it's wrong the system falls back to simple rules. An **MCP server** lets an AI agent work with the tickets through a few safe actions, and an **n8n workflow** brings the messages in.

![OrderDesk API sorting a complaint](docs/screenshot.png)

## Why I built it

I worked at a restaurant that handled a lot of online orders, and complaints came in all the time, especially during busy shifts. A missing drink and an allergy problem landed in the same pile, and it was up to whoever had a free minute to sort them. I wanted to see how that could be handled better, with AI doing the sorting and a human stepping in when it matters.

I also wanted to learn how to give an AI agent access to a real system safely, and how to build a backend that keeps a full history of everything that happens. The same idea works for any support inbox, not just restaurants.

## How it works

```
customer msg ──> n8n webhook ──> POST /tickets ──> FastAPI ──> events table (PostgreSQL)
                                                        │
                                                        └── triage: Claude API ─(check)─> urgency + category
                                                                        └─ if invalid: keyword rules
AI agent (Claude Desktop) ──> MCP server ──> OrderDesk API (only the actions listed as tools)
```

## Choices I made

- **Every change is saved as an event (event sourcing).** Tickets are never overwritten. Created, sorted, escalated, status changed: each one is added to an `events` table, and the current ticket is rebuilt by replaying them in order. That way you can always see what happened and when, which matters once an AI agent is touching customer cases.
- **The AI's answer gets checked before it's used.** Claude has to reply with JSON using only the allowed values. A made-up value, chatty text or an API error means the keyword rules take over, so nothing breaks. Each ticket records whether the AI or the rules made the call.
- **Rules are ordered by how serious the problem is.** The first match wins, so "I got someone else's order and I'm allergic to nuts" is treated as an allergy issue, not just a wrong order.
- **The agent can only do five things.** It can list, read, update and escalate tickets, but it can't delete anything or touch the database.
- **Tests don't need the internet.** Without an API key the rules are used, so the tests run fast and give the same result every time, locally and in GitHub Actions.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/tickets` | Create a ticket from a customer message, sort it, escalate if urgent |
| GET | `/tickets?status=open` | List tickets, optionally by status |
| GET | `/tickets/{id}` | Current state of a ticket |
| GET | `/tickets/{id}/history` | Every event for that ticket, in order |
| POST | `/tickets/{id}/status` | Move to `open`, `in_progress` or `resolved` |
| POST | `/tickets/{id}/escalate` | Hand to a human |

Once it's running, you can try everything at `http://localhost:8000/docs`.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

This uses a local SQLite file by default. To use PostgreSQL instead:

```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://orderdesk:orderdesk@localhost:5432/orderdesk
```

To sort with Claude instead of the rules, set `ANTHROPIC_API_KEY`.

Tests: `pytest -v` (they also run in GitHub Actions on every push).

## MCP server (AI agent access)

With the API running, add this to Claude Desktop's config (`claude_desktop_config.json`):

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

Then ask Claude something like *"Which open tickets are urgent, and what happened on the latest one?"*

## n8n workflow

`docker compose up -d n8n`, open `http://localhost:5678`, and import `n8n/workflow.json`.

Webhook (customer message) → HTTP Request `POST /tickets` → IF `needs_human` is true → notify staff / else → automatic reply to the customer.

<!-- TODO: build this in n8n, then export it to n8n/workflow.json -->

## Agent procedure: "My order never arrived"

<!-- TODO: write ~10 if-then steps the agent follows, using the MCP tools. Example start:
1. Call get_ticket. If the order is more than 30 minutes past its delivery time, ...
-->

## What I'd add next

- A separate table with each ticket's current state, so listing tickets doesn't replay every event
- Recording *who* made each change (staff or AI agent)
- Letting one ticket have more than one category (an allergy *and* a late order)
- A set of realistic test messages to measure how accurate the sorting is