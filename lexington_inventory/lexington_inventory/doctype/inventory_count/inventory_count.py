import frappe
from frappe.model.document import Document


class InventoryCount(Document):
    # on_submit posting of the Stock Reconciliation is wired via the
    # doc_events hook (count_reconciler.on_count_submit) in hooks.py.
    pass
