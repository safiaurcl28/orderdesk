"""MCP server that lets an AI agent work with OrderDesk tickets.

Each tool calls the OrderDesk API over HTTP, so the agent only gets the actions
listed here, nothing more. Run the API first, then add this server to Claude Desktop
(see README).
"""
import os

import httpx
from mcp.server.mcpserver import MCPServer

API = os.getenv("ORDERDESK_API", "http://localhost:8000")
mcp = MCPServer("orderdesk")


@mcp.tool()
def list_open_tickets() -> list[dict]:
    """List all tickets that are still open."""
    return httpx.get(f"{API}/tickets", params={"status": "open"}).json()


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Get the current state of one ticket: customer message, order id, urgency, category, status."""
    return httpx.get(f"{API}/tickets/{ticket_id}").json()


@mcp.tool()
def get_ticket_history(ticket_id: str) -> list[dict]:
    """Get every event that happened to a ticket, oldest first."""
    return httpx.get(f"{API}/tickets/{ticket_id}/history").json()


@mcp.tool()
def update_status(ticket_id: str, status: str) -> dict:
    """Move a ticket to 'open', 'in_progress' or 'resolved'."""
    return httpx.post(f"{API}/tickets/{ticket_id}/status", json={"status": status}).json()


@mcp.tool()
def escalate_to_human(ticket_id: str) -> dict:
    """Hand a ticket to restaurant staff when you are not sure how to solve it."""
    return httpx.post(f"{API}/tickets/{ticket_id}/escalate").json()


if __name__ == "__main__":
    mcp.run()
