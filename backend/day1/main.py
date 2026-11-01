
import re
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import get_menu
from rest_phase4 import extractor
from order_service import (
    preview_order,
    place_order,
    get_order_by_id,
    get_order_history,
    cancel_order,
)

app = FastAPI(title="Restaurant AI Agent API")

# Local development: allow Vite on localhost/127.0.0.1 ports.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://restaurant-ai-agent-nu.vercel.app/",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



class ChatRequest(BaseModel):
    customer_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


# Temporary in-memory session storage.
sessions: Dict[str, Dict[str, Any]] = {}


def get_session(session_id: str, customer_name: str):
    if session_id not in sessions:
        sessions[session_id] = {
            "customer_name": customer_name.strip(),
            "messages": [],
            "items": [],
            "status": "new",
            "order_id": 0,
        }

    session = sessions[session_id]

    if (
        session["customer_name"].casefold()
        != customer_name.strip().casefold()
    ):
        raise HTTPException(
            status_code=403,
            detail="This session belongs to another customer.",
        )

    return session


@app.get("/")
def home():
    return {"message": "Restaurant AI Agent API is running!"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agent-info")
def agent_info():
    return {"message": "Restaurant AI Agent API is connected!"}


@app.get("/menu")
def show_menu():
    try:
        items = get_menu()

        return [
            {
                "id": item[0],
                "dish_name": item[1],
                "price": item[2],
                "stock": item[3],
            }
            for item in items
        ]

    except Exception as error:
        print(f"Menu API error: {error}")

        raise HTTPException(
            status_code=500,
            detail="Unable to load the restaurant menu.",
        )


def understand_message(message: str, session: dict):
    try:
        menu_names = [
            item[1] for item in get_menu()
        ]
    except Exception as error:
        print(f"Menu retrieval error: {error}")
        raise RuntimeError("Unable to retrieve the menu.")

    prompt = f"""
You are the intent extractor for a restaurant ordering API.

Available menu:
{menu_names}

Current session status: {session['status']}
Pending items: {session['items']}

Classify the latest user message.

Possible intents:
order, new_order, confirm, reject, cancel,
track_order, order_history, unrelated, invalid_order.

Rules:
- Extract dish names and positive integer quantities.
- Use only actual menu names when possible.
- For tracking or cancellation, extract the numeric order ID.
- "Yes" during awaiting_confirmation means confirm.
- "No" during awaiting_confirmation means reject.
- "Cancel order 3" means cancel order ID 3.
- A plain "cancel" during awaiting_confirmation rejects
  the pending order.
- Do not invent order IDs.
- For unrelated messages, use unrelated.
"""

    return extractor.invoke([
        {"role": "system", "content": prompt},
        {"role": "user", "content": message},
    ])


def extract_order_id(message: str):
    patterns = [
        r"\border\s*(?:id|number|no\.?)\s*#?\s*(\d+)\b",
        r"\border\s*#\s*(\d+)\b",
        r"\b(?:track|tracking|cancel)\s+order\s+(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            return int(match.group(1))

    return None


@app.post("/chat")
def chat(request: ChatRequest):
    customer_name = request.customer_name.strip()
    message = request.message.strip()

    if not customer_name:
        raise HTTPException(
            status_code=422,
            detail="Customer name cannot be empty.",
        )

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Message cannot be empty.",
        )

    session = get_session(
        request.session_id,
        customer_name,
    )

    try:
        result = understand_message(message, session)
    except Exception as error:
        print(f"Intent extraction error: {error}")

        raise HTTPException(
            status_code=503,
            detail="Intent extraction service is unavailable. Please try again.",
        )

    intent = getattr(result, "intent", "unrelated")
    reply = ""

    # NEW ORDER
    if intent in ("order", "new_order"):
        items = []

        for item in (getattr(result, "items", None) or []):
            dish_name = (getattr(item, "dish_name", "") or "").strip()

            try:
                quantity = int(item.quantity)
            except (AttributeError, TypeError, ValueError):
                continue

            if dish_name and quantity > 0:
                items.append({
                    "dish_name": dish_name,
                    "quantity": quantity,
                })

        if not items:
            reply = (
                "Please specify a menu item and quantity. "
                "Example: 2 pizza."
            )
        else:
            try:
                preview = preview_order(items)

                if not preview["can_place_order"]:
                    unavailable = [
                        (
                            f"{item['dish_name']} "
                            f"(requested {item['quantity']}, "
                            f"available {item['stock_available']})"
                        )
                        for item in preview["items"]
                        if not item["in_stock"]
                    ]

                    reply = (
                        "Sorry, insufficient stock for: "
                        + ", ".join(unavailable)
                        + ". Please choose another order."
                    )

                    session["status"] = "new"
                    session["items"] = []

                else:
                    session["items"] = items
                    session["status"] = "awaiting_confirmation"

                    bill_lines = [
                        (
                            f"{item['quantity']} x "
                            f"{item['dish_name']} @ Rs. "
                            f"{item['unit_price']:.2f} = Rs. "
                            f"{item['line_total']:.2f}"
                        )
                        for item in preview["items"]
                    ]

                    reply = (
                        "Please review your order:\n"
                        + "\n".join(bill_lines)
                        + f"\nTotal bill: Rs. {preview['total_amount']:.2f}"
                        + "\nWould you like to confirm? Reply yes or no."
                    )

            except ValueError as error:
                reply = str(error)
                session["status"] = "new"
                session["items"] = []

            except Exception as error:
                print(f"Order preview error: {error}")
                reply = "Sorry, I couldn't prepare your order. Please try again."

    # CONFIRM ORDER
    elif intent == "confirm":
        if session["status"] != "awaiting_confirmation":
            reply = "There is no pending order to confirm."
        else:
            try:
                order = place_order(
                    customer_name=customer_name,
                    items=session["items"],
                )

                session["status"] = "complete"
                session["order_id"] = order["order_id"]

                item_summary = ", ".join(
                    f"{item['quantity']} x {item['dish_name']}"
                    for item in order["items"]
                )

                reply = (
                    f"Order #{order['order_id']} placed successfully!\n"
                    f"Items: {item_summary}\n"
                    f"Total: Rs. {order['total_amount']:.2f}\n"
                    "Thank you!"
                )

                session["items"] = []

            except Exception as error:
                print(f"Order placement error: {error}")
                reply = (
                    "Sorry, the order could not be placed. "
                    "Please check the available stock and try again."
                )

    # REJECT PENDING ORDER
    elif intent == "reject":
        session["items"] = []
        session["status"] = "cancelled"
        reply = "Okay, your pending order was not placed."

    # TRACK ORDER
    elif intent == "track_order":
        order_id = getattr(result, "order_id", None)

        if order_id is None:
            order_id = extract_order_id(message)

        if not order_id or order_id <= 0:
            reply = "Please provide a valid order ID, e.g. Track order 2."
        else:
            try:
                order = get_order_by_id(order_id)

                if (
                    order is None
                    or order["customer_name"].strip().casefold()
                    != customer_name.casefold()
                ):
                    reply = (
                        f"I couldn't find order #{order_id} "
                        f"for {customer_name}."
                    )
                else:
                    item_lines = [
                        (
                            f"{item['quantity']} x {item['dish_name']} "
                            f"= Rs. {item['line_total']:.2f}"
                        )
                        for item in order["items"]
                    ]

                    reply = (
                        f"Order #{order['order_id']}\n"
                        f"Status: {order['status']}\n"
                        f"Items: {', '.join(item_lines)}\n"
                        f"Total: Rs. {order['total_amount']:.2f}\n"
                        f"Placed at: {order['created_at']}"
                    )

            except Exception as error:
                print(f"Order tracking error: {error}")
                reply = "Sorry, I couldn't retrieve the order details. Please try again."

    # CANCEL ORDER
    elif intent == "cancel":
        order_id = getattr(result, "order_id", None)

        if order_id is None:
            order_id = extract_order_id(message)

        if (
            order_id is None
            and session["status"] == "awaiting_confirmation"
        ):
            session["items"] = []
            session["status"] = "cancelled"
            reply = "Okay, your pending order was not placed."

        elif not order_id or order_id <= 0:
            reply = "Please provide an order ID, e.g. Cancel order 2."

        else:
            try:
                order = cancel_order(
                    order_id=order_id,
                    customer_name=customer_name,
                )

                session["status"] = "cancelled"

                reply = (
                    f"Order #{order['order_id']} cancelled successfully. "
                    "The item stock has been restored."
                )

            except ValueError as error:
                reply = str(error)

            except Exception as error:
                print(f"Cancellation error: {error}")
                reply = "Sorry, the cancellation could not be completed. Please try again."

    # ORDER HISTORY
    elif intent == "order_history":
        try:
            orders = get_order_history(limit=1000)

            customer_orders = [
                order
                for order in orders
                if order["customer_name"].strip().casefold()
                == customer_name.casefold()
            ]

            if not customer_orders:
                reply = f"No previous orders found for {customer_name}."
            else:
                lines = []

                for order in customer_orders:
                    items_text = ", ".join(
                        f"{item['quantity']} x {item['dish_name']}"
                        for item in order["items"]
                    )

                    lines.append(
                        f"Order #{order['order_id']} | "
                        f"{order['status']} | "
                        f"Rs. {order['total_amount']:.2f} | "
                        f"{items_text}"
                    )

                reply = (
                    f"Order history for {customer_name}:\n"
                    + "\n".join(lines)
                )

        except Exception as error:
            print(f"Order history error: {error}")
            reply = "Sorry, I couldn't retrieve your order history. Please try again."

    # UNRELATED / UNKNOWN INTENT
    else:
        reply = (
            "Hi! I can help you place food orders, check the menu, "
            "track orders, cancel orders, or view order history."
        )

    session["messages"].append({
        "user": message,
        "assistant": reply,
    })
    session["messages"] = session["messages"][-20:]

    return {
        "customer_name": customer_name,
        "reply": reply,
        "status": session["status"],
        "session_id": request.session_id,
    }
