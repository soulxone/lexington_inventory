// stock_entry_monitor.js
// Adds real-time stock level preview on Stock Entry items

frappe.ui.form.on("Stock Entry", {
    refresh(frm) {
        if (frm.doc.docstatus !== 0) return;

        frm.add_custom_button(__("Check Stock Levels"), () => {
            _show_stock_levels(frm);
        }, __("Inventory Monitor"));
    },
});

frappe.ui.form.on("Stock Entry Detail", {
    item_code(frm, cdt, cdn) {
        _fetch_and_show_item_stock(frm, cdt, cdn);
    },
});

function _fetch_and_show_item_stock(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.item_code) return;

    frappe.call({
        method: "lexington_inventory.lexington_inventory.api.get_item_stock_info",
        args: { item_code: row.item_code },
        callback(r) {
            if (!r.message || r.message.status !== "success") return;
            const s = r.message;
            const stockStatus = s.actual_qty <= 0
                ? "🔴 Zero Stock"
                : s.actual_qty <= s.reorder_level
                ? "🟠 Low Stock"
                : "🟢 In Stock";
            frappe.show_alert({
                message: `${row.item_code}: ${stockStatus} (${s.actual_qty} on hand)`,
                indicator: s.actual_qty <= 0 ? "red" : s.actual_qty <= s.reorder_level ? "orange" : "green",
            }, 5);
        },
    });
}

function _show_stock_levels(frm) {
    const items = (frm.doc.items || []).map(r => r.item_code).filter(Boolean);
    if (!items.length) {
        frappe.show_alert({ message: "No items in this entry.", indicator: "orange" }, 3);
        return;
    }

    const d = new frappe.ui.Dialog({
        title: __("Stock Levels for This Entry"),
        size: "large",
    });
    d.show();
    d.$body.html(`<p style="text-align:center;color:#888"><i class="fa fa-spinner fa-spin"></i> Loading…</p>`);

    Promise.all(items.map(item =>
        frappe.call({
            method: "lexington_inventory.lexington_inventory.api.get_item_stock_info",
            args: { item_code: item }
        }).then(r => r.message)
    )).then(results => {
        const rows = results.map(s => {
            const color = s.actual_qty <= 0 ? "#e74c3c" : s.actual_qty <= s.reorder_level ? "#e67e22" : "#27ae60";
            return `<tr>
                <td>${s.item_code}</td>
                <td style="color:${color};font-weight:600">${s.actual_qty}</td>
                <td>${s.reorder_level || "—"}</td>
                <td>${s.open_alerts > 0 ? `<span class="badge badge-warning">${s.open_alerts}</span>` : "✓"}</td>
            </tr>`;
        }).join("");
        d.$body.html(`
            <table class="table table-condensed">
                <thead><tr><th>Item</th><th>On Hand</th><th>Reorder Level</th><th>Alerts</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `);
    });
}
