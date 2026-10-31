# Phase 3 — Multi-item LangGraph order flow

## Before replacing anything
Keep your original `rest.py` as a backup. This file is named `rest_phase3.py` so it will not overwrite the original.

## Install/copy
Copy `rest_phase3.py` into:
`C:\Users\DELL\Desktop\resturantAI\backend\day1`

Keep it in the same folder as:
- `database.py`
- `order_service.py`
- `restaurant.db`
- `.env`

The `.env` must contain `GROQ_API_KEY=...`.

## Run
```powershell
python rest_phase3.py
```

Example:
- Name: Ayush
- Order: `2 pizza and 1 burger`
- Check the printed bill.
- Answer `yes` to proceed or `no` to cancel.

Note: cooking and serving remain demo simulations with random outcomes, just like the original project. The database order is saved and stock is deducted only after serving succeeds. `place_order()` handles the stock deduction, so this version intentionally does not call `update_stock()` separately (prevents double deduction).

## Safety
- Does not modify `database.py`.
- Does not reset menu items.
- Does not modify the original `rest.py`.
- Existing `order_service.py` must be present.
- Out-of-stock orders are not saved.
- If stock changes after the bill preview, `place_order()` rechecks it transactionally.

## Important test note
Your earlier test order used 1 pizza and 1 burger, so current stock was shown as pizza=2 and burger=0. Burger is now out of stock. To test a successful order, choose a dish with sufficient stock or use a quantity that is currently available. Do not reset your database just to test.
