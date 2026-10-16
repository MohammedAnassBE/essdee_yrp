const STATE_ICONS = {
	done: "pi pi-check-circle",
	attention: "pi pi-exclamation-circle",
	off: "pi pi-minus-circle",
	not_started: "pi pi-circle",
	locked: "pi pi-lock",
}
const STATE_TEXT = { done: "Complete", attention: "Needs attention", off: "Off", not_started: "Not started", locked: "Locked" }

export function reviewSummary(sections, states) {
	return sections.filter((section) => section.key !== "review").map((section) => {
		const state = states[section.key]?.state || "not_started"
		const hint = states[section.key]?.hint || ""
		const text = state === "attention" ? hint : [STATE_TEXT[state], state === "done" && hint && hint !== "done" ? hint : ""].filter(Boolean).join(" · ")
		return { key: section.key, number: section.number, label: section.label, state, icon: STATE_ICONS[state] || STATE_ICONS.not_started, text }
	})
}
