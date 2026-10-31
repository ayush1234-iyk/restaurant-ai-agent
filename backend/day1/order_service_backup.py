"""
Phase 2: Restaurant AI Agent — order management service.

SAFE DESIGN:
- Uses the existing restaurant.db and existing menu_items table.
- Does NOT drop, recreate, rename, or seed menu_items.
- Does NOT reset existing stock values.
- Creates only customers, orders, and order_items tables.
- Re-checks stock and prices inside a single SQLite transaction when placing an order.

Expected existing menu_items columns:
    id, dish_name, price, stock
Additional columns such as category/description are fine.
"""

from pathlib import Path
import sqlite3
from typing import Iterable, Mapping, Any

DB_PATH = Path(__file__).with_name("restaurant.db")


def get_connection() -> sqlite3.Connection:
    """Open a connection with foreign-key enforcement enabled."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_order_tables() -> None:
    """
    Add Phase 2 tables if they do not exist.
    Safe to run repeatedly; existing menu items and stock are untouched.
    """
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                phone TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'CONFIRMED'
                    CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
                total_amount REAL NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                dish_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price REAL NOT NULL CHECK (unit_price >= 0),
                line_total REAL NOT NULL CHECK (line_total >= 0),
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
            );

            CREATE INDEX IF NOT EXISTS idx_orders_customer_created
                ON orders(customer_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_order_items_order
                ON order_items(order_id);
            """
        )


def _normalize_items(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """
    Accepts e.g. [{"dish_name": "Pizza", "quantity": 2}, ...].
    Duplicate dishes are combined case-insensitively.
    """
    combined: dict[str, dict[str, Any]] = {}

    for item in items:
        name = str(item.get("dish_name", "")).strip()
        quantity = item.get("quantity")

        if not name:
            raise ValueError("Every item must include a dish_name.")

        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(
                f"Quantity for '{name}' must be a positive whole number."
            )

        key = name.casefold()

        if key not in combined:
            combined[key] = {
                "dish_name": name,
                "quantity": quantity
            }
        else:
            combined[key]["quantity"] += quantity

    if not combined:
        raise ValueError("Order must contain at least one item.")

    return list(combined.values())
