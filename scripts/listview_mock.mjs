export const USER_LISTVIEW_ROUTE = "**/api/method/essdee_yrp.api.list_columns.get_user_listview*"

const LAYOUT_FIELDTYPES = new Set([
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Table",
	"Table MultiSelect",
	"Fold",
	"Heading",
	"Image",
])

const STANDARD_FIELDS = [
	{ fieldname: "owner", fieldtype: "Link", label: "Created By", options: "User" },
	{ fieldname: "creation", fieldtype: "Datetime", label: "Created On", options: "" },
	{ fieldname: "modified_by", fieldtype: "Link", label: "Last Updated By", options: "User" },
	{ fieldname: "modified", fieldtype: "Datetime", label: "Last Updated On", options: "" },
]

/** Mirror of `essdee_yrp.api.list_columns.get_user_listview` built from mocked meta, with no saved columns. */
export function userListviewSettings(metaFields = [], { isSubmittable = false, columns = null, currencyFields = {} } = {}) {
	const visibleFields = metaFields.filter((field) => field.fieldname && !field.hidden && !LAYOUT_FIELDTYPES.has(field.fieldtype))
	const metaNames = new Set(visibleFields.map((field) => field.fieldname))
	const fields = [
		{ fieldname: "name", fieldtype: "Data", label: "ID", options: "" },
		...visibleFields,
		...STANDARD_FIELDS.filter((field) => !metaNames.has(field.fieldname)),
		...(isSubmittable ? [{ fieldname: "docstatus", fieldtype: "Int", label: "Document Status", options: "" }] : []),
	]
	return { fields, columns, currency_fields: currencyFields }
}

export function fulfillUserListview(route, metaFields, options) {
	return route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: userListviewSettings(metaFields, options) }),
	})
}
