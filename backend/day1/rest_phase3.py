import os
import random
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from database import get_menu
from order_service import preview_order, place_order


# =========================================================
# 1. CONFIGURATION
# =========================================================

load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    raise ValueError("GROQ_API_KEY missing. Please add it to your .env file.")

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    temperature=0,
)


# =========================================================
# 2. STRUCTURED OUTPUT
# =========================================================

class OrderLine(BaseModel):
    dish_name: str = Field(description="Exact or closest dish name from the customer's request")
    quantity: int = Field(description="Positive whole-number quantity")


class OrderIntent(BaseModel):
    intent: Literal[
        "order",
        "new_order",
        "confirm",
        "reject",
        "cancel",
        "unrelated",
        "invalid_order",
    ] = Field(description="Intent of the customer's latest message")
    items: list[OrderLine] = Field(
        default_factory=list,
        description="Every dish and quantity in a new order. Empty for yes/no/cancel/unrelated.",
    )


extractor = llm.with_structured_output(OrderIntent)


# =========================================================
# 3. LANGGRAPH STATE
# =========================================================

class RestaurantState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_input: str
    customer_name: str
    items: list[dict]
    status: str
    intent: str
    order_retry_attempts: int
    cook_retry_attempts: int
    serve_retry_attempts: int
    test_cook_outcomes: list[str]
    test_serve_outcomes: list[str]
    final_result: str
    order_id: int


# =========================================================
# 4. HELPERS
# =========================================================

def say(message: str):
    print(message)
    return AIMessage(content=message)


def get_valid_menu_names() -> list[str]:
    return [row[1] for row in get_menu()]


# =========================================================
# 5. PARSE CUSTOMER MESSAGE
# =========================================================

def parse_input(state: RestaurantState):
    menu_names = get_valid_menu_names()
    prompt = f"""
You are an intent extractor for a restaurant ordering agent.
Available menu item names include:
{menu_names}

Current status: {state.get('status', 'new')}

Classify the user's latest message:
- order: customer gives a food order with one or more dishes.
- new_order: customer gives a different/new food order.
- confirm: customer clearly agrees to the pending order, e.g. yes, confirm, okay.
- reject: customer declines the pending order, e.g. no, don't place it.
- cancel: customer wants to cancel.
- unrelated: not about ordering food.
- invalid_order: ordering intent is present but no usable dish/positive quantity.

Rules:
- For an order, extract EVERY dish and its quantity.
- Use menu names when a close match exists; do not invent menu items.
- For confirm/reject/cancel/unrelated, items should be empty.
- A quantity must be a positive whole number.
- Current pending items: {state.get('items', [])}
- If status is awaiting_confirmation and the user says yes, classify as confirm.
- If status is awaiting_confirmation and the user says no, classify as reject.
Return only the structured fields.
"""
    try:
        result = extractor.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["user_input"]),
        ])
    except Exception as error:
        print(f"Could not process the input: {error}")
        remaining = max(0, state["order_retry_attempts"] - 1)
        msg = say("I couldn't understand that. Please enter a dish and quantity, e.g. '2 pizza and 1 burger'.")
        return {
            "intent": "invalid_order",
            "status": "invalid",
            "order_retry_attempts": remaining,
            "messages": [HumanMessage(content=state["user_input"]), msg],
        }

    updates = {
        "intent": result.intent,
        "messages": [HumanMessage(content=state["user_input"])],
    }

    if result.intent in ("order", "new_order"):
        valid_items = []
        if not result.items:
            result_items = []
        else:
            result_items = result.items

        for item in result_items:
            name = item.dish_name.strip()
            if not name or item.quantity <= 0:
                continue
            valid_items.append({"dish_name": name, "quantity": item.quantity})

        if not valid_items:
            remaining = max(0, state["order_retry_attempts"] - 1)
            updates.update({
                "intent": "invalid_order",
                "status": "invalid",
                "order_retry_attempts": remaining,
            })
            updates["messages"].append(
                say(f"Please include a menu item and positive quantity. Attempts remaining: {remaining}.")
            )
            return updates

        updates.update({
            "items": valid_items,
            "status": "new",
            "order_retry_attempts": max(0, state["order_retry_attempts"] - 1),
        })
        return updates

    if result.intent == "confirm":
        if state.get("status") == "awaiting_confirmation":
            updates["status"] = "customer_confirmed"
        else:
            updates["status"] = "invalid"
            updates["messages"].append(say("There is no pending order to confirm. Please enter your order first."))
        return updates

    if result.intent in ("reject", "cancel"):
        updates["status"] = "cancelled"
        updates["final_result"] = "cancelled"
        updates["messages"].append(say("Okay, the order was not placed."))
        return updates

    if result.intent == "unrelated":
        remaining = max(0, state["order_retry_attempts"] - 1)
        updates.update({"status": "invalid", "order_retry_attempts": remaining})
        updates["messages"].append(
            say(f"I can only help with restaurant food orders. Attempts remaining: {remaining}.")
        )
        return updates

    remaining = max(0, state["order_retry_attempts"] - 1)
    updates.update({"status": "invalid", "order_retry_attempts": remaining})
    updates["messages"].append(
        say(f"Please enter a valid food order. Attempts remaining: {remaining}.")
    )
    return updates


# =========================================================
# 6. CHECK STOCK AND SHOW BILL
# =========================================================

def order_confirm(state: RestaurantState):
    try:
        preview = preview_order(state["items"])
    except ValueError as error:
        msg = say(str(error) + " Please enter a different order.")
        return {
            "status": "unavailable",
            "messages": [msg],
        }

    lines = preview["items"]
    if not preview["can_place_order"]:
        unavailable = [
            f"{line['dish_name']} (requested {line['quantity']}, available {line['stock_available']})"
            for line in lines if not line["in_stock"]
        ]
        msg = say(
            "Sorry, we don't have enough stock for: "
            + ", ".join(unavailable)
            + ". No order has been placed. Please choose another order."
        )
        return {"status": "unavailable", "messages": [msg]}

    bill_lines = [
        f"  {line['quantity']} x {line['dish_name']} @ Rs. {line['unit_price']:.2f}"
        f" = Rs. {line['line_total']:.2f}"
        for line in lines
    ]
    message = (
        "Please review your order:\n"
        + "\n".join(bill_lines)
        + f"\nTotal bill: Rs. {preview['total_amount']:.2f}\n"
        + "Would you like me to place this order? Please answer yes or no."
    )
    return {
        "status": "awaiting_confirmation",
        "messages": [say(message)],
    }


def ask_customer(state: RestaurantState):
    return {"user_input": input("Your choice: ").strip()}


def get_order_input(state: RestaurantState):
    return {
        "user_input": input("\nPlease enter a food order (e.g. 2 pizza and 1 burger): ").strip()
    }


# =========================================================
# 7. COOK ORDER (existing demo behavior retained)
# =========================================================

def cook(state: RestaurantState):
    outcomes = state.get("test_cook_outcomes", [])
    if outcomes:
        outcome = outcomes[0].lower()
        remaining_outcomes = outcomes[1:]
    else:
        outcome = "success" if random.random() < 0.60 else "fail"
        remaining_outcomes = []

    if outcome in ("success", "succeed"):
        msg = say("Cooking successful! Your order is ready.")
        return {
            "status": "ready",
            "test_cook_outcomes": remaining_outcomes,
            "messages": [msg],
        }

    msg = say("Cooking failed for this order.")
    return {
        "status": "cook_failed",
        "test_cook_outcomes": remaining_outcomes,
        "messages": [msg],
    }


def retry_cook(state: RestaurantState):
    remaining = max(0, state["cook_retry_attempts"] - 1)
    msg = say(f"Retrying cooking. Retries remaining after this attempt: {remaining}.")
    return {"cook_retry_attempts": remaining, "messages": [msg]}


# =========================================================
# 8. SERVE AND SAVE ORDER
# =========================================================

def serve(state: RestaurantState):
    outcomes = state.get("test_serve_outcomes", [])
    if outcomes:
        outcome = outcomes[0].lower()
        remaining_outcomes = outcomes[1:]
    else:
        outcome = "success" if random.random() < 0.60 else "fail"
        remaining_outcomes = []

    if outcome not in ("success", "succeed"):
        remaining = max(0, state["serve_retry_attempts"] - 1)
        msg = say(f"Serving failed. Serving retries remaining: {remaining}.")
        return {
            "status": "serve_failed",
            "serve_retry_attempts": remaining,
            "test_serve_outcomes": remaining_outcomes,
            "messages": [msg],
        }

    try:
        # place_order rechecks current stock and updates stock in one transaction.
        # Do NOT call database.update_stock here as well, or stock would be deducted twice.
        order = place_order(
            customer_name=state["customer_name"],
            items=state["items"],
        )
    except (ValueError, Exception) as error:
        msg = say(f"Sorry, we couldn't complete the order: {error}")
        return {
            "status": "inventory_error",
            "final_result": "not_completed",
            "test_serve_outcomes": remaining_outcomes,
            "messages": [msg],
        }

    item_summary = ", ".join(
        f"{item['quantity']} x {item['dish_name']}" for item in order["items"]
    )
    msg = say(
        f"Order #{order['order_id']} placed successfully!\n"
        f"Items: {item_summary}\n"
        f"Total bill: Rs. {order['total_amount']:.2f}\n"
        "Thank you!"
    )
    return {
        "status": "complete",
        "final_result": "completed",
        "order_id": order["order_id"],
        "test_serve_outcomes": remaining_outcomes,
        "messages": [msg],
    }


def apology(state: RestaurantState):
    msg = say("Sorry, we couldn't complete your order. Thank you for your patience.")
    return {"status": "failed", "final_result": "not_completed", "messages": [msg]}


# =========================================================
# 9. ROUTING
# =========================================================

def route_after_parse(state: RestaurantState):
    if state["status"] == "cancelled":
        return "end"
    if state["intent"] in ("order", "new_order"):
        return "order_confirm"
    if state["status"] == "customer_confirmed":
        return "cook"
    if state["order_retry_attempts"] <= 0:
        return "apology"
    return "get_order_input"


def route_after_order_confirm(state: RestaurantState):
    if state["status"] == "awaiting_confirmation":
        return "ask_customer"
    if state["order_retry_attempts"] <= 0:
        return "apology"
    return "get_order_input"


def route_after_cook(state: RestaurantState):
    if state["status"] == "ready":
        return "serve"
    if state["cook_retry_attempts"] > 0:
        return "retry_cook"
    return "apology"


def route_after_serve(state: RestaurantState):
    if state["status"] == "complete":
        return "end"
    if state["status"] == "inventory_error":
        return "apology"
    if state["serve_retry_attempts"] > 0 and state["cook_retry_attempts"] > 0:
        return "retry_cook"
    return "apology"


# =========================================================
# 10. BUILD GRAPH
# =========================================================

builder = StateGraph(RestaurantState)

builder.add_node("parse_input", parse_input)
builder.add_node("order_confirm", order_confirm)
builder.add_node("ask_customer", ask_customer)
builder.add_node("get_order_input", get_order_input)
builder.add_node("cook", cook)
builder.add_node("retry_cook", retry_cook)
builder.add_node("serve", serve)
builder.add_node("apology", apology)

builder.add_edge(START, "parse_input")

builder.add_conditional_edges(
    "parse_input",
    route_after_parse,
    {
        "end": END,
        "order_confirm": "order_confirm",
        "cook": "cook",
        "get_order_input": "get_order_input",
        "apology": "apology",
    },
)

builder.add_conditional_edges(
    "order_confirm",
    route_after_order_confirm,
    {
        "ask_customer": "ask_customer",
        "get_order_input": "get_order_input",
        "apology": "apology",
    },
)

builder.add_edge("ask_customer", "parse_input")
builder.add_edge("get_order_input", "parse_input")

builder.add_conditional_edges(
    "cook",
    route_after_cook,
    {
        "serve": "serve",
        "retry_cook": "retry_cook",
        "apology": "apology",
    },
)
builder.add_edge("retry_cook", "cook")

builder.add_conditional_edges(
    "serve",
    route_after_serve,
    {
        "end": END,
        "retry_cook": "retry_cook",
        "apology": "apology",
    },
)
builder.add_edge("apology", END)

graph = builder.compile()


# =========================================================
# 11. RUN AGENT
# =========================================================

if __name__ == "__main__":
    print("Welcome to the Restaurant AI Agent!")
    customer_name = input("Please enter your name: ").strip() or "Walk-in Customer"
    first_input = input("What would you like to order? ").strip()

    initial_state: RestaurantState = {
        "messages": [],
        "user_input": first_input,
        "customer_name": customer_name,
        "items": [],
        "status": "new",
        "intent": "",
        "order_retry_attempts": 3,
        "cook_retry_attempts": 2,
        "serve_retry_attempts": 2,
        "test_cook_outcomes": [],
        "test_serve_outcomes": [],
        "final_result": "pending",
        "order_id": 0,
    }

    result = graph.invoke(initial_state)

    print("\n========== FINAL RESULT ==========")
    print("Status:", result["status"])
    print("Final result:", result["final_result"])
    if result.get("order_id"):
        print("Order ID:", result["order_id"])
    print("==================================")
