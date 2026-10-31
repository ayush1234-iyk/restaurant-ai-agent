import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("restaurant.db")
DATA_PATH = Path(__file__).with_name("menu_dataset.json")
TARGET_MENU_SIZE = 500


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    items = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        cur = conn.cursor()

        # Keep the existing table and its stock values; add new columns safely.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dish_name TEXT NOT NULL UNIQUE,
                price REAL NOT NULL CHECK(price >= 0),
                stock INTEGER NOT NULL CHECK(stock >= 0)
            )
        """)

        columns = {
            row[1] for row in cur.execute("PRAGMA table_info(menu_items)").fetchall()
        }
        if "category" not in columns:
            cur.execute("ALTER TABLE menu_items ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'")
        if "description" not in columns:
            cur.execute("ALTER TABLE menu_items ADD COLUMN description TEXT NOT NULL DEFAULT ''")

        # Add category/description metadata for existing items without changing prices or stock.
        for item in items:
            cur.execute("""
                UPDATE menu_items
                SET category = ?, description = ?
                WHERE LOWER(dish_name) = LOWER(?)
            """, (item["category"], item["description"], item["dish_name"]))

        existing_count = cur.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        inserted = 0

        # Preserve existing rows and only add new dishes until the database has 500 rows.
        for item in items:
            if existing_count >= TARGET_MENU_SIZE:
                break
            cur.execute(
                "SELECT 1 FROM menu_items WHERE LOWER(dish_name) = LOWER(?)",
                (item["dish_name"],)
            )
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO menu_items (dish_name, price, stock, category, description)
                VALUES (?, ?, ?, ?, ?)
            """, (
                item["dish_name"], item["price"], item["stock"],
                item["category"], item["description"]
            ))
            existing_count += 1
            inserted += 1

        conn.commit()
        final_count = cur.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        print(f"Dataset records available: {len(items)}")
        print(f"New dishes inserted: {inserted}")
        print(f"Total menu items in database: {final_count}")
        print("Existing dish prices and stock values were preserved.")
        print("\nSample menu:")
        for row in cur.execute("""
            SELECT id, dish_name, category, price, stock
            FROM menu_items ORDER BY id LIMIT 10
        """):
            print(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
