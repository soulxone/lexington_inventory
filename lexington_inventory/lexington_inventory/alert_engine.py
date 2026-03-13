"""
alert_engine.py
──────────────────────────────────────────────────────────────────────────────
Scheduled tasks:
  • run_daily_stock_check  — creates/updates Inventory Alert records
  • refresh_stock_snapshot — hourly bin-level snapshot (caches qty values)

Called by hooks.py scheduler_events.
"""

import frappe
from frappe.utils import today, now_datetime, flt


def refresh_stock_snapshot():
    """
    Hourly: Pull current stock qty for all items in the monitored warehouse.
    Stores snapshot timestamp in Inventory Monitor Settings for dashboard display.
    """
    settings = _get_settings()
    if not settings:
        return

    warehouse = settings.default_warehouse
    company   = settings.company

    # Count items with stock in the warehouse
    item_count = frappe.db.count("Bin", {"warehouse": warehouse, "actual_qty": [">", 0]})

    frappe.db.set_value("Inventory Monitor Settings", None, {
        "last_snapshot_at":    now_datetime(),
        "last_snapshot_items": item_count,
    })
    frappe.db.commit()


def run_daily_stock_check():
    """
    Daily: Scan all items in monitored warehouse against their reorder levels.
    Create or update Inventory Alert records for items below threshold.
    """
    settings = _get_settings()
    if not settings:
        return

    warehouse = settings.default_warehouse
    company   = settings.company
    threshold_pct = flt(settings.low_stock_threshold_pct) / 100.0

    # Fetch items with custom reorder fields set (lim_reorder_level > 0)
    # Falls back to ERPNext Item Reorder table if custom field not set
    alerts_created = 0
    alerts_updated = 0
    errors = 0

    try:
        # Get all items with qty in this warehouse
        bins = frappe.db.get_all(
            "Bin",
            filters={"warehouse": warehouse},
            fields=["item_code", "actual_qty", "valuation_rate"],
        )

        for bin_row in bins:
            try:
                _check_item_alert(
                    bin_row.item_code,
                    flt(bin_row.actual_qty),
                    flt(bin_row.valuation_rate),
                    warehouse,
                    settings,
                )
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"Inventory Alert — {bin_row.item_code}")
                errors += 1

        # Also check zero-stock items (items with item_reorder set but no bin)
        if settings.notify_on_zero_stock:
            _check_zero_stock_items(warehouse, settings)

        status = "Success" if not errors else f"Partial ({errors} errors)"
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Inventory Alert Engine — daily run failed")
        status = "Error"

    frappe.db.set_value("Inventory Monitor Settings", None, {
        "last_alert_run_at":  now_datetime(),
        "last_alert_status":  status,
    })
    frappe.db.commit()


def _check_item_alert(item_code, current_qty, valuation_rate, warehouse, settings):
    """Evaluate one item and create/update an alert if needed."""
    # Get reorder level from custom field first, then fall back to Item Reorder table
    reorder_level = frappe.db.get_value("Item", item_code, "lim_reorder_level") or 0
    reorder_qty   = frappe.db.get_value("Item", item_code, "lim_reorder_qty") or 0

    if not reorder_level:
        # Check ERPNext native Item Reorder
        native = frappe.db.get_value(
            "Item Reorder",
            {"parent": item_code, "warehouse": warehouse},
            ["warehouse_reorder_level", "warehouse_reorder_qty"],
            as_dict=True,
        )
        if native:
            reorder_level = flt(native.warehouse_reorder_level)
            reorder_qty   = flt(native.warehouse_reorder_qty)

    if not reorder_level:
        return  # No reorder config — skip

    alert_type = None
    if current_qty <= 0 and settings.notify_on_zero_stock:
        alert_type = "Zero Stock"
    elif current_qty <= reorder_level and settings.notify_on_reorder_level:
        alert_type = "Low Stock"

    if not alert_type:
        # Clear existing Open alert if stock is now OK
        existing = frappe.db.get_value(
            "Inventory Alert",
            {"item_code": item_code, "warehouse": warehouse, "status": "Open"},
            "name",
        )
        if existing:
            frappe.db.set_value("Inventory Alert", existing, "status", "Resolved")
        return

    # Check if Open alert already exists — update qty, else create new
    existing = frappe.db.get_value(
        "Inventory Alert",
        {"item_code": item_code, "warehouse": warehouse, "status": "Open"},
        "name",
    )
    if existing:
        frappe.db.set_value("Inventory Alert", existing, {
            "current_qty": current_qty,
            "alert_type":  alert_type,
        })
    else:
        alert = frappe.new_doc("Inventory Alert")
        alert.update({
            "item_code":     item_code,
            "warehouse":     warehouse,
            "alert_type":    alert_type,
            "alert_date":    today(),
            "status":        "Open",
            "current_qty":   current_qty,
            "reorder_level": reorder_level,
            "reorder_qty":   reorder_qty,
        })
        alert.insert(ignore_permissions=True)

        # Auto-create PO if configured
        if settings.auto_create_purchase_orders and reorder_qty > 0:
            _create_reorder_po(alert, settings)


def _check_zero_stock_items(warehouse, settings):
    """Find items configured with reorder levels that have zero/no bin."""
    items_with_reorder = frappe.db.sql("""
        SELECT ir.parent as item_code, ir.warehouse_reorder_level, ir.warehouse_reorder_qty
        FROM `tabItem Reorder` ir
        WHERE ir.warehouse = %(warehouse)s
          AND ir.warehouse_reorder_level > 0
          AND ir.parent NOT IN (
            SELECT item_code FROM `tabBin` WHERE warehouse = %(warehouse)s AND actual_qty > 0
          )
    """, {"warehouse": warehouse}, as_dict=True)

    for row in items_with_reorder:
        _check_item_alert(
            row.item_code, 0, 0, warehouse, settings
        )


def _create_reorder_po(alert_doc, settings):
    """Auto-create a Purchase Order for a low-stock alert."""
    preferred_supplier = frappe.db.get_value("Item", alert_doc.item_code, "lim_preferred_supplier")
    if not preferred_supplier:
        # Try ERPNext Item default supplier
        preferred_supplier = frappe.db.get_value(
            "Item Default",
            {"parent": alert_doc.item_code, "company": settings.company},
            "default_supplier",
        )
    if not preferred_supplier:
        return  # Can't create PO without a supplier

    po = frappe.new_doc("Purchase Order")
    po.supplier  = preferred_supplier
    po.company   = settings.company
    po.schedule_date = frappe.utils.add_days(today(), settings.default_lead_time_days or 14)
    po.lim_auto_generated = 1
    po.lim_alert_ref = alert_doc.name

    item_row = po.append("items", {})
    item_row.item_code  = alert_doc.item_code
    item_row.qty        = flt(alert_doc.reorder_qty) * flt(settings.default_reorder_multiplier or 1)
    item_row.schedule_date = po.schedule_date
    item_row.warehouse  = alert_doc.warehouse

    po.insert(ignore_permissions=True)
    if settings.auto_submit_po:
        po.submit()

    frappe.db.set_value("Inventory Alert", alert_doc.name, {
        "status":         "PO Created",
        "action_taken":   "PO Created",
        "purchase_order": po.name,
    })
    alert_doc.purchase_order = po.name


def _get_settings():
    """Return Inventory Monitor Settings singleton, or None if not configured."""
    try:
        s = frappe.get_single("Inventory Monitor Settings")
        if not s.default_warehouse or not s.company:
            return None
        return s
    except Exception:
        return None
