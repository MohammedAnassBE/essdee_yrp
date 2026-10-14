def autoname(doc):
	if doc.supplier:
		doc.name = doc.warehouse_name.strip()
