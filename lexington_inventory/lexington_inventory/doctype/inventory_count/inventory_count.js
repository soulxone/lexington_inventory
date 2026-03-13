// inventory_count.js — Frappe form JS for Inventory Count

frappe.ui.form.on("Inventory Count", {
    refresh(frm) {
        _update_status_banner(frm);

        if (frm.doc.docstatus === 0) {
            // ── Draft / In Progress buttons ────────────────────────────────
            frm.add_custom_button(__("Refresh System Qty"), () => {
                if (frm.is_dirty()) {
                    frappe.msgprint(__("Please save the form before refreshing system quantities."));
                    return;
                }
                frappe.show_progress(__("Fetching stock levels…"), 0, 100);
                frappe.call({
                    method: "lexington_inventory.lexington_inventory.api.populate_count_items",
                    args: { count_name: frm.doc.name },
                    callback(r) {
                        frappe.hide_progress();
                        const res = r.message || {};
                        if (res.status === "success") {
                            frappe.show_alert({ message: res.message, indicator: "green" }, 5);
                            frm.reload_doc();
                        }
                    },
                });
            }, __("Actions"));

            frm.add_custom_button(__("Load All Warehouse Items"), () => {
                frappe.confirm(
                    __("This will replace the current item list with ALL items in {0}. Continue?",
                       [frm.doc.warehouse || "the warehouse"]),
                    () => _load_all_warehouse_items(frm)
                );
            }, __("Actions"));

            if (frm.doc.status === "In Progress") {
                frm.add_custom_button(__("Mark As Pending Review"), () => {
                    frm.set_value("status", "Pending Review");
                    frm.save();
                });
            }
        }

        if (frm.doc.docstatus === 1) {
            // ── Submitted — show reconciliation link ───────────────────────
            if (frm.doc.reconciliation_ref) {
                frm.dashboard.add_comment(
                    `✓ Reconciled — <a href="/app/stock-reconciliation/${frm.doc.reconciliation_ref}">${frm.doc.reconciliation_ref}</a>`,
                    "green", true
                );
            }
            if (frm.doc.recount_required) {
                frm.dashboard.add_comment(
                    "⚠ Re-count required on some items — please review and amend.",
                    "orange", true
                );
            }
        }
    },

    warehouse(frm) {
        // Prompt to auto-load items when warehouse is set
        if (frm.doc.warehouse && !frm.doc.items?.length) {
            frappe.show_alert({
                message: __("Warehouse set. Use Actions → Load All Warehouse Items to populate the count list."),
                indicator: "blue",
            }, 6);
        }
    },
});

frappe.ui.form.on("Inventory Count Item", {
    counted_qty(frm, cdt, cdn) {
        _recalculate_row(frm, cdt, cdn);
    },
    recount_qty(frm, cdt, cdn) {
        // If recount_qty is entered, use it as the final counted qty
        const row = locals[cdt][cdn];
        if (row.recount_qty) {
            frappe.model.set_value(cdt, cdn, "counted_qty", row.recount_qty);
        }
    },
});

function _recalculate_row(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const variance_qty = (row.counted_qty || 0) - (row.system_qty || 0);
    const variance_pct = row.system_qty ? Math.abs(variance_qty) / row.system_qty * 100 : 0;
    const variance_value = variance_qty * (row.valuation_rate || 0);

    frappe.model.set_value(cdt, cdn, "variance_qty",   variance_qty);
    frappe.model.set_value(cdt, cdn, "variance_pct",   variance_pct);
    frappe.model.set_value(cdt, cdn, "variance_value", variance_value);

    // Update summary counters
    _update_summary(frm);
}

function _update_summary(frm) {
    const items = frm.doc.items || [];
    const counted = items.filter(r => r.counted_qty !== null && r.counted_qty !== undefined).length;
    const withVar = items.filter(r => r.variance_qty && r.variance_qty !== 0).length;
    const totalVar = items.reduce((sum, r) => sum + Math.abs(r.variance_value || 0), 0);

    frm.set_value("total_items",         items.length);
    frm.set_value("items_counted",       counted);
    frm.set_value("items_with_variance", withVar);
    frm.set_value("total_variance_value", totalVar);
}

function _update_status_banner(frm) {
    if (!frm.doc.total_items) return;
    const pct = Math.round((frm.doc.items_counted || 0) / frm.doc.total_items * 100);
    frm.dashboard.add_comment(
        `Count progress: <b>${frm.doc.items_counted || 0} / ${frm.doc.total_items}</b> items (${pct}%) — Variance: <b>${frappe.format(frm.doc.total_variance_value, {fieldtype:"Currency"})}</b>`,
        frm.doc.recount_required ? "orange" : (pct === 100 ? "green" : "blue"),
        true
    );
}

function _load_all_warehouse_items(frm) {
    frappe.show_progress(__("Loading items…"), 0, 100);
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Bin",
            filters: { warehouse: frm.doc.warehouse },
            fields: ["item_code", "actual_qty", "valuation_rate"],
            limit_page_length: 500,
        },
        callback(r) {
            frappe.hide_progress();
            if (!r.message || !r.message.length) {
                frappe.msgprint(__("No items found in warehouse {0}", [frm.doc.warehouse]));
                return;
            }
            frm.clear_table("items");
            r.message.forEach(bin => {
                const row = frm.add_child("items");
                row.item_code      = bin.item_code;
                row.system_qty     = bin.actual_qty;
                row.valuation_rate = bin.valuation_rate;
            });
            frm.refresh_field("items");
            frappe.show_alert({
                message: __("{0} items loaded from {1}.", [r.message.length, frm.doc.warehouse]),
                indicator: "green",
            }, 5);
        },
    });
}
