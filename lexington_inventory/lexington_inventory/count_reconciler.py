"""
count_reconciler.py
──────────────────────────────────────────────────────────────────────────────
Handles Inventory Count submission:
  1. Validates counted_qty is filled for all items
  2. Calculates variance_qty, variance_pct, variance_value for each row
  3. Flags rows exceeding threshold for re-count
  4. Creates a Stock Reconciliation in ERPNext to adjust ledger
  5. Links the Reconciliation back to the Inventory Count
"""

import frappe
from frappe.utils import flt, now_datetime


def on_count_submit(doc, method=None):
    """
    Hook: called when Inventory Count is submitted.
    doc: Inventory Count document (Frappe document object)
    """
    settings = _get_settings()
    variance_threshold = flt(getattr(settings, "count_variance_threshold_pct", 5)) / 100.0
    require_recount    = getattr(settings, "require_recount_on_variance", 1)

    total_variance_value = 0
    items_with_variance  = 0
    recount_required     = False

    # ── Step 1: Calculate variances ──────────────────────────────────────────
    for row in doc.items:
        if row.counted_qty is None or row.counted_qty == "":
            frappe.throw(f"Please enter Counted Qty for item {row.item_code}")

        system_qty   = flt(row.system_qty)
        counted_qty  = flt(row.counted_qty)
        variance_qty = counted_qty - system_qty
        val_rate     = flt(row.valuation_rate)

        variance_value = variance_qty * val_rate
        variance_pct   = (abs(variance_qty) / system_qty * 100) if system_qty else 0

        row.variance_qty   = variance_qty
        row.variance_pct   = variance_pct
        row.variance_value = variance_value

        if variance_qty != 0:
            items_with_variance += 1
            total_variance_value += abs(variance_value)

        # Flag for re-count if above threshold
        if require_recount and variance_pct > (variance_threshold * 100):
            row.recount_flag = 1
            recount_required = True
        else:
            row.recount_flag = 0

    # Update summary fields
    doc.db_set("total_items",          len(doc.items))
    doc.db_set("items_counted",        sum(1 for r in doc.items if r.counted_qty is not None))
    doc.db_set("items_with_variance",  items_with_variance)
    doc.db_set("total_variance_value", total_variance_value)
    doc.db_set("recount_required",     1 if recount_required else 0)
    doc.db_set("submitted_at",         now_datetime())
    doc.db_set("status",               "Pending Review" if recount_required else "Approved")

    # Save variance fields on child rows
    for row in doc.items:
        frappe.db.set_value("Inventory Count Item", row.name, {
            "variance_qty":   row.variance_qty,
            "variance_pct":   row.variance_pct,
            "variance_value": row.variance_value,
            "recount_flag":   row.recount_flag,
        })

    # ── Step 2: If no recount required, post Stock Reconciliation ────────────
    if not recount_required:
        recon_name = _create_stock_reconciliation(doc)
        doc.db_set("reconciliation_ref", recon_name)
        doc.db_set("status", "Reconciled")


def _create_stock_reconciliation(count_doc):
    """Create ERPNext Stock Reconciliation from the Inventory Count."""
    recon = frappe.new_doc("Stock Reconciliation")
    recon.company = count_doc.company or frappe.defaults.get_global_default("company")
    recon.purpose = "Stock Reconciliation"
    recon.inventory_count_ref = count_doc.name  # custom field added by fixture

    for row in count_doc.items:
        if flt(row.variance_qty) == 0:
            continue  # No change needed
        item_row = recon.append("items", {})
        item_row.item_code = row.item_code
        item_row.warehouse = count_doc.warehouse
        item_row.qty       = flt(row.counted_qty)

    if not recon.items:
        return None  # Nothing to reconcile

    recon.insert(ignore_permissions=True)
    recon.submit()
    return recon.name


def populate_system_qty(count_doc):
    """
    API helper: populate system_qty and valuation_rate for all items in the count
    from the current bin levels. Called from client JS when items are added.
    """
    warehouse = count_doc.warehouse
    for row in count_doc.items:
        bin_data = frappe.db.get_value(
            "Bin",
            {"item_code": row.item_code, "warehouse": warehouse},
            ["actual_qty", "valuation_rate"],
            as_dict=True,
        )
        if bin_data:
            row.system_qty     = flt(bin_data.actual_qty)
            row.valuation_rate = flt(bin_data.valuation_rate)
        else:
            row.system_qty     = 0
            row.valuation_rate = 0


def _get_settings():
    try:
        return frappe.get_single("Inventory Monitor Settings")
    except Exception:
        return frappe._dict(count_variance_threshold_pct=5, require_recount_on_variance=1)
