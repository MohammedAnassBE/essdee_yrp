const SMALL_WORDS = new Set(["of", "and", "&", "the", "for", "to", "in"])
/** Common abbreviations whose letters differ from the label's initials. */
const ALIASES = {
	po: "purchase order",
	wo: "work order",
	pi: "purchase invoice",
	ipd: "item production detail",
	cp: "cutting plan",
	fp: "finishing plan",
	ste: "stock entr",
	ppo: "production order",
	grn: "goods received note",
	dc: "delivery challan",
}
const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"])

const normalize = (value) => String(value || "").toLowerCase().trim()
const initials = (words) => words.map((word) => word[0]).join("")

function isAcronymMatch(query, label) {
	if (query.length < 2 || query.includes(" ")) return false
	const words = label.split(/[\s/-]+/).filter(Boolean)
	const significant = words.filter((word) => !SMALL_WORDS.has(word))
	return initials(words).startsWith(query) || initials(significant).startsWith(query)
		|| Boolean(ALIASES[query] && label.includes(ALIASES[query]))
}

/** 0 label prefix, 1 initials or alias, 2 every word in label or group, -1 no match. */
export function workspaceSearchRank(query, option) {
	const search = normalize(query)
	const label = normalize(option.label)
	if (!search || label.startsWith(search)) return 0
	if (isAcronymMatch(search, label)) return 1
	const text = `${label} ${normalize(option.group)}`
	return search.split(/\s+/).every((word) => text.includes(word)) ? 2 : -1
}

function rankedOptions(options, query) {
	return options
		.map((option, index) => ({ option, index, rank: workspaceSearchRank(query, option) }))
		.filter(({ rank }) => rank >= 0)
		.sort((left, right) => left.rank - right.rank || left.index - right.index)
		.map(({ option }) => option)
}

const cardOption = (card) => ({ type: "card", id: `card:${card.key}`, key: card.key, label: card.label, group: card.group || "", icon: card.icon || "pi pi-th-large" })
const reportOption = (report) => ({ type: "report", id: `report:${report.value}`, key: report.value, label: report.label, group: report.group || "", icon: report.icon || "pi pi-table" })

/** Cards and reports matching `query`, as non-empty "Cards" / "Reports" groups. */
export function workspaceSearchGroups(cards = [], reports = [], query = "") {
	return [
		{ label: "Cards", items: rankedOptions(cards.map(cardOption), query) },
		{ label: "Reports", items: rankedOptions(reports.map(reportOption), query) },
	].filter((group) => group.items.length)
}

export function visibleWorkspaceCards(cards = [], selectedKey = "") {
	const selected = cards.filter((card) => card.key === selectedKey)
	return selected.length ? selected : cards
}

/** The report page route the department's Reports card opens, set to one report. */
export function workspaceReportTarget(reportsTo, value, queryKey = "report") {
	const base = typeof reportsTo === "string" ? { path: reportsTo } : reportsTo
	return { ...base, query: { ...base.query, [queryKey]: value } }
}

export function isWorkspaceSearchShortcut(event) {
	const target = event.target
	if (target && (EDITABLE_TAGS.has(target.tagName) || target.isContentEditable)) return false
	const modified = Boolean(event.ctrlKey || event.metaKey)
	if (event.key === "/") return !modified && !event.altKey
	return modified && !event.altKey && String(event.key).toLowerCase() === "k"
}
