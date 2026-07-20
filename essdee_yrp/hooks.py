app_name = "essdee_yrp"
app_title = "Essdee YRP"
app_publisher = "anas@essdee.fit"
app_description = "Essdee customization layer on the yrp app"
app_email = "anas@essdee.fit"
app_license = "mit"
required_apps = ["yrp"]

fixtures = [
	{
		"dt": "Custom Field",
		"or_filters": [
			[
				"name",
				"in",
				[
					"Item-product_category",
					"Item-is_cloth_item",
					"Supplier-apply_sewing_plan",
					"Process-additional_allowance",
					"Process-includes_packing",
					"Process-is_cloth_process",
					"Process-item",
				],
			],
			["dt", "=", "Item Production Detail"],
			["dt", "in", ["Production Order", "Production Order Detail"]],
		],
	},
	# Field-order override: keeps `ipd_processes` on the Item Details tab
	# (production_api parity) — the custom garment tabs would otherwise pull
	# it into the hidden-for-cloth Advance Settings tab.
	{
		"dt": "Property Setter",
		"filters": [
			["doc_type", "=", "Item Production Detail"],
			["property", "=", "field_order"],
		],
	},
	# /web role grants: base yrp leaves IPD System-Manager-only and Terms and
	# Condition without floor-role write — the /web UI needs both usable by the
	# floor roles, granted as Custom DocPerm (base yrp stays untouched).
	{
		"dt": "Custom DocPerm",
		"filters": [["parent", "in", ["Item Production Detail", "Terms and Condition"]]],
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
	{"dt": "UI Layout", "filters": [["disabled", "=", 0]]},
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
	"Lot",
	"Work Order",
	"Work Order Correction",
	"Delivery Challan",
	"Goods Received Note",
	"Stock Entry",
	"Item",
	"Item Production Detail",
	"Terms and Condition",
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
app_include_js = ["essdee_yrp.bundle.js"]

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
	"Item Production Detail": "public/js/item_production_detail.js",
	"Production Order": "public/js/production_order.js",
	"Work Order": "public/js/work_order.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Delivery Challan": "public/js/delivery_challan.js",
	"Goods Received Note": "public/js/goods_received_note.js",
	"Stock Entry": "public/js/stock_entry.js",
}
doctype_list_js = {"Item Production Detail": "public/js/item_production_detail_list.js"}
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
# jinja = {
# 	"methods": "essdee_yrp.utils.jinja_methods",
# 	"filters": "essdee_yrp.utils.jinja_filters"
# }

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

# after_build = "essdee_yrp.build.after_build"

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
	"Item Production Detail": {
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
	"Work Order": {
		"validate": "essdee_yrp.work_order_hooks.validate",
	},
	"Work Order Correction": {
		"before_submit": "essdee_yrp.work_order_correction_hooks.validate_correction_ipd_items"
	},
	"Goods Received Note": {
		"on_submit": "essdee_yrp.fabric_tracking.on_grn_submit",
		"on_cancel": "essdee_yrp.fabric_tracking.on_grn_cancel",
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

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "essdee_yrp.event.get_events"
# }
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
