"""
api.py
──────────────────────────────────────────────────────────────────────────────
Whitelisted API endpoints for the Lexington Inventory Monitor.
Called from client-side JS forms.
"""

import frappe
from frappe import _
from frappe.utils import flt, today


@frappe.whitelist()
def get_item_stock_info(item_code, warehouse=None):
    """
    Return current stock, reorder level, open alerts for an item.
    Used by Item form monitor tab.
    """
    if not warehouse:
        settings = frappe.get_single("Inventory Monitor Settings")
        warehouse = settings.default_warehouse

    bin_data = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "reserved_qty", "ordered_qty", "valuation_rate"],
        as_dict=True,
    ) or {}

    reorder_level = frappe.db.get_value("Item", item_code, "lim_reorder_level") or 0
    reorder_qty   = frappe.db.get_value("Item", item_code, "lim_reorder_qty") or 0
    last_count    = frappe.db.get_value("Item", item_code, "lim_last_count_date")

    # Native reorder fallback
    if not reorder_level:
        native = frappe.db.get_value(
            "Item Reorder",
            {"parent": item_code, "warehouse": warehouse},
            ["warehouse_reorder_level", "warehouse_reorder_qty"],
            as_dict=True,
        )
        if native:
            reorder_level = flt(native.warehouse_reorder_level)
            reorder_qty   = flt(native.warehouse_reorder_qty)

    open_alerts = frappe.db.count(
        "Inventory Alert",
        {"item_code": item_code, "warehouse": warehouse, "status": "Open"},
    )

    # Last 5 stock movements
    movements = frappe.db.sql("""
        SELECT sle.posting_date, sle.voucher_type, sle.voucher_no,
               sle.actual_qty, sle.qty_after_transaction
        FROM `tabStock Ledger Entry` sle
        WHERE sle.item_code = %(item)s
          AND sle.warehouse = %(wh)s
        ORDER BY sle.posting_date DESC, sle.creation DESC
        LIMIT 5
    """, {"item": item_code, "wh": warehouse}, as_dict=True)

    return {
        "status": "success",
        "item_code": item_code,
        "warehouse": warehouse,
        "actual_qty": flt(bin_data.get("actual_qty")),
        "reserved_qty": flt(bin_data.get("reserved_qty")),
        "ordered_qty": flt(bin_data.get("ordered_qty")),
        "valuation_rate": flt(bin_data.get("valuation_rate")),
        "reorder_level": reorder_level,
        "reorder_qty": reorder_qty,
        "last_count_date": last_count,
        "open_alerts": open_alerts,
        "recent_movements": movements,
    }


@frappe.whitelist()
def run_stock_check_now():
    """Manual trigger for the daily stock check. System Manager only."""
    frappe.only_for("System Manager")
    from lexington_inventory.lexington_inventory.alert_engine import run_daily_stock_check
    run_daily_stock_check()
    alert_count = frappe.db.count("Inventory Alert", {"status": "Open", "alert_date": today()})
    return {
        "status": "success",
        "message": _("Stock check complete. {0} open alert(s) today.").format(alert_count),
        "open_alerts": alert_count,
    }


@frappe.whitelist()
def populate_count_items(count_name):
    """
    Populate system_qty and valuation_rate for all items in an Inventory Count.
    Called from the Inventory Count form JS when user clicks 'Refresh System Qty'.
    """
    doc = frappe.get_doc("Inventory Count", count_name)
    if doc.docstatus != 0:
        frappe.throw(_("Can only refresh on Draft counts"))

    from lexington_inventory.lexington_inventory.count_reconciler import populate_system_qty
    populate_system_qty(doc)
    doc.save()
    return {
        "status": "success",
        "message": _("System quantities refreshed for {0} items.").format(len(doc.items)),
    }


@frappe.whitelist()
def get_open_alerts(warehouse=None, limit=20):
    """Return open Inventory Alerts for the dashboard."""
    filters = {"status": "Open"}
    if warehouse:
        filters["warehouse"] = warehouse

    alerts = frappe.db.get_all(
        "Inventory Alert",
        filters=filters,
        fields=["name", "item_code", "item_name", "warehouse",
                "alert_type", "alert_date", "current_qty",
                "reorder_level", "reorder_qty"],
        order_by="alert_date desc",
        limit=int(limit),
    )
    return {"status": "success", "alerts": alerts, "total": len(alerts)}


@frappe.whitelist()
def create_reorder_po(alert_name):
    """Manually trigger PO creation for a specific alert."""
    frappe.only_for(["Stock Manager", "System Manager"])
    alert = frappe.get_doc("Inventory Alert", alert_name)
    if alert.status not in ["Open"]:
        frappe.throw(_("Alert is already resolved or has a PO."))

    settings = frappe.get_single("Inventory Monitor Settings")
    from lexington_inventory.lexington_inventory.alert_engine import _create_reorder_po
    _create_reorder_po(alert, settings)
    frappe.db.commit()

    return {
        "status": "success",
        "message": _("Purchase Order created: {0}").format(alert.purchase_order),
        "purchase_order": alert.purchase_order,
    }


@frappe.whitelist()
def get_dashboard_summary():
    """Return summary stats for the Lexington Inventory workspace dashboard."""
    settings = frappe.get_single("Inventory Monitor Settings")
    warehouse = settings.default_warehouse

    return {
        "status": "success",
        "open_alerts":       frappe.db.count("Inventory Alert", {"status": "Open"}),
        "zero_stock":        frappe.db.count("Inventory Alert", {"status": "Open", "alert_type": "Zero Stock"}),
        "low_stock":         frappe.db.count("Inventory Alert", {"status": "Open", "alert_type": "Low Stock"}),
        "pending_counts":    frappe.db.count("Inventory Count", {"status": ["in", ["Draft", "In Progress"]]}),
        "items_in_warehouse": frappe.db.count("Bin", {"warehouse": warehouse, "actual_qty": [">", 0]}),
        "last_snapshot_at":  settings.last_snapshot_at,
        "last_alert_run_at": settings.last_alert_run_at,
        "last_alert_status": settings.last_alert_status,
    }
