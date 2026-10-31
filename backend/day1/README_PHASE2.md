# Restaurant AI Agent — Phase 2: Order Management

## Safety
This phase adds a separate `order_service.py` module. It does **not** replace your current `database.py` or `rest.py`, and it does not delete or reseed `menu_items`. Your existing 500 dishes and current stock values remain as they are.

## 1. Copy the file
Copy `order_service.py` into:
`C:\Users\DELL\Desktop\resturantAI\backend\day1`

Keep it in the same folder as `restaurant.db`.

If your database file is stored in another location, change `DB_PATH` near the top of `order_service.py` to the exact path of your current database. Do not create a new empty database by accident.

## 2. Initialize the new tables
Open a terminal in that folder and run:
```powershell
python order_service.py
```
It creates `customers`, `orders`, and `order_items` only if they do not already exist.

## 3. Test a bill preview (does not deduct stock)
Run:
```powershell
python -c "from order_service import preview_order; print(preview_order([{'dish_name':'Pizza','quantity':1},{'dish_name':'Burger','quantity':1}]))"
```

## 4. Place a test order (this DOES save the order and deduct stock)
Only run this if you want to make a real test order in your database:
```powershell
python -c "from order_service import place_order; print(place_order('Test Customer',[{'dish_name':'Pizza','quantity':1},{'dish_name':'Burger','quantity':1}]))"
```
This operation is transactional: if any item is unavailable, it rolls back the entire order and stock changes.

## 5. View order history
```powershell
python -c "from order_service import get_order_history; print(get_order_history())"
```

## Functions
- `initialize_order_tables()` — safely adds the three order tables.
- `preview_order(items)` — calculates current prices/stock; does not mutate data.
- `place_order(customer_name, items, phone=None)` — saves a confirmed order and decrements stock atomically.
- `get_order_history(limit=20)` — returns recent orders.

Input format:
```python
[
    {"dish_name": "Pizza", "quantity": 2},
    {"dish_name": "Burger", "quantity": 1},
]
```

This is the database/order-service foundation. The next phase will connect multi-dish natural-language requests and confirmation to the LangGraph agent.
