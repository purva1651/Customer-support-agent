"""Shared low-level helpers for agent action and response nodes."""

import asyncio
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.agent.router import ActionSelection


async def _invoke_tool(
    tool: Any, arguments: dict[str, Any], timeout_seconds: float, retries: int
) -> tuple[Any, int]:
    attempts = 0
    while True:
        attempts += 1
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.invoke, arguments), timeout=timeout_seconds
            )
            return result, attempts
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500 or attempts > retries:
                raise
        except TimeoutError:
            if attempts > retries:
                raise
        except Exception:
            if attempts > retries:
                raise


def _message_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content.strip()
    return json.dumps(content, ensure_ascii=False, default=str)


def _fallback_booking_selection(
    message: str, tools: Mapping[str, Any]
) -> ActionSelection | None:
    booking_match = re.search(r"\b(B\d+)\b", message, flags=re.IGNORECASE)
    if booking_match is None:
        return None
    booking_id = booking_match.group(1).upper()
    if re.search(r"\b(cancel|cancellation|cancelling|canceling)\b", message, re.I):
        if "cancel_booking" in tools:
            return ActionSelection(
                tool_name="cancel_booking", arguments={"booking_id": booking_id}
            )
    if re.search(r"\b(check|look\s*up|lookup|status|track|find)\b", message, re.I):
        if "get_booking_status" in tools:
            return ActionSelection(
                tool_name="get_booking_status", arguments={"booking_id": booking_id}
            )
    return None


def _has_explicit_refund_request(message: str) -> bool:
    if not re.search(r"\bB\d+\b", message, flags=re.IGNORECASE):
        return False
    if not re.search(r"\brefund\b", message, flags=re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"\b(request|submit|file|raise|open|make|ask|want|need)\b|"
            r"\bplease\s+refund\b",
            message,
            flags=re.IGNORECASE,
        )
    )


def _fallback_refund_request_selection(
    message: str, tools: Mapping[str, Any]
) -> ActionSelection | None:
    if "request_refund" not in tools or not _has_explicit_refund_request(message):
        return None
    booking_match = re.search(r"\b(B\d+)\b", message, flags=re.IGNORECASE)
    if booking_match is None:
        return None
    reason_match = re.search(r"\b(?:because|reason is|since)\b\s*(.+)$", message, re.I)
    reason = reason_match.group(1).strip() if reason_match else message.strip()
    return ActionSelection(
        tool_name="request_refund",
        arguments={"booking_id": booking_match.group(1).upper(), "reason": reason},
    )


def _format_tool_result(value: Any, tool_name: str | None = None) -> str:
    if tool_name == "get_booking_status" and isinstance(value, dict):
        booking_id = value.get("id", value.get("booking_id", "the booking"))
        status = str(value.get("status", "unknown")).replace("_", " ")
        lines = [f"Booking {booking_id} is {status}."]
        if route := value.get("route"):
            lines.append(f"Route: {route}.")
        if departure := value.get("departs_at"):
            try:
                departure_time = datetime.fromisoformat(str(departure))
                formatted_time = departure_time.strftime("%B %d, %Y at %I:%M %p")
                formatted_time = formatted_time.replace(" 0", " ")
                offset = departure_time.utcoffset()
                timezone = (
                    "IST"
                    if offset == timedelta(hours=5, minutes=30)
                    else departure_time.strftime("UTC%z")
                )
                lines.append(f"Departure: {formatted_time} {timezone}.")
            except ValueError:
                lines.append(f"Departure: {departure}.")
        if seat := value.get("seat"):
            lines.append(f"Seat: {seat}.")
        if amount := value.get("amount"):
            lines.append(f"Amount: ₹{float(amount):,.2f}.")
        return "\n".join(lines)
    if tool_name == "cancel_booking" and isinstance(value, dict):
        booking = value.get("booking", {})
        booking_id = booking.get("id", booking.get("booking_id", "the booking"))
        fee = value.get("fee")
        refund = value.get("refund_amount")
        return (
            f"Booking {booking_id} has been cancelled. "
            f"Cancellation fee: ₹{float(fee):,.2f}. "
            f"Refund: ₹{float(refund):,.2f}."
        )
    if tool_name == "request_refund" and isinstance(value, dict):
        request_id = value.get("request_id", "the refund request")
        booking_id = value.get("booking_id", "the booking")
        if value.get("already_pending"):
            return (
                f"Refund request {request_id} for booking {booking_id} is already pending. "
                "No second request was created, and no refund has been issued or approved."
            )
        return (
            f"Refund request {request_id} for booking {booking_id} was recorded as pending. "
            "This records a request only; no refund has been issued or approved."
        )
    if tool_name == "update_contact" and isinstance(value, dict):
        return "Your customer contact details were updated."
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)
