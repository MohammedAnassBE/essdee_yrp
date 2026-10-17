import frappe


def execute():
	"""Size Type slots are 'size 1' to 'size 10'; earlier rows stored 'size1' to 'size10'."""
	detail = frappe.qb.DocType("SD YRP FG Item Size Type Detail")
	for index in range(1, 11):
		frappe.qb.update(detail).set(detail.size, f"size {index}").where(detail.size == f"size{index}").run()
