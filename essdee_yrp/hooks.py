app_name = "essdee_yrp"
app_title = "Essdee YRP"
app_publisher = "anas@essdee.fit"
app_description = "Essdee customization layer on the yrp app"
app_email = "anas@essdee.fit"
app_license = "mit"
required_apps = ["yrp"]

# Code-owned downstream extensions for the base /web registry. Layout JSON may
# reference these safe keys but cannot supply executable methods itself.
yrp_ui_metrics = ["essdee_yrp.ui_registry.get_metrics"]
yrp_ui_calculations = ["essdee_yrp.ui_registry.get_calculations"]
# Base YRP validates only inert action identifiers. The Essdee /web host owns
# their visual implementation and therefore contributes its complete safe
# vocabulary here instead of hardcoding business actions in the base app.
yrp_ui_actions = [
	"create_grn",
	"create_dc",
	"complete_transfer",
	"build_cloth_programs",
	"more_menu",
	"ewaybill_menu",
	"send_sms",
	"send_whatsapp",
	"cancel_doc",
]
yrp_stock_item_entry_fields = ["essdee_yrp.stock_item_extensions.get_entry_fields"]

fixtures = [
	# Export only fields explicitly owned by this customization app. A patch
	# stamps the historical fields before this strict filter is used.
	{
		"dt": "Custom Field",
		"filters": [["module", "=", "Essdee YRP"]],
	},
	# Field-order override: keeps `ipd_processes` on the Item Details tab
	# (production_api parity) — the custom garment tabs would otherwise pull
	# it into the hidden-for-cloth Advance Settings tab.
	{
		"dt": "Property Setter",
		"filters": [
			[
				"name",
				"in",
				[
					"YRP Item Production Detail-main-field_order",
					"YRP Work Order-naming_series-options",
					"YRP Work Order-naming_series-default",
					"YRP Delivery Challan-from_location-fetch_from",
					"YRP Delivery Challan-from_location-reqd",
					"YRP Delivery Challan-is_rework-fetch_from",
					"YRP Delivery Challan-is_rework-fetch_if_empty",
					"YRP Delivery Challan-ste_transferred-depends_on",
					"YRP Delivery Challan-ste_transferred-precision",
					"YRP Delivery Challan-transfer_complete-depends_on",
					"YRP Delivery Challan-vehicle_no-allow_on_submit",
					"YRP Delivery Challan Item-secondary_qty-precision",
					"YRP Goods Received Note-naming_series-options",
					"YRP Goods Received Note-naming_series-default",
					"YRP Stock Entry-naming_series-options",
					"YRP Stock Entry-naming_series-default",
					"YRP Stock Entry-additional_amount-read_only_depends_on",
					"YRP Stock Entry-purpose-options",
					"YRP Process Cost-naming_series-options",
					"YRP Process Cost-naming_series-default",
					"YRP Process Cost-approved_by-read_only",
					"YRP Process Cost-attribute-mandatory_depends_on",
					"YRP Process Cost-depends_on_attribute-read_only",
					"YRP Process Cost-depends_on_attribute-default",
					"YRP Process Cost-is_expired-read_only",
					"YRP Process Cost-item-fetch_from",
					"YRP Purchase Order-naming_series-options",
					"YRP Purchase Order-naming_series-default",
					"YRP Purchase Invoice-naming_series-options",
					"YRP Purchase Invoice-naming_series-default",
					"YRP Purchase Invoice Item-item_group-reqd",
					"YRP Production Ordered Detail-quantity-fieldtype",
					"YRP Stock Reconciliation-naming_series-options",
					"YRP Stock Reconciliation-naming_series-default",
					"YRP Stock Update-naming_series-options",
					"YRP Stock Update-naming_series-default",
					"YRP Item Price-main-autoname",
					"YRP Stock Ledger Entry-main-autoname",
					"YRP Stock Reservation Entry-main-autoname",
					"YRP Stock Reservation Entry-voucher_type-options",
				],
			],
		],
	},
	# /web role grants: base yrp leaves IPD System-Manager-only and Terms and
	# Condition without floor-role write — the /web UI needs both usable by the
	# floor roles, granted as Custom DocPerm (base yrp stays untouched).
	{
		"dt": "Custom DocPerm",
		"filters": [["parent", "in", [
			'YRP Item Production Detail',
			'YRP Terms and Condition',
			'SD YRP Sewing Plan Entry Detail',
		]]],
	},
	# /web per-user UI (spec §12.2): the code-owned layouts shipped to every site.
	# THE FILTER IS LOAD-BEARING — sync_fixtures force-imports on every
	# `bench migrate`, so an unfiltered fixture would silently revert every
	# same-named prod-edited layout and ship stray dev test layouts. Names listed
	# here are therefore CODE-OWNED: never edit them live on prod (a migrate
	# reverts the change) — duplicate to a new name instead. Per-user assignment
	# (YRP UI Preference) is NOT fixtured, so who-gets-which stays prod-owned.
	# 2026-07-20 (owner): ship ALL enabled layouts (status = Enabled), not a name
	# list. `disabled = 0` — so any enabled layout on the exporting site is
	# captured; disabled layouts (dev drills, unfinished templates) stay out.
	{"dt": 'YRP UI Layout', "filters": [["disabled", "=", 0]]},
]

# Apps
# ------------------

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "essdee_yrp",
		"logo": "/assets/essdee_yrp/frontend/favicon.png",
		"title": "Essdee YRP",
		"route": "/web",
	}
]

# /web SPA catch-all: deep links under /web (the Vue router runs in history mode
# with base "/web") all resolve to the web.html template, which boots the SPA.
website_route_rules = [
	{"from_route": "/web/<path:app_path>", "to_route": "web"},
]

# /web DocType catalog for base yrp's UI-config validation (USE_CASE §4 item
# 17): ui_config.validate_config reads this hook to warn at save/lint time on
# nav / quickCreate / newCta / listViews doctypes the SPA cannot route.
# CHECKLIST RULE (same as www/web.py WEB_DOCTYPES, which mirrors
# frontend/src/config/doctypes.js GROUPS): all three lists change together.
yrp_web_doctype_catalog = [
	'SD YRP Lot',
	'YRP Work Order',
	'YRP Work Order Correction',
	'YRP Delivery Challan',
	'YRP Goods Received Note',
	'YRP Process Cost',
	'SD YRP Lot Transfer',
	'YRP Stock Entry',
	'YRP Item',
	'YRP Item Production Detail',
	'YRP Terms and Condition',
]

# Post-login landing: ordinary users land on the custom /web work hub;
# System Manager / Administrator keep the Desk default (function returns None
# for them, so Frappe falls through). See essdee_yrp/www_home.py.
get_website_user_home_page = "essdee_yrp.www_home.get_website_user_home_page"

# Desk gate: non-(System Manager/Administrator) users are 302'd from
# /app|/apps|/desk|/ to /web. See essdee_yrp/auth.py.
before_request = ["essdee_yrp.auth.block_desk_for_non_managers"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/essdee_yrp/css/essdee_yrp.css"
app_include_js = [
	"essdee_yrp.bundle.js",
	"assets/essdee_yrp/node_modules/frappe-gantt/dist/frappe-gantt.min.js",
]
app_include_css = [
	"assets/essdee_yrp/node_modules/frappe-gantt/dist/frappe-gantt.min.css"
]

# include js, css files in header of web template
# web_include_css = "/assets/essdee_yrp/css/essdee_yrp.css"
# web_include_js = "/assets/essdee_yrp/js/essdee_yrp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "essdee_yrp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	'YRP Item': "public/js/item.js",
	'YRP Item Production Detail': "public/js/item_production_detail.js",
	'YRP Production Order': [
		"public/js/production_order.js",
		"public/js/production_order_workflow.js",
	],
	'YRP Work Order': "public/js/work_order.js",
	'YRP Purchase Order': "public/js/purchase_order.js",
	'YRP Delivery Challan': "public/js/delivery_challan.js",
	'YRP Goods Received Note': "public/js/goods_received_note.js",
	'YRP Purchase Invoice': "public/js/purchase_invoice.js",
	'YRP Item BOM Attribute Mapping': "public/js/item_bom_attribute_mapping.js",
	'YRP Process Cost': "public/js/process_cost.js",
	'SD YRP Finishing Plan': "public/js/finishing_plan.js",
	# List form: both scripts load for Stock Entry. The guard hides the desk Cancel
	# action on transfer SEs (source_grn set); see the JS file for the mechanism.
	'YRP Stock Entry': [
		"public/js/stock_entry.js",
		"public/js/stock_entry_transfer_cancel_guard.js",
	],
}
doctype_list_js = {
	'SD YRP Cutting Plan': "public/js/cutting_plan_list.js",
	'YRP Item Production Detail': "public/js/item_production_detail_list.js",
	'YRP Production Order': "public/js/production_order_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "essdee_yrp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": [
		"essdee_yrp.print_helpers.get_created_date",
		"essdee_yrp.print_helpers.get_current_user_time",
		"essdee_yrp.print_helpers.get_user_signature",
		"essdee_yrp.print_helpers.get_ipd_pf_details",
		"essdee_yrp.print_helpers.fetch_stock_entry_items",
		"essdee_yrp.print_helpers.fetch_grn_purchase_item_details",
		"essdee_yrp.print_helpers.get_dc_structure",
		"essdee_yrp.print_helpers.fetch_order_item_details",
		"essdee_yrp.print_helpers.fetch_item_details",
		"essdee_yrp.print_helpers.check_key_value_in_dict_or_list_of_dict",
		"essdee_yrp.print_helpers.parse_json",
		"essdee_yrp.print_helpers.get_item_from_variant",
		"essdee_yrp.print_helpers.get_cloth_program_print_data",
		"essdee_yrp.print_helpers.get_supplier_address_display",
		"essdee_yrp.print_helpers.get_warehouse_name",
		"essdee_yrp.print_helpers.get_warehouse_address_display",
		"essdee_yrp.ipd_ui.fetch_combination_items",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_dict_object",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_mapping_details",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_ipd_print_accessory_combination",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_consumption_sheet_data",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_shortened_link.sd_yrp_shortened_link.get_short_link",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product.get_latest_product_images",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product.get_product_colour_codes",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_panels",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_bundle_items",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_colours",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_cutting_plan_laysheets_report",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_cutting_plan_size_reports",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_ccr",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.remove_empty_rows",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order.sd_yrp_cutting_order.get_cutting_order_laysheets_report",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order.sd_yrp_cutting_order.get_cutting_order_size_reports",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order.sd_yrp_cutting_order.get_cutting_order_ccr",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker.get_panels_and_size",
		"essdee_yrp.production_order_workflow.get_production_order_details",
		"essdee_yrp.finishing.inward.get_finishing_plan_inward_details",
		"essdee_yrp.finishing.ocr.get_fp_ocr_details",
		"essdee_yrp.finishing.ocr.get_ocr_percentage",
		"essdee_yrp.finishing.ocr.get_ocr_style",
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch.sd_yrp_finishing_plan_dispatch.get_fpd_print_data",
		"essdee_yrp.sewing.read_models.get_sewing_consumption_print_data",
		"essdee_yrp.sewing.read_models.get_monthly_summary_print_data",
	],
}

# Installation
# ------------

# before_install = "essdee_yrp.install.before_install"
after_install = "essdee_yrp.setup.after_install"

# Consumer-site setup (recreate records ERPNext's setup wizard would install).
after_migrate = "essdee_yrp.setup.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "essdee_yrp.uninstall.before_uninstall"
# after_uninstall = "essdee_yrp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "essdee_yrp.utils.before_app_install"
# after_app_install = "essdee_yrp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "essdee_yrp.utils.before_app_uninstall"
# after_app_uninstall = "essdee_yrp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# Rebuild the /web Vite SPA whenever `bench build` runs. `after_migrate` is the
# guaranteed deploy trigger (see setup.after_migrate); this covers `bench build`
# too. Both call the same source-hash-gated, never-raises helper.
after_build = "essdee_yrp.web_build.build_web_spa"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "essdee_yrp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	'YRP Production Order': {
		"onload": "essdee_yrp.production_order_workflow.onload",
		"before_validate": "essdee_yrp.production_order_workflow.before_validate",
		"validate": "essdee_yrp.production_order_workflow.validate",
		"before_update_after_submit": "essdee_yrp.production_order_workflow.before_update_after_submit",
		"before_submit": "essdee_yrp.production_order_workflow.before_submit",
		"on_submit": "essdee_yrp.production_order_workflow.on_submit",
		"before_cancel": "essdee_yrp.production_order_workflow.before_cancel",
	},
	'YRP Work Station': {
		"before_validate": "essdee_yrp.time_and_action.work_station.validate_default_action_work_station",
	},
	'YRP Purchase Order': {
		"before_validate": "essdee_yrp.purchase_order_lots.sync_linked_lots",
	},
	'YRP Item': {
		"validate": "essdee_yrp.item_validations.validate",
	},
	'YRP Item Production Detail': {
		"onload": "essdee_yrp.ipd_ui.onload",
		"before_validate": [
			"essdee_yrp.ipd_validations.before_validate",
			"essdee_yrp.fabric_ipd.ensure_cloth_item_attributes",
		],
		"validate": "essdee_yrp.ipd_validations.validate",
		"on_update": [
			"essdee_yrp.ipd_validations.on_update",
			"essdee_yrp.fabric_ipd.sync_fabric_process_matrices",
			# order matters: the plan solver reads the matrices rebuilt above
			"essdee_yrp.fabric_plan.on_ipd_update",
		],
		"on_trash": "essdee_yrp.ipd_validations.on_trash",
	},
	'YRP Work Order': {
		"before_print": "essdee_yrp.print_helpers.prepare_print_document",
		"onload": "essdee_yrp.work_order_hooks.onload",
		"validate": "essdee_yrp.work_order_hooks.validate",
		"before_cancel": "essdee_yrp.sewing.plan.before_work_order_cancel",
		"on_submit": [
			"essdee_yrp.finishing.work_order.on_submit",
			"essdee_yrp.sewing.plan.on_work_order_submit",
			"essdee_yrp.finishing.rebuild.on_work_order_lifecycle_change",
		],
		"on_cancel": [
			"essdee_yrp.finishing.work_order.on_cancel",
			"essdee_yrp.sewing.plan.on_work_order_cancel",
			"essdee_yrp.finishing.rebuild.on_work_order_lifecycle_change",
		],
	},
	'YRP Delivery Challan': {
		"before_print": "essdee_yrp.print_helpers.prepare_print_document",
		"after_insert": "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.sd_yrp_cutting_bulk_lay_sheets.record_delivery_challan",
		"onload": "essdee_yrp.delivery_challan_hooks.onload",
		"before_validate": "essdee_yrp.delivery_challan_hooks.before_validate",
		"before_cancel": "essdee_yrp.cutting.movement.before_cancel",
		"on_submit": [
			"essdee_yrp.cutting.movement.on_submit",
			"essdee_yrp.work_order_piece_tracking.on_delivery_challan_submit",
			"essdee_yrp.finishing.delivery_challan.on_submit",
			"essdee_yrp.delivery_challan_hooks.sync_cutting_plan_received_cloth",
		],
		"on_cancel": [
			"essdee_yrp.cutting.movement.on_cancel",
			"essdee_yrp.work_order_piece_tracking.on_delivery_challan_cancel",
			"essdee_yrp.finishing.delivery_challan.on_cancel",
			"essdee_yrp.delivery_challan_hooks.sync_cutting_plan_received_cloth",
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.sd_yrp_cutting_bulk_lay_sheets.refresh_linked_bulk_status",
		],
	},
	'YRP Work Order Correction': {
		"before_submit": "essdee_yrp.work_order_correction_hooks.validate_correction_ipd_items"
	},
	'YRP Goods Received Note': {
		"before_print": "essdee_yrp.print_helpers.prepare_print_document",
		"before_validate": [
			"essdee_yrp.packing_hooks.set_grn_includes_packing",
			# Calculated-input availability is intentionally not a Draft Save
			# validation. EssdeeGoodsReceivedNote.before_submit locks the Work
			# Order and rebuilds the cutting/packing/stitching/identity/fabric
			# plan before any stock or valuation side effect.
			"essdee_yrp.purchase_order_lots.validate_grn_lots",
			"essdee_yrp.cutting.movement.validate_transaction_link",
		],
		"before_cancel": [
			"essdee_yrp.finishing.grn.before_cancel",
			"essdee_yrp.cutting.movement.before_cancel",
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item.before_grn_cancel",
		],
		"on_submit": [
			"essdee_yrp.fabric_grn.on_submit",
			"essdee_yrp.fabric_tracking.on_grn_submit",
			"essdee_yrp.finishing.grn.on_submit",
			"essdee_yrp.cutting.movement.on_submit",
			"essdee_yrp.work_order_piece_tracking.on_goods_received_note_submit",
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item.sync_grn_rework",
		],
		"on_cancel": [
			"essdee_yrp.fabric_grn.on_cancel",
			"essdee_yrp.fabric_tracking.on_grn_cancel",
			"essdee_yrp.finishing.grn.on_cancel",
			"essdee_yrp.cutting.movement.on_cancel",
			"essdee_yrp.work_order_piece_tracking.on_goods_received_note_cancel",
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item.on_grn_cancel",
		],
	},
	# A Stock Entry created by the cross-bench GRN transfer (source_grn set) may be
	# cancelled ONLY by the mrp GRN-cancel flow (cancel_grn_transfer sets
	# doc.flags.from_grn_transfer). Blocks every other cancel path server-side so the
	# UI hide (public/js/stock_entry_transfer_cancel_guard.js) cannot be bypassed.
	'YRP Stock Entry': {
		"before_print": "essdee_yrp.print_helpers.prepare_print_document",
		"onload": "essdee_yrp.stock_entry_hooks.onload",
		"before_validate": [
			"essdee_yrp.packing_hooks.set_stock_entry_includes_packing",
			"essdee_yrp.stock_entry_hooks.before_validate",
		],
		"validate": "essdee_yrp.stock_entry_hooks.validate",
		"before_submit": "essdee_yrp.stock_entry_hooks.before_submit",
		"on_submit": "essdee_yrp.stock_entry_hooks.on_submit",
		"before_cancel": [
			"essdee_yrp.api.stock_transfer.guard_transfer_se_cancel",
			"essdee_yrp.cutting.movement.before_cancel",
		],
		"on_cancel": "essdee_yrp.stock_entry_hooks.on_cancel",
	},
	'YRP Stock Reconciliation': {
		"onload": "essdee_yrp.stock_reconciliation_hooks.onload",
	},
	'SD YRP Lot Transfer': {
		"on_submit": [
			"essdee_yrp.finishing.old_lot.on_lot_transfer_submit",
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.sd_yrp_cutting_bulk_lay_sheets.refresh_linked_bulk_status",
		],
		"on_cancel": [
			"essdee_yrp.finishing.old_lot.on_lot_transfer_cancel",
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.sd_yrp_cutting_bulk_lay_sheets.refresh_linked_bulk_status",
		],
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"essdee_yrp.tasks.all"
# 	],
# 	"daily": [
# 		"essdee_yrp.tasks.daily"
# 	],
# 	"hourly": [
# 		"essdee_yrp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"essdee_yrp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"essdee_yrp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "essdee_yrp.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "essdee_yrp.custom.task.CustomTaskMixin"
# }

# Base YRP owns ordinary GRNs. This subclass activates only the Essdee
# Finishing return transaction (is_return), including its two-warehouse stock
# movement and Work Order Deliverable reversal.
override_doctype_class = {
	'YRP Delivery Challan': "essdee_yrp.overrides.delivery_challan.EssdeeDeliveryChallan",
	'YRP Goods Received Note': "essdee_yrp.overrides.goods_received_note.EssdeeGoodsReceivedNote",
	'YRP Item Production Detail': "essdee_yrp.overrides.item_production_detail.EssdeeItemProductionDetail",
	'YRP Purchase Invoice': "essdee_yrp.overrides.purchase_invoice.EssdeePurchaseInvoice",
	'YRP Work Order': "essdee_yrp.overrides.work_order.EssdeeWorkOrder",
}

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	# ERP's existing PI hooks call the production_api-era Bill Tracking routes.
	# Keep those stable while adapting their ERP PI name to F16's local PI Link.
	"production_api.production_api.doctype.vendor_bill_tracking.vendor_bill_tracking.close_vendor_bill":
		"essdee_yrp.erp_purchase_invoice.close_bill_tracking_from_erp",
	"production_api.production_api.doctype.vendor_bill_tracking.vendor_bill_tracking.revert_purchase_invoice_link":
		"essdee_yrp.erp_purchase_invoice.revert_bill_tracking_from_erp",
	# Work Order bills are edited as finished-piece process rows while their
	# hidden base rows preserve the exact physical GRN valuation lineage.
	"yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.fetch_grn_details":
		"essdee_yrp.purchase_invoice.fetch_grn_details",
	# Base intentionally offers zero-pending Work Order rows for excess DCs, but
	# its grouped editor also uses pending as the input maximum. The Essdee
	# adapter removes only that zero maximum while retaining server authority.
	"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan.get_work_order_defaults":
		"essdee_yrp.work_order_actions.get_delivery_challan_defaults",
	# Base YRP's Desk button calls this path. Route it through the
	# Essdee-owned close implementation so Desk and /web use one stock contract.
	"yrp.yrp.doctype.yrp_work_order.yrp_work_order.update_stock":
		"essdee_yrp.work_order_close.close_work_order",
	# Internal-unit GRNs live in Transit Warehouse until Complete Transfer;
	# inspection must classify the bin that actually holds the stock.
	"yrp.yrp.doctype.yrp_inspection_entry.yrp_inspection_entry.get_initial_payload":
		"essdee_yrp.overrides.inspection_entry.get_initial_payload",
	# Migrated garment receivables may have one saved row_index per size.
	# Normalize copied GRN defaults so the editable matrix renders one logical
	# SKU row with all sizes, without rewriting the Work Order source rows.
	"yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note.get_work_order_defaults":
		"essdee_yrp.overrides.goods_received_note.get_work_order_defaults",
	# Base's generic attribute callback runs alongside the Essdee Desk handler.
	# Route it here so an item-only response cannot race the Lot/IPD response.
	"yrp.yrp.doctype.yrp_process_cost.yrp_process_cost.get_pc_attribute_values":
		"essdee_yrp.process_cost.get_pc_attribute_values",
	# The generic popup already subtracts inspection and prior Work Order
	# consumption. Also subtract Essdee's direct Rework Details conversions.
	"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_rework_source_rows":
		"essdee_yrp.rework_work_order.get_rework_source_rows",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "essdee_yrp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["essdee_yrp.utils.before_request"]
# after_request = ["essdee_yrp.utils.after_request"]

# Job Events
# ----------
# before_job = ["essdee_yrp.utils.before_job"]
# after_job = ["essdee_yrp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"essdee_yrp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
