"""
stock_events.py
──────────────────────────────────────────────────────────────────────────────
Doc-event handlers for ERPNext Stock Entry and Purchase Receipt.
Re-evaluates inventory alerts when stock moves occur.
"""

import frappe


def on_stock_entry_submit(doc, method=None):
    """
    Called when a Stock Entry (Receipt / Transfer / Issue) is submitted.
    Triggers alert re-evaluation for affected items.
    """
    affected_items = {row.item_code for row in doc.items if row.item_code}
    for item_code in affected_items:
        _refresh_alerts_for_item(item_code, doc.from_warehouse or doc.to_warehouse)


def on_purchase_receipt_submit(doc, method=None):
    """
    Called when a Purchase Receipt is submitted.
    Resolves any Open/PO-Created alerts for received items.
    """
    for row in doc.items:
        if not row.item_code:
            continue
        # Close out PO-Created alerts for this item at this warehouse
        alerts = frappe.db.get_all(
            "Inventory Alert",
            filters={
                "item_code": row.item_code,
                "warehouse": row.warehouse,
                "status": ["in", ["Open", "PO Created"]],
            },
            fields=["name", "reorder_level"],
        )
        for alert in alerts:
            # Check current qty — if above reorder level, resolve
            current_qty = frappe.db.get_value(
                "Bin",
                {"item_code": row.item_code, "warehouse": row.warehouse},
                "actual_qty",
            ) or 0
            if current_qty > (alert.reorder_level or 0):
                frappe.db.set_value("Inventory Alert", alert.name, {
                    "status":      "Resolved",
                    "resolved_at": frappe.utils.now_datetime(),
                })


def _refresh_alerts_for_item(item_code, warehouse):
    """
    Re-check alert status for a single item after a stock movement.
    Imports alert_engine to avoid circular imports.
    """
    if not warehouse:
        return
    settings = _get_settings()
    if not settings or settings.default_warehouse != warehouse:
        return

    from lexington_inventory.lexington_inventory.alert_engine import _check_item_alert
    current_qty   = frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
    ) or 0
    valuation_rate = frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate"
    ) or 0
    _check_item_alert(item_code, current_qty, valuation_rate, warehouse, settings)


def _get_settings():
    try:
        s = frappe.get_single("Inventory Monitor Settings")
        return s if (s.default_warehouse and s.company) else None
    except Exception:
        return None
