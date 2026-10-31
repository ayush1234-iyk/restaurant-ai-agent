# Restaurant AI Agent — Phase 4

## What's added
- Track a specific order by ID.
- View order history for the name entered at startup.
- Existing multi-dish order, confirmation, cooking/serving simulation, stock update, and order saving flow retained.
- Tracking checks the entered customer name against the order name before displaying details.

## Setup
1. Copy `rest_phase4.py` into the same folder as `database.py`, `order_service.py`, `restaurant.db`, and `.env`.
2. Ensure `order_service.py` includes `get_order_by_id(order_id)`.
3. Do not delete or recreate `restaurant.db`; it contains your current menu stock and order history.
4. Run in PowerShell:

   ```powershell
   python rest_phase4.py
   ```

5. Enter the customer name matching the order, then try:
   - `Track order 2`
   - `Show my order history`
   - `I want 1 pizza`

Order history is filtered by the entered customer name. This is a basic demo identity check, not production-grade authentication.
