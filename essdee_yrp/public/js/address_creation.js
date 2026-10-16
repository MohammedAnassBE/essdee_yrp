(() => {
	const url = new URL(window.location.href);
	const supplier = url.searchParams.get("essdee_supplier");
	const title = url.searchParams.get("address_title");
	if (!supplier) return;
	let applied = false;
	function applySupplier(frm) {
		if (applied || !frm.is_new()) return;
		applied = true;
		if (!(frm.doc.links || []).some((row) => row.link_doctype === "Supplier" && row.link_name === supplier)) {
			frm.add_child("links", { link_doctype: "Supplier", link_name: supplier });
			frm.refresh_field("links");
		}
		if (title && !frm.doc.address_title) frm.set_value("address_title", title);
	}
	frappe.ui.form.on("Address", { onload: applySupplier, refresh: applySupplier });
})();
