// inventory_monitor_settings.js — Frappe form JS for Inventory Monitor Settings

frappe.ui.form.on("Inventory Monitor Settings", {
    refresh(frm) {
        // ── Toolbar buttons ────────────────────────────────────────────────
        frm.add_custom_button(__("Run Stock Check Now"), () => {
            frappe.confirm(
                __("Run a full stock check against all monitored items now?"),
                () => {
                    frappe.show_progress(__("Running stock check…"), 0, 100, __("Please wait"));
                    frappe.call({
                        method: "lexington_inventory.lexington_inventory.api.run_stock_check_now",
                        callback(r) {
                            frappe.hide_progress();
                            const res = r.message || {};
                            frappe.show_alert({
                                message: res.message || (res.status === "success" ? "Done" : "Error"),
                                indicator: res.status === "success" ? "green" : "red",
                            }, 7);
                            frm.reload_doc();
                        },
                    });
                }
            );
        }, __("Monitor"));

        frm.add_custom_button(__("View Open Alerts"), () => {
            frappe.set_route("List", "Inventory Alert", "List", { status: "Open" });
        }, __("Monitor"));

        frm.add_custom_button(__("New Inventory Count"), () => {
            frappe.new_doc("Inventory Count");
        }, __("Monitor"));

        frm.add_custom_button(__("Dashboard Summary"), () => {
            _show_dashboard_summary(frm);
        }, __("Monitor"));

        // ── Status banner ──────────────────────────────────────────────────
        if (frm.doc.last_alert_run_at) {
            const color = frm.doc.last_alert_status === "Success" ? "green"
                        : frm.doc.last_alert_status === "Error"   ? "red" : "orange";
            frm.dashboard.add_comment(
                `Last alert run: <b>${frm.doc.last_alert_status || "—"}</b> at ${frm.doc.last_alert_run_at}` +
                (frm.doc.last_snapshot_items ? ` — ${frm.doc.last_snapshot_items} items in snapshot` : ""),
                color, true
            );
        }
    },
});

function _show_dashboard_summary(frm) {
    frappe.call({
        method: "lexington_inventory.lexington_inventory.api.get_dashboard_summary",
        callback(r) {
            if (!r.message || r.message.status !== "success") return;
            const s = r.message;
            frappe.msgprint({
                title: __("Inventory Monitor Dashboard"),
                message: `
                    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:8px 0">
                        <div style="background:#fde8e8;padding:16px;border-radius:8px;text-align:center">
                            <div style="font-size:32px;font-weight:700;color:#e74c3c">${s.zero_stock}</div>
                            <div style="font-size:11px;color:#888">ZERO STOCK ITEMS</div>
                        </div>
                        <div style="background:#fef3e2;padding:16px;border-radius:8px;text-align:center">
                            <div style="font-size:32px;font-weight:700;color:#e67e22">${s.low_stock}</div>
                            <div style="font-size:11px;color:#888">LOW STOCK ITEMS</div>
                        </div>
                        <div style="background:#e8f5e9;padding:16px;border-radius:8px;text-align:center">
                            <div style="font-size:32px;font-weight:700;color:#27ae60">${s.items_in_warehouse}</div>
                            <div style="font-size:11px;color:#888">ITEMS IN WAREHOUSE</div>
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
                        <div style="background:#f8f9fa;padding:12px;border-radius:8px;text-align:center">
                            <div style="font-size:24px;font-weight:700;color:#3498db">${s.open_alerts}</div>
                            <div style="font-size:11px;color:#888">TOTAL OPEN ALERTS</div>
                        </div>
                        <div style="background:#f8f9fa;padding:12px;border-radius:8px;text-align:center">
                            <div style="font-size:24px;font-weight:700;color:#9b59b6">${s.pending_counts}</div>
                            <div style="font-size:11px;color:#888">PENDING COUNTS</div>
                        </div>
                    </div>
                    <p style="margin-top:12px;font-size:11px;color:#aaa">
                        Last snapshot: ${s.last_snapshot_at || "Never"} &nbsp;|&nbsp;
                        Last alert run: ${s.last_alert_run_at || "Never"} (${s.last_alert_status || "—"})
                    </p>
                `,
                indicator: "blue",
            });
        },
    });
}
