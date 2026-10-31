import sqlite3
from pathlib import Path

# Keep restaurant.db in the same folder as this Python file.
DB_PATH = Path(__file__).with_name("restaurant.db")


def get_connection():
    return sqlite3.connect(DB_PATH, timeout=10)


def initialize_database():
    """Create the table and add starter dishes only if the table is empty.

    Existing menu/stock is never reset by this function.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL CHECK(stock >= 0)
        )
        """
    )

    cursor.execute("SELECT COUNT(*) FROM menu_items")
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.executemany(
            """
            INSERT INTO menu_items (dish_name, price, stock)
            VALUES (?, ?, ?)
            """,
            [
                ("pizza", 250, 5),
                ("burger", 120, 3),
                ("paneer tikka", 200, 2),
                ("cold coffee", 100, 0),
            ],
        )

    conn.commit()
    conn.close()


def get_menu():
    initialize_database()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, dish_name, price, stock FROM menu_items ORDER BY id"
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_dish(dish_name):
    initialize_database()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT dish_name, price, stock
            FROM menu_items
            WHERE LOWER(dish_name) = LOWER(?)
            """,
            (dish_name.strip(),),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def update_stock(dish_name, quantity):
    """Atomically subtract quantity only when sufficient stock exists."""
    if not isinstance(quantity, int) or quantity <= 0:
        return False

    initialize_database()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE menu_items
            SET stock = stock - ?
            WHERE LOWER(dish_name) = LOWER(?)
              AND stock >= ?
            """,
            (quantity, dish_name.strip(), quantity),
        )
        success = cursor.rowcount == 1
        if success:
            conn.commit()
        else:
            conn.rollback()
        return success
    finally:
        conn.close()


if __name__ == "__main__":
    initialize_database()
    print("Restaurant Menu:")
    for item in get_menu():
        print(item)
