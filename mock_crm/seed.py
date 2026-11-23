from typing import Any

CUSTOMERS: tuple[dict[str, Any], ...] = (
    {"id": "C001", "name": "Aarav Patel", "email": "aarav@example.com", "phone": "+919876543210"},
    {"id": "C002", "name": "Maya Shah", "email": "maya@example.com", "phone": "+919876543211"},
)

BOOKINGS: tuple[dict[str, Any], ...] = (
    {
        "id": "B001",
        "customer_id": "C001",
        "route": "Ahmedabad to Mumbai",
        "departs_at": "2026-12-01T09:30:00+05:30",
        "seat": "12A",
        "amount": 1200.00,
        "status": "confirmed",
    },
    {
        "id": "B002",
        "customer_id": "C001",
        "route": "Mumbai to Pune",
        "departs_at": "2026-12-05T14:00:00+05:30",
        "seat": "4C",
        "amount": 650.00,
        "status": "confirmed",
    },
    {
        "id": "B003",
        "customer_id": "C002",
        "route": "Delhi to Jaipur",
        "departs_at": "2026-12-03T08:00:00+05:30",
        "seat": "8B",
        "amount": 900.00,
        "status": "confirmed",
    },
)
