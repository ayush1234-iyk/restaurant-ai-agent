import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


# Load local .env file.
# On Render, DATABASE_URL comes from environment variables.
load_dotenv(Path(__file__).resolve().parent / ".env")


def get_connection():
    """Connect to Neon PostgreSQL."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL missing. Check your .env file or Render environment."
        )

    return psycopg.connect(database_url)


def initialize_database():
    """Verify that the existing PostgreSQL menu table is accessible."""
    with get_connection() as conn:
        conn.execute("SELECT 1 FROM menu_items LIMIT 1")


def get_menu():
    """Return all menu items in the existing tuple format."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, dish_name, price, stock
            FROM menu_items
            ORDER BY id
            """
        )
        return cursor.fetchall()


def get_dish(dish_name):
    """Find a dish without case sensitivity."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT dish_name, price, stock
            FROM menu_items
            WHERE LOWER(dish_name) = LOWER(%s)
            """,
            (dish_name.strip(),),
        )
        return cursor.fetchone()


def update_stock(dish_name, quantity):
    """Subtract stock only when sufficient quantity is available."""
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return False

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE menu_items
            SET stock = stock - %s
            WHERE LOWER(dish_name) = LOWER(%s)
              AND stock >= %s
            """,
            (quantity, dish_name.strip(), quantity),
        )

        return cursor.rowcount == 1


if __name__ == "__main__":
    initialize_database()

    menu = get_menu()
    print(f"Restaurant Menu: {len(menu)} dishes found.")

    for item in menu[:10]:
        print(item)