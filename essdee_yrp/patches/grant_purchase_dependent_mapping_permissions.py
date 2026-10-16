from essdee_yrp.patches.grant_purchase_item_permissions import grant_permissions

PERMISSION_GRANTS = {
	"YRP Item Dependent Attribute Mapping": {
		"Purchase Manager": ("read", "create", "write", "delete"),
		"Item Manager": ("read", "create", "write", "delete"),
	},
}


def execute():
	grant_permissions(PERMISSION_GRANTS)
