from essdee_yrp.patches.grant_purchase_item_permissions import grant_permissions

PERMISSION_GRANTS = {
	"UOM": {"Purchase Manager": ("read", "select")},
	"SD YRP Product Category": {
		"Purchase Manager": ("read", "select"),
		"Item Manager": ("read", "select"),
	},
}
LEVEL_ONE_GRANTS = {
	"Item": {
		"Purchase Manager": ("read", "write"),
		"Item Manager": ("read", "write"),
	},
}


def execute():
	grant_permissions(PERMISSION_GRANTS)
	grant_permissions(LEVEL_ONE_GRANTS, permlevel=1)
