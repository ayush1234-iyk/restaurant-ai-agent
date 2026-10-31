"""
Restaurant AI Agent order service.
Uses existing restaurant.db; never drops, seeds, or resets menu_items/stock.
"""
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping, Any

DB_PATH = Path(__file__).with_name("restaurant.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_order_tables() -> None:
    conn = get_connection()
    try:
        conn.executescript("""
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
                CHECK (status IN ('PENDING','CONFIRMED','CANCELLED')),
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
        CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
        """)
        conn.commit()
    finally:
        conn.close()


def _normalize_items(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for item in items:
        name = str(item.get("dish_name", "")).strip()
        quantity = item.get("quantity")
        if not name:
            raise ValueError("Every item must include a dish_name.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f"Quantity for '{name}' must be a positive whole number.")
        key = name.casefold()
        if key not in combined:
            combined[key] = {"dish_name": name, "quantity": quantity}
        else:
            combined[key]["quantity"] += quantity
    if not combined:
        raise ValueError("Order must contain at least one item.")
    return list(combined.values())


def _menu_item_by_name(conn: sqlite3.Connection, name: str):
    return conn.execute(
        "SELECT id, dish_name, price, stock FROM menu_items "
        "WHERE dish_name = ? COLLATE NOCASE LIMIT 1",
        (name.strip(),),
    ).fetchone()


def preview_order(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = _normalize_items(items)
    initialize_order_tables()
    conn = get_connection()
    try:
        lines, total, can_place = [], 0.0, True
        for requested in normalized:
            row = _menu_item_by_name(conn, requested["dish_name"])
            if row is None:
                raise ValueError(f"'{requested['dish_name']}' is not available on the menu.")
            qty, price, stock = requested["quantity"], float(row["price"]), int(row["stock"])
            in_stock = stock >= qty
            if not in_stock:
                can_place = False
            line_total = price * qty
            total += line_total
            lines.append({
                "menu_item_id": int(row["id"]), "dish_name": row["dish_name"],
                "quantity": qty, "unit_price": price, "line_total": line_total,
                "stock_available": stock, "in_stock": in_stock,
            })
        return {"can_place_order": can_place, "items": lines, "total_amount": total}
    finally:
        conn.close()


def place_order(customer_name: str, items: Iterable[Mapping[str, Any]],
                phone: str | None = None) -> dict[str, Any]:
    name = str(customer_name or "").strip()
    if not name:
        raise ValueError("Customer name is required.")
    normalized = _normalize_items(items)
    initialize_order_tables()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        customer = conn.execute(
            "SELECT id FROM customers WHERE customer_name = ? COLLATE NOCASE ORDER BY id LIMIT 1",
            (name,),
        ).fetchone()
        if customer is None:
            cur = conn.execute(
                "INSERT INTO customers (customer_name, phone) VALUES (?, ?)", (name, phone)
            )
            customer_id = int(cur.lastrowid)
        else:
            customer_id = int(customer["id"])
            if phone:
                conn.execute("UPDATE customers SET phone = ? WHERE id = ?", (phone, customer_id))

        checked, total = [], 0.0
        for requested in normalized:
            row = _menu_item_by_name(conn, requested["dish_name"])
            if row is None:
                raise ValueError(f"'{requested['dish_name']}' is not available on the menu.")
            qty, stock = requested["quantity"], int(row["stock"])
            if stock < qty:
                raise ValueError(
                    f"Not enough stock for {row['dish_name']}: requested {qty}, available {stock}."
                )
            price = float(row["price"])
            line_total = price * qty
            checked.append({
                "menu_item_id": int(row["id"]), "dish_name": row["dish_name"],
                "quantity": qty, "unit_price": price, "line_total": line_total,
            })
            total += line_total

        cur = conn.execute(
            "INSERT INTO orders (customer_id, status, total_amount) VALUES (?, 'CONFIRMED', ?)",
            (customer_id, total),
        )
        order_id = int(cur.lastrowid)
        for item in checked:
            cur = conn.execute(
                "UPDATE menu_items SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (item["quantity"], item["menu_item_id"], item["quantity"]),
            )
            if cur.rowcount != 1:
                raise ValueError(f"Stock changed for {item['dish_name']}; please try again.")
            conn.execute("""
                INSERT INTO order_items
                (order_id, menu_item_id, dish_name, quantity, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (order_id, item["menu_item_id"], item["dish_name"], item["quantity"],
                  item["unit_price"], item["line_total"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result = get_order_by_id(order_id)
    if result is None:
        raise RuntimeError("Order was saved but could not be retrieved.")
    return result


def _order_with_items(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    items = conn.execute("""
        SELECT menu_item_id, dish_name, quantity, unit_price, line_total
        FROM order_items WHERE order_id = ? ORDER BY id
    """, (row["id"],)).fetchall()
    return {
        "order_id": int(row["id"]), "customer_id": int(row["customer_id"]),
        "customer_name": row["customer_name"], "phone": row["phone"],
        "status": row["status"], "total_amount": float(row["total_amount"]),
        "created_at": row["created_at"],
        "items": [{
            "menu_item_id": int(i["menu_item_id"]), "dish_name": i["dish_name"],
            "quantity": int(i["quantity"]), "unit_price": float(i["unit_price"]),
            "line_total": float(i["line_total"]),
        } for i in items],
    }


def get_order_by_id(order_id: int) -> dict[str, Any] | None:
    initialize_order_tables()
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT o.id, o.customer_id, c.customer_name, c.phone,
                   o.status, o.total_amount, o.created_at
            FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE o.id = ?
        """, (int(order_id),)).fetchone()
        return None if row is None else _order_with_items(conn, row)
    finally:
        conn.close()


def get_order_history(limit: int = 20) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer.")
    initialize_order_tables()
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT o.id, o.customer_id, c.customer_name, c.phone,
                   o.status, o.total_amount, o.created_at
            FROM orders o JOIN customers c ON c.id = o.customer_id
            ORDER BY o.id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [_order_with_items(conn, row) for row in rows]
    finally:
        conn.close()


def cancel_order(order_id: int, customer_name: str) -> dict[str, Any]:
    name = str(customer_name or "").strip()
    if not name:
        raise ValueError("Customer name is required.")
    if isinstance(order_id, bool) or int(order_id) <= 0:
        raise ValueError("A valid order ID is required.")
    initialize_order_tables()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT o.id, o.customer_id, c.customer_name, c.phone,
                   o.status, o.total_amount, o.created_at
            FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE o.id = ?
        """, (int(order_id),)).fetchone()
        if row is None:
            raise ValueError(f"Order #{order_id} was not found.")
        if row["customer_name"].strip().casefold() != name.casefold():
            raise ValueError(f"Order #{order_id} does not belong to customer '{name}'.")
        if row["status"] == "CANCELLED":
            raise ValueError(f"Order #{order_id} has already been cancelled.")
        if row["status"] not in ("PENDING", "CONFIRMED"):
            raise ValueError(f"Order #{order_id} cannot be cancelled (status: {row['status']}).")

        items = conn.execute(
            "SELECT menu_item_id, dish_name, quantity FROM order_items WHERE order_id = ?",
            (int(order_id),),
        ).fetchall()
        for item in items:
            cur = conn.execute(
                "UPDATE menu_items SET stock = stock + ? WHERE id = ?",
                (int(item["quantity"]), int(item["menu_item_id"])),
            )
            if cur.rowcount != 1:
                raise ValueError(f"Could not restore stock for {item['dish_name']}.")
        cur = conn.execute(
            "UPDATE orders SET status = 'CANCELLED' "
            "WHERE id = ? AND status IN ('PENDING','CONFIRMED')",
            (int(order_id),),
        )
        if cur.rowcount != 1:
            raise ValueError(f"Order #{order_id} could not be cancelled.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result = get_order_by_id(int(order_id))
    if result is None:
        raise RuntimeError("Order was cancelled but could not be retrieved.")
    return result


initialize_order_tables()