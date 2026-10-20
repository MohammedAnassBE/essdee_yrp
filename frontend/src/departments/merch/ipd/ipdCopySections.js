export function copyDialogSections(sections) {
	return sections.flatMap((section) => {
		const label = { attributes: "Item attributes", processes: "Processes" }[section.key] || section.label
		const row = { ...section, label, note: section.locked ? "always copied" : "" }
		if (section.key !== "processes") return [row]
		return [row, { key: "embellishment", copyKey: "processes", label: "Emblishment", locked: true,
			note: section.locked ? "always copied" : "copied with Processes", meta: "" }]
	})
}
