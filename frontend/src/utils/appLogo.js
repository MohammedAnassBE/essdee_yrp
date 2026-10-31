/** Desk's app logo URL from boot (frappe get_app_logo), or "" to keep the monogram. */
export function getAppLogo(boot = globalThis.window?.frappe?.boot) {
	const logo = boot?.app_logo
	return typeof logo === "string" ? logo.trim() : ""
}
