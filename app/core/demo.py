"""
Demo mode content for Dawn.
Provides sample data and a guided tour script.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

# Sample data for demo
SAMPLE_SUPPORT_TICKETS = {
    "columns": [
        "ticket_id",
        "created_at",
        "assigned_to",
        "resolved_by",
        "status",
        "priority",
        "category",
        "resolution_time_hours",
        "customer_name",
        "subject",
    ],
    "data": [
        [
            "TK-001",
            "2024-01-15 09:30",
            "Alex Chen",
            "Alex Chen",
            "Closed",
            "High",
            "Account",
            2.5,
            "Acme Corp",
            "Login not working",
        ],
        [
            "TK-002",
            "2024-01-15 10:15",
            "Priya Sharma",
            "Priya Sharma",
            "Closed",
            "Medium",
            "Billing",
            4.2,
            "Beta Inc",
            "Invoice discrepancy",
        ],
        [
            "TK-003",
            "2024-01-15 11:00",
            "Alex Chen",
            "Alex Chen",
            "Closed",
            "High",
            "Technical",
            1.8,
            "Gamma Ltd",
            "API timeout issue",
        ],
        [
            "TK-004",
            "2024-01-15 14:30",
            "Marcus Johnson",
            "Marcus Johnson",
            "Closed",
            "Low",
            "General",
            6.5,
            "Delta Co",
            "Feature request",
        ],
        [
            "TK-005",
            "2024-01-15 15:45",
            "Priya Sharma",
            "Priya Sharma",
            "Closed",
            "High",
            "Account",
            3.2,
            "Epsilon Corp",
            "Payment method declined",
        ],
        [
            "TK-006",
            "2024-01-16 08:00",
            "Alex Chen",
            "Alex Chen",
            "Closed",
            "Medium",
            "Technical",
            2.1,
            "Zeta Systems",
            "Dashboard loading slow",
        ],
        [
            "TK-007",
            "2024-01-16 09:30",
            "Sarah Williams",
            "Sarah Williams",
            "Closed",
            "High",
            "Billing",
            5.5,
            "Eta Industries",
            "Multiple charges",
        ],
        [
            "TK-008",
            "2024-01-16 11:00",
            "Marcus Johnson",
            "Marcus Johnson",
            "Closed",
            "Low",
            "General",
            7.2,
            "Theta Corp",
            "Documentation question",
        ],
        [
            "TK-009",
            "2024-01-16 13:15",
            "Priya Sharma",
            "Priya Sharma",
            "Closed",
            "High",
            "Account",
            2.8,
            "Iota Ltd",
            "2FA setup issue",
        ],
        [
            "TK-010",
            "2024-01-16 16:00",
            "Alex Chen",
            "Alex Chen",
            "Closed",
            "Medium",
            "Technical",
            3.5,
            "Kappa Inc",
            "Export data problem",
        ],
        [
            "TK-011",
            "2024-01-17 09:00",
            "Sarah Williams",
            "Sarah Williams",
            "Closed",
            "High",
            "Account",
            4.1,
            "Lambda Co",
            "Subscription cancellation",
        ],
        [
            "TK-012",
            "2024-01-17 10:30",
            "Priya Sharma",
            "Priya Sharma",
            "Closed",
            "Medium",
            "Billing",
            3.7,
            "Mu Systems",
            "Invoice customization",
        ],
    ],
}


def create_demo_dataframe() -> pd.DataFrame:
    df = pd.DataFrame(SAMPLE_SUPPORT_TICKETS["data"], columns=SAMPLE_SUPPORT_TICKETS["columns"])
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["resolution_time_hours"] = df["resolution_time_hours"].astype(float)
    return df


def get_demo_file_bytes() -> bytes:
    df = create_demo_dataframe()
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Tickets", index=False)
    output.seek(0)
    return output.getvalue()


def get_guided_tour_steps() -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "duration_seconds": 4,
            "title": "Instant upload",
            "description": "Bring your workbook into Dawn",
            "caption": "Drop in a spreadsheet. Dawn starts immediately.",
            "highlight_element": "[data-tile-expanded='upload']",
            "tile_id": "upload",
            "action": "auto-upload",
        },
        {
            "step": 2,
            "duration_seconds": 4,
            "title": "Fast preview",
            "description": "Preview rows, columns, and schema",
            "caption": "Instant shape, columns, and quality signals.",
            "highlight_element": "[data-tile-expanded='preview']",
            "tile_id": "preview",
            "action": "auto-preview",
        },
        {
            "step": 3,
            "duration_seconds": 5,
            "title": "Index + insights",
            "description": "Index the data and generate insights",
            "caption": "Auto-indexed. Insights ready to explore.",
            "highlight_element": "[data-tile-expanded='insight']",
            "tile_id": "insight",
            "action": "auto-index",
        },
        {
            "step": 4,
            "duration_seconds": 5,
            "title": "Ask in plain English",
            "description": "Ask a natural-language question",
            "caption": "Ask a question. Get a cited answer.",
            "highlight_element": "[data-tile-expanded='contextChat']",
            "tile_id": "contextChat",
            "action": "send-question",
            "question": "Who resolved the most tickets? Avg resolution time?",
            "demo_answer": "Alex Chen resolved the most tickets (5). Avg resolution time is ~2.6 hours.",
        },
        {
            "step": 5,
            "duration_seconds": 5,
            "title": "Agent swarm",
            "description": "Run multi-agent analysis",
            "caption": "Swarm analysis surfaces deeper signals.",
            "highlight_element": "[data-tile-expanded='agent']",
            "tile_id": "agent",
            "action": "trigger-agent",
        },
        {
            "step": 6,
            "duration_seconds": 4,
            "title": "Swarm telemetry",
            "description": "Watch the agent plan unfold",
            "caption": "Reports and recommendations appear fast.",
            "highlight_element": "[data-tile-expanded='agentOrbit']",
            "tile_id": "agentOrbit",
            "action": "wait",
        },
        {
            "step": 7,
            "duration_seconds": 3,
            "title": "Local + private",
            "description": "Everything stays on your machine",
            "caption": "Runs locally. Choose your LLM. Data stays private.",
            "highlight_element": "[data-demo-target='dawn-sidebar']",
            "tile_id": None,
            "action": "end",
        },
    ]
