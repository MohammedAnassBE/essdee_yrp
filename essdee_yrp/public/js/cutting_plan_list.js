frappe.listview_settings["SD YRP Cutting Plan"] = {
	add_fields: ["cp_status", "no_of_colours", "no_of_colours_completed"],
	get_indicator(doc) {
		const colours = {
			Draft: "gray",
			Planned: "blue",
			"Fabric Partially Received": "orange",
			"Ready to Cut": "purple",
			"Cutting In Progress": "yellow",
			"Partially Completed": "orange",
			Completed: "green",
			"Cut Panel Dispatch Pending": "red",
		};
		let label = doc.cp_status || "Draft";
		if (["Fabric Partially Received", "Partially Completed", "Cut Panel Dispatch Pending"].includes(label)) {
			label = `${label} - ${doc.no_of_colours_completed || 0}/${doc.no_of_colours || 0}`;
		}
		return [__(label), colours[doc.cp_status] || "gray", `cp_status,=,${doc.cp_status}`];
	},
};
