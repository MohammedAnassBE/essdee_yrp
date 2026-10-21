import { departments, getWorkspacePaths } from "../departments/registry.js"

export const LAYOUT_UNAVAILABLE_PATH = "/not-in-your-layout"

/** Department and workspace keys a user's registered YRP UI Layout narrows /web to, or null for the full permission-based view. */
export function getLockedDepartment(boot) {
	const uiConfig = boot?.ui_config
	const meta = uiConfig?.meta
	if (meta?.render_mode !== "Registered Experience") return null
	const department = departments.find((item) => item.key === meta.experience_key)
	if (!department) {
		console.warn(`/web: no department for experience "${meta.experience_key}"; showing all workspaces`)
		return null
	}
	const workspaces = uiConfig.config?.experience_props?.workspaces
	return { ...department, workspaces: Array.isArray(workspaces) ? workspaces : Object.keys(getWorkspacePaths(department)) }
}

export const lockedDepartment = getLockedDepartment(globalThis.window?.frappe?.boot)

function getSegments(target) {
	return String((typeof target === "string" ? target : target?.path) || "").toLowerCase().split(/[?#]/)[0].split("/").filter(Boolean)
}

/** Whether a navigation page at `path` (string or route location) is hidden by the layout: another department, or a section no listed workspace owns. Document pages stay open so cross-department links work. */
export function isOutsideLayout(path, department = lockedDepartment, isDocument = false) {
	if (!department || isDocument) return false
	const [first, segment] = getSegments(path)
	if (!departments.some((item) => item.path === `/${first}`)) return false
	if (!segment) return `/${first}` !== department.path
	const paths = getWorkspacePaths(department)
	return !department.workspaces.some((key) => paths[key]?.includes(`/${first}/${segment}`))
}

/** Whether `path` is the landing page of a department the layout's department combines. */
function isCombinedLanding(path, department) {
	return (department.combines || []).some((key) => departments.find((item) => item.key === key)?.path === path)
}

/** Whether a launcher card belongs to the user's layout. */
export function isWorkspaceInLayout(item, department = lockedDepartment) {
	return !isOutsideLayout(item.to, department)
}

/** Guard result: the workspaces page goes to the layout's department; navigation pages outside the layout show the layout notice. */
export function getLockedRedirect(to, department = lockedDepartment) {
	if (!department) return undefined
	const path = to.path.toLowerCase().replace(/\/+$/, "") || "/"
	if (path === "/" || isCombinedLanding(path, department)) return { path: department.path, replace: true }
	const isDocument = Object.keys(to.params || {}).some((key) => key !== "pathMatch")
	if (!isOutsideLayout(path, department, isDocument)) return undefined
	return { path: LAYOUT_UNAVAILABLE_PATH, query: { from: to.fullPath || to.path }, replace: true }
}

/** Whether a back link would leave the layout. */
export function isLockedExit(path, department = lockedDepartment) {
	return Boolean(department) && (path === "/" || isOutsideLayout(path, department)) && !isCombinedLanding(path, department)
}

export function getHomePath(department = lockedDepartment) {
	return department?.path || "/"
}
