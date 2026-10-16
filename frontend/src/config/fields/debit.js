/** Debit — compact request form opened directly from a Work Order. */

const detailGroups = [
	{
		label: "Debit",
		fields: ["work_order", "debit_type", "debit_no", "debit_value", "reason", "debit_document"],
	},
	{
		label: "Approval",
		fields: ["status", "approved_by", "inspection", "on_close", "amended_from"],
	},
]

const formOrder = [
	"work_order",
	"debit_type",
	"debit_no",
	"debit_value",
	"reason",
	"debit_document",
]

const hideFormFields = ["status", "approved_by", "inspection", "on_close", "amended_from"]

const help = {
	work_order: "The Work Order against which this debit is raised.",
	debit_value: "Enter the debit amount.",
	reason: "Explain why the debit is being raised.",
}

export default { detailGroups, formOrder, hideFormFields, help }
