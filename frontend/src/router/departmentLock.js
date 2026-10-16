import { departments } from "../departments/registry.js"

/** Department a user's registered YRP UI Layout locks /web to, or null for the full workspace view. */
export function getLockedDepartment(boot) {
	const meta = boot?.ui_config?.meta
	if (meta?.render_mode !== "Registered Experience") return null
	const department = departments.find((item) => item.key === meta.experience_key)
	if (!department) console.warn(`/web: no department for experience "${meta.experience_key}"; showing all workspaces`)
	return department || null
}

export const lockedDepartment = getLockedDepartment(globalThis.window?.frappe?.boot)

/** Redirect for the workspaces page or another department's landing page; deep links stay open. */
export function getLockedRedirect(path, department = lockedDepartment) {
	const landingPath = path.toLowerCase().replace(/\/+$/, "") || "/"
	if (!department || landingPath === department.path) return undefined
	const isLanding = landingPath === "/" || departments.some((item) => item.path === landingPath)
	return isLanding ? { path: department.path, replace: true } : undefined
}

export function isLockedExit(path, department = lockedDepartment) {
	return Boolean(department) && path === "/"
}

export function getHomePath(department = lockedDepartment) {
	return department?.path || "/"
}
