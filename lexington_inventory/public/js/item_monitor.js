// item_monitor.js
// Adds an "Inventory Monitor" tab to the ERPNext Item form
// showing live stock levels, reorder config, open alerts, recent movements.

frappe.ui.form.on("Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        // ── "Inventory Monitor" button in toolbar ──────────────────────────
        frm.add_custom_button(__("Inventory Monitor"), () => {
            _show_stock_monitor_dialog(frm.doc.item_code);
        }, __("Stock"));

        // ── Alert badge if open alerts exist ───────────────────────────────
        frappe.db.count("Inventory Alert", {
            item_code: frm.doc.item_code,
            status: "Open"
        }).then(count => {
            if (count > 0) {
                frm.dashboard.add_comment(
                    `⚠ ${count} open inventory alert${count > 1 ? "s" : ""} for this item.`,
                    "orange", true
                );
            }
        });
    },

    lim_reorder_level(frm) {
        // Recalculate reorder status indicator when threshold changes
        _update_reorder_indicator(frm);
    },
});

function _show_stock_monitor_dialog(item_code) {
    const d = new frappe.ui.Dialog({
        title: __("Inventory Monitor — {0}", [item_code]),
        size: "large",
    });
    d.show();
    d.$body.html(`<div style="padding:16px;text-align:center;color:#888">
        <i class="fa fa-spinner fa-spin fa-2x"></i><br>Loading stock data…
    </div>`);

    frappe.call({
        method: "lexington_inventory.lexington_inventory.api.get_item_stock_info",
        args: { item_code },
        callback(r) {
            if (!r.message || r.message.status !== "success") {
                d.$body.html(`<p class="text-danger">Failed to load stock data.</p>`);
                return;
            }
            const s = r.message;
            const alertBadge = s.open_alerts > 0
                ? `<span class="badge badge-warning">${s.open_alerts} open alert${s.open_alerts > 1 ? "s" : ""}</span>`
                : `<span class="badge badge-success">No alerts</span>`;

            const movements = (s.recent_movements || []).map(m => `
                <tr>
                    <td>${m.posting_date}</td>
                    <td>${m.voucher_type}</td>
                    <td><a href="/app/${(m.voucher_type||"").toLowerCase().replace(/ /g,"-")}/${m.voucher_no}">${m.voucher_no}</a></td>
                    <td style="color:${m.actual_qty >= 0 ? "green" : "red"}">${m.actual_qty >= 0 ? "+" : ""}${m.actual_qty}</td>
                    <td>${m.qty_after_transaction}</td>
                </tr>
            `).join("") || `<tr><td colspan="5" style="color:#aaa;text-align:center">No recent movements</td></tr>`;

            const pctOfReorder = s.reorder_level
                ? Math.round((s.actual_qty / s.reorder_level) * 100)
                : null;
            const levelBar = pctOfReorder !== null ? `
                <div style="background:#eee;border-radius:4px;height:8px;margin:4px 0">
                    <div style="background:${s.actual_qty <= 0 ? "#e74c3c" : s.actual_qty <= s.reorder_level ? "#e67e22" : "#27ae60"};
                                width:${Math.min(pctOfReorder, 100)}%;height:100%;border-radius:4px;transition:width .3s">
                    </div>
                </div>
                <small style="color:#888">${pctOfReorder}% of reorder level</small>
            ` : "";

            d.$body.html(`
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px">
                    <div style="background:#f8f9fa;padding:16px;border-radius:8px;text-align:center">
                        <div style="font-size:28px;font-weight:700;color:${s.actual_qty <= 0 ? "#e74c3c" : s.actual_qty <= s.reorder_level ? "#e67e22" : "#27ae60"}">
                            ${s.actual_qty}
                        </div>
                        <div style="color:#888;font-size:11px;margin-top:4px">CURRENT QTY</div>
                        ${levelBar}
                    </div>
                    <div style="background:#f8f9fa;padding:16px;border-radius:8px;text-align:center">
                        <div style="font-size:28px;font-weight:700;color:#3498db">${s.reorder_level || "—"}</div>
                        <div style="color:#888;font-size:11px;margin-top:4px">REORDER LEVEL</div>
                        <div style="margin-top:4px;font-size:12px">Reorder Qty: <b>${s.reorder_qty || "—"}</b></div>
                    </div>
                    <div style="background:#f8f9fa;padding:16px;border-radius:8px;text-align:center">
                        <div style="font-size:28px;font-weight:700">${alertBadge}</div>
                        <div style="color:#888;font-size:11px;margin-top:8px">ALERTS</div>
                        <div style="margin-top:4px;font-size:12px">Last count: <b>${s.last_count_date || "Never"}</b></div>
                    </div>
                </div>
                <div style="margin-top:8px">
                    <h6 style="color:#555;font-weight:600;margin-bottom:8px">Recent Stock Movements (last 5)</h6>
                    <table class="table table-condensed" style="font-size:12px">
                        <thead><tr>
                            <th>Date</th><th>Type</th><th>Reference</th><th>Qty Change</th><th>Balance</th>
                        </tr></thead>
                        <tbody>${movements}</tbody>
                    </table>
                </div>
                <div style="margin-top:8px">
                    <a href="/app/inventory-alert?item_code=${item_code}" class="btn btn-xs btn-default">
                        <i class="fa fa-bell"></i> View All Alerts
                    </a>
                    <a href="/app/inventory-count?new=1" class="btn btn-xs btn-primary" style="margin-left:8px">
                        <i class="fa fa-list-ol"></i> New Count
                    </a>
                </div>
            `);
        },
    });
}

function _update_reorder_indicator(frm) {
    // Optionally add a field-level hint when reorder level is configured
    if (frm.doc.lim_reorder_level > 0) {
        frm.set_df_property("lim_reorder_level", "description",
            `Item will alert when stock falls below ${frm.doc.lim_reorder_level} units.`
        );
    }
}
