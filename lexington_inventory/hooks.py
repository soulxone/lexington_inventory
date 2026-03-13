app_name = "lexington_inventory"
app_title = "Lexington Inventory Monitor"
app_publisher = "Welchwyse"
app_description = "Real-time inventory monitoring, cycle counts, low-stock alerts, and supplier reorder for Lexington / Welchwyse warehouse"
app_email = "admin@welchwyse.com"
app_license = "MIT"

# ── Document events ────────────────────────────────────────────────────────────
doc_events = {
    # When a Stock Entry (Receipt/Transfer/Issue) is submitted, update alert thresholds
    "Stock Entry": {
        "on_submit": "lexington_inventory.lexington_inventory.stock_events.on_stock_entry_submit",
    },
    # When a Purchase Receipt is submitted, clear pending reorder alerts
    "Purchase Receipt": {
        "on_submit": "lexington_inventory.lexington_inventory.stock_events.on_purchase_receipt_submit",
    },
    # Inventory Count submitted → post Stock Reconciliation
    "Inventory Count": {
        "on_submit": "lexington_inventory.lexington_inventory.count_reconciler.on_count_submit",
    },
}

# ── Scheduled tasks ────────────────────────────────────────────────────────────
scheduler_events = {
    "daily": [
        # Check all items against reorder levels, create Inventory Alerts
        "lexington_inventory.lexington_inventory.alert_engine.run_daily_stock_check",
    ],
    "cron": {
        # Refresh live stock snapshot every hour
        "0 * * * *": [
            "lexington_inventory.lexington_inventory.alert_engine.refresh_stock_snapshot",
        ],
    },
}

# ── Fixtures ──────────────────────────────────────────────────────────────────
fixtures = [
    # Default singleton settings
    {
        "doctype": "Inventory Monitor Settings",
        "filters": []
    },
    # Workspace
    {
        "doctype": "Workspace",
        "filters": [["name", "in", ["Lexington Inventory"]]]
    },
    # Custom Fields added to ERPNext Item and Purchase Order
    {
        "doctype": "Custom Field",
        "filters": [
            ["name", "in", [
                "Item-lim_reorder_level",
                "Item-lim_reorder_qty",
                "Item-lim_preferred_supplier",
                "Item-lim_cycle_count_frequency",
                "Item-lim_last_count_date",
                "Item-lim_section",
                "Purchase Order-lim_auto_generated",
                "Purchase Order-lim_alert_ref",
            ]]
        ]
    },
]

# ── DocType JS overrides ────────────────────────────────────────────────────────
# Adds "Inventory Monitor" tab on Item form, alert banner on low-stock items
doctype_js = {
    "Item":             "public/js/item_monitor.js",
    "Purchase Order":   "public/js/purchase_order_monitor.js",
    "Stock Entry":      "public/js/stock_entry_monitor.js",
}

# ── Desktop Icons / Workspace ──────────────────────────────────────────────────
# Role-based home page — Warehouse managers land on Lexington Inventory workspace
# home_page = "Lexington Inventory"  # uncomment if warehouse role should see this by default
