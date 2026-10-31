import os
import random
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from database import get_menu, get_dish, update_stock


# =========================================================
# 1. CONFIGURATION
# =========================================================

load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    raise ValueError(
        "GROQ_API_KEY missing. Please add it to your .env file."
    )

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    temperature=0
)


# =========================================================
# 2. DATABASE MENU LOOKUP
# =========================================================

def find_dish(dish_name: str):
    """Find a dish in SQLite without case-sensitivity problems."""
    if not dish_name:
        return None

    dish_name = dish_name.strip().lower()

    for item in get_menu():
        # get_menu() returns: (id, dish_name, price, stock)
        if item[1].strip().lower() == dish_name:
            return item[1]

    return None


# =========================================================
# 3. LLM STRUCTURED OUTPUT
# =========================================================

class OrderIntent(BaseModel):
    intent: Literal[
        "order",
        "new_order",
        "accept_partial",
        "reject_partial",
        "cancel",
        "unrelated",
        "invalid_order",
    ] = Field(description="The intent of the user's message")

    dish_name: str = Field(
        default="",
        description="Name of the food item"
    )

    quantity: int = Field(
        default=0,
        description="Quantity requested by the customer"
    )


extractor = llm.with_structured_output(OrderIntent)


# =========================================================
# 4. LANGGRAPH STATE
# =========================================================

class RestaurantState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

    user_input: str

    dish_name: str
    required_quantity: int
    available_quantity: str

    status: str
    intent: str

    order_retry_attempts: int
    cook_retry_attempts: int
    serve_retry_attempts: int

    final_result: str

    # Optional deterministic test sequences.
    # Example: ["fail", "success"]
    test_cook_outcomes: list[str]
    test_serve_outcomes: list[str]


# =========================================================
# 5. HELPER FUNCTIONS
# =========================================================

def say(message: str):
    """Print a message and return it for LangGraph history."""
    print(message)
    return AIMessage(content=message)


def extract_order(state: RestaurantState) -> OrderIntent:
    """Extract intent, dish and quantity from user input."""

    current_status = state.get("status", "new")

    system_prompt = f"""
You are the intent extractor for a restaurant food-ordering agent.

This agent ONLY handles restaurant food orders.

Current order:
Dish: {state.get("dish_name", "")}
Required quantity: {state.get("required_quantity", 0)}
Available quantity: {state.get("available_quantity", "0")}
Current status: {current_status}

Classify the user's latest message:

1. order:
   A normal food order, such as "2 pizza" or "I want 3 burgers".

2. new_order:
   A new food order provided after the customer was asked about
   partial availability or after a previous order was unavailable.

3. accept_partial:
   The customer agrees to accept the available quantity.
   Examples: "yes", "okay", "I will take them".

4. reject_partial:
   The customer rejects the partial order.
   Examples: "no", "I don't want it", "give me something else".

5. cancel:
   The customer wants to cancel the order.

6. unrelated:
   The message is not related to restaurant food ordering.
   Examples: "Who is Narendra Modi?", "Tell me a joke".

7. invalid_order:
   The message appears to be a food order but does not contain
   a usable dish or positive quantity.

Rules:
- Never answer general knowledge questions.
- Do not invent a dish or quantity.
- For a new food order, extract the dish and quantity.
- If the customer accepts partial availability, use accept_partial.
- If the customer rejects partial availability, use reject_partial.
- If the user gives a different dish and quantity, use new_order.
- If the user cancels, use cancel.
"""

    return extractor.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["user_input"]),
    ])


# =========================================================
# 6. PARSE USER INPUT
# =========================================================

def parse_input(state: RestaurantState):

    try:
        result = extract_order(state)

    except Exception as error:
        print(f"\nCould not process the input: {error}")

        remaining = max(
            0,
            state["order_retry_attempts"] - 1
        )

        message = say(
            "I couldn't understand that input. "
            "Please enter a food order with a dish and quantity."
        )

        return {
            "intent": "invalid_order",
            "status": "invalid",
            "order_retry_attempts": remaining,
            "messages": [
                HumanMessage(content=state["user_input"]),
                message,
            ],
        }

    intent = result.intent

    updates = {
        "intent": intent,
        "messages": [
            HumanMessage(content=state["user_input"])
        ],
    }

    # -----------------------------------------------------
    # Unrelated question
    # -----------------------------------------------------

    if intent == "unrelated":

        remaining = max(
            0,
            state["order_retry_attempts"] - 1
        )

        updates["order_retry_attempts"] = remaining
        updates["status"] = "invalid"

        updates["messages"].append(
            say(
                "I can only help with restaurant food orders. "
                f"Attempts remaining: {remaining}"
            )
        )

        return updates

    # -----------------------------------------------------
    # Cancellation
    # -----------------------------------------------------

    if intent == "cancel":

        updates["status"] = "cancelled"
        updates["final_result"] = "cancelled"

        updates["messages"].append(
            say("Your order has been cancelled.")
        )

        return updates

    # -----------------------------------------------------
    # Accept partial availability
    # -----------------------------------------------------

    if intent == "accept_partial":

        available = int(state["available_quantity"])

        if available <= 0:

            updates["intent"] = "invalid_order"
            updates["status"] = "invalid"

            updates["messages"].append(
                say(
                    "This item is unavailable. "
                    "Please choose another dish."
                )
            )

            return updates

        updates["dish_name"] = state["dish_name"]
        updates["required_quantity"] = available
        updates["status"] = "confirmed"

        updates["messages"].append(
            say(
                f"Partial order accepted: {available} "
                f"{state['dish_name']}."
            )
        )

        return updates

    # -----------------------------------------------------
    # Reject partial availability
    # -----------------------------------------------------

    if intent == "reject_partial":

        updates["status"] = "rejected_partial"

        updates["messages"].append(
            say("No problem. Please enter another food order.")
        )

        return updates

    # -----------------------------------------------------
    # Invalid food order
    # -----------------------------------------------------

    if intent == "invalid_order":

        remaining = max(
            0,
            state["order_retry_attempts"] - 1
        )

        updates["order_retry_attempts"] = remaining
        updates["status"] = "invalid"

        updates["messages"].append(
            say(
                "Please provide a valid dish name and a positive "
                f"quantity. Attempts remaining: {remaining}"
            )
        )

        return updates

    # -----------------------------------------------------
    # Normal order / new order
    # -----------------------------------------------------

    if intent in ("order", "new_order"):

        remaining = max(
            0,
            state["order_retry_attempts"] - 1
        )

        updates["order_retry_attempts"] = remaining

        if not result.dish_name.strip() or result.quantity <= 0:

            updates["intent"] = "invalid_order"
            updates["status"] = "invalid"

            updates["messages"].append(
                say(
                    "Please enter a valid dish and a positive quantity."
                )
            )

            return updates

        updates["dish_name"] = result.dish_name.strip().lower()
        updates["required_quantity"] = result.quantity
        updates["status"] = "new"

        return updates

    return updates


# =========================================================
# 7. CHECK MENU AND INVENTORY
# =========================================================

def order_confirm(state: RestaurantState):

    dish_name = state["dish_name"]
    required = state["required_quantity"]

    menu_dish = find_dish(dish_name)

    # Dish does not exist.
    if menu_dish is None:

        message = say(
            f"Sorry, {dish_name} is not available on our menu."
        )

        return {
            "available_quantity": "0",
            "status": "not_available",
            "messages": [message],
        }

    # Always read the latest price and stock from SQLite.
    dish = get_dish(menu_dish)

    if dish is None:
        message = say(
            f"Sorry, {dish_name} is not available on our menu."
        )
        return {
            "available_quantity": "0",
            "status": "not_available",
            "messages": [message],
        }

    menu_dish, price, available = dish

    # No stock.
    if available == 0:

        message = say(
            f"Sorry, {menu_dish} is currently out of stock."
        )

        return {
            "dish_name": menu_dish,
            "available_quantity": "0",
            "status": "not_available",
            "messages": [message],
        }

    # Full quantity available.
    if available >= required:

        total = required * price

        message = say(
            f"Order confirmed: {required} {menu_dish}. "
            f"Total price: Rs. {total}."
        )

        return {
            "dish_name": menu_dish,
            "available_quantity": str(available),
            "status": "confirmed",
            "messages": [message],
        }

    # Only a partial quantity is available.
    total = available * price

    message = say(
        f"You requested {required} {menu_dish}, but only "
        f"{available} are available. "
        f"Would you like to accept {available} for Rs. {total}? "
        "Please answer yes or no."
    )

    return {
        "dish_name": menu_dish,
        "available_quantity": str(available),
        "status": "partial",
        "messages": [message],
    }


# =========================================================
# 8. ASK CUSTOMER
# =========================================================

def ask_customer(state: RestaurantState):

    user_input = input("Your choice: ").strip()

    return {
        "user_input": user_input
    }


# =========================================================
# 9. GET A NEW ORDER
# =========================================================

def get_order_input(state: RestaurantState):

    user_input = input(
        "\nPlease enter a food order (dish and quantity): "
    ).strip()

    return {
        "user_input": user_input
    }


# =========================================================
# 10. COOK ORDER
# =========================================================

def cook(state: RestaurantState):

    test_outcomes = state.get("test_cook_outcomes", [])

    if test_outcomes:
        outcome = test_outcomes[0].lower()

        remaining_outcomes = test_outcomes[1:]

    else:
        outcome = (
            "success" if random.random() < 0.60 else "fail"
        )

        remaining_outcomes = []

    if outcome in ("success", "succeed"):
        message = say(
            f"Cooking successful! Your {state['dish_name']} "
            "is ready."
        )

        return {
            "status": "ready",
            "test_cook_outcomes": remaining_outcomes,
            "messages": [message],
        }

    message = say(
        f"Cooking failed for {state['dish_name']}."
    )

    return {
        "status": "cook_failed",
        "test_cook_outcomes": remaining_outcomes,
        "messages": [message],
    }


# =========================================================
# 11. DECREMENT COOK RETRY COUNTER
# =========================================================

def retry_cook(state: RestaurantState):

    remaining = max(
        0,
        state["cook_retry_attempts"] - 1
    )

    message = say(
        f"Retrying cooking. Retries remaining after this attempt: "
        f"{remaining}."
    )

    return {
        "cook_retry_attempts": remaining,
        "messages": [message],
    }


# =========================================================
# 12. SERVE ORDER
# =========================================================

def serve(state: RestaurantState):

    test_outcomes = state.get("test_serve_outcomes", [])

    if test_outcomes:
        outcome = test_outcomes[0].lower()

        remaining_outcomes = test_outcomes[1:]

    else:
        outcome = (
            "success" if random.random() < 0.60 else "fail"
        )

        remaining_outcomes = []

    # Serving successful.
    if outcome in ("success", "succeed"):

        menu_dish = find_dish(state["dish_name"])

        # Update stock only after successful serving. The SQL update
        # also checks that enough stock remains, preventing negative stock.
        if menu_dish is None or not update_stock(
            menu_dish,
            state["required_quantity"]
        ):
            message = say(
                "Sorry, the stock changed while processing your order. "
                "We could not complete your order."
            )

            return {
                "status": "inventory_error",
                "final_result": "not_completed",
                "test_serve_outcomes": remaining_outcomes,
                "messages": [message],
            }

        message = say(
            f"Your order of {state['required_quantity']} "
            f"{state['dish_name']} has been served successfully!"
        )

        return {
            "status": "complete",
            "final_result": "completed",
            "test_serve_outcomes": remaining_outcomes,
            "messages": [message],
        }

    # Serving failed.
    remaining = max(
        0,
        state["serve_retry_attempts"] - 1
    )

    message = say(
        "Serving failed. "
        f"Serving retries remaining: {remaining}."
    )

    return {
        "status": "serve_failed",
        "serve_retry_attempts": remaining,
        "test_serve_outcomes": remaining_outcomes,
        "messages": [message],
    }


# =========================================================
# 13. APOLOGY / FAILURE NODE
# =========================================================

def apology(state: RestaurantState):

    message = say(
        "Sorry, we couldn't complete your order. "
        "Thank you for your patience."
    )

    return {
        "status": "failed",
        "final_result": "not_completed",
        "messages": [message],
    }


# =========================================================
# 14. ROUTING FUNCTIONS
# =========================================================

def route_after_parse(state: RestaurantState):

    intent = state["intent"]

    if intent == "cancel":
        return "end"

    if intent == "unrelated":

        if state["order_retry_attempts"] <= 0:
            return "apology"

        return "get_order_input"

    if intent == "invalid_order":

        if state["order_retry_attempts"] <= 0:
            return "apology"

        return "get_order_input"

    if intent == "reject_partial":

        if state["order_retry_attempts"] <= 0:
            return "apology"

        return "get_order_input"

    if intent == "accept_partial":

        if state["status"] == "confirmed":
            return "cook"

        return "get_order_input"

    if intent in ("order", "new_order"):
        return "order_confirm"

    return "get_order_input"


def route_after_order_confirm(state: RestaurantState):

    # A valid order can proceed even if this was the final attempt.
    if state["status"] == "confirmed":
        return "cook"

    if state["order_retry_attempts"] <= 0:
        return "apology"

    return "ask_customer"


def route_after_cook(state: RestaurantState):

    if state["status"] == "ready":
        return "serve"

    if state["cook_retry_attempts"] > 0:
        return "retry_cook"

    return "apology"


def route_after_serve(state: RestaurantState):

    if state["status"] == "complete":
        return "end"

    # Inventory changed unexpectedly; do not cook/serve the same order again.
    if state["status"] == "inventory_error":
        return "apology"

    # Serving failed. Another cooking attempt is allowed only
    # when BOTH serving and cooking retries remain.
    if (
        state["serve_retry_attempts"] > 0
        and state["cook_retry_attempts"] > 0
    ):
        return "retry_cook"

    return "apology"


# =========================================================
# 15. BUILD LANGGRAPH
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
        "apology": "apology",
        "get_order_input": "get_order_input",
        "cook": "cook",
        "order_confirm": "order_confirm",
    },
)

builder.add_conditional_edges(
    "order_confirm",
    route_after_order_confirm,
    {
        "cook": "cook",
        "ask_customer": "ask_customer",
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
# 16. RUN THE AGENT
# =========================================================

if __name__ == "__main__":

    print("Welcome! What would you like to order?")

    first_input = input().strip()

    initial_state: RestaurantState = {
        "messages": [],
        "user_input": first_input,

        "dish_name": "",
        "required_quantity": 0,
        "available_quantity": "0",

        "status": "new",
        "intent": "",

        "order_retry_attempts": 3,
        "cook_retry_attempts": 2,
        "serve_retry_attempts": 2,

        "final_result": "pending",

        # Empty lists mean cooking/serving outcomes are random.
        "test_cook_outcomes": [],
        "test_serve_outcomes": [],
    }

    result = graph.invoke(initial_state)

    print("\n========== FINAL RESULT ==========")
    print("Status:", result["status"])
    print("Final result:", result["final_result"])
    print("Order attempts remaining:", result["order_retry_attempts"])
    print("Cook retries remaining:", result["cook_retry_attempts"])
    print("Serve retries remaining:", result["serve_retry_attempts"])
    print("==================================")