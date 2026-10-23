/** "work-orders" -> "Work Orders". */
export function titleCase(segment = "") {
	return String(segment).split("-").filter(Boolean).map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ")
}

/** "Work Orders" -> "Work Order", "Dispatches" -> "Dispatch". */
export function singularLabel(label = "") {
	if (/(ch|sh|ss|x)es$/i.test(label)) return label.slice(0, -2)
	if (/ies$/i.test(label)) return `${label.slice(0, -3)}y`
	if (/[^s]s$/i.test(label)) return label.slice(0, -1)
	return label
}

function documentName(params = {}) {
	const names = Object.entries(params)
		.filter(([key, value]) => key !== "pathMatch" && typeof value === "string" && value)
		.map(([, value]) => value)
	return names.at(-1) || ""
}

/** Desk-style tab title from the route alone: document name, "New <Doctype>", list label or department name. */
export function routeTitle(route, departments = []) {
	if (route.name === "administrator" || route.path === "/") return "Workspaces"
	const department = departments.find((item) => item.path === route.path)
	if (department) return department.label
	if (route.meta?.title) return route.meta.title
	if (route.params?.pathMatch !== undefined) return "Not Found"
	const segments = route.path.split("/").filter(Boolean)
	if (segments.at(-1) === "new") return `New ${singularLabel(titleCase(segments.at(-2)))}`
	return documentName(route.params) || titleCase(segments.at(-1)) || "Essdee YRP"
}

/** A page-reported title wins while it belongs to the current path. */
export function resolvePageTitle(route, departments = [], reported = null) {
	if (reported?.title && reported.path === route.path) return reported.title
	return routeTitle(route, departments)
}
