export const AVATAR_TONE_COUNT = 8

/** Frappe's get_abbr: first letter of the first `maxLength` words, "?" when empty. */
export function getAbbreviation(text, maxLength = 2) {
	const words = String(text || "").split(" ").map((word) => word.trim()).filter(Boolean)
	return words.slice(0, maxLength).map((word) => word[0]).join("") || "?"
}

/** Stable 0..7 colour slot for a name, so a user keeps the same avatar colour. */
export function getAvatarTone(text) {
	let hash = 0
	for (const character of String(text || "")) hash = (hash * 31 + character.codePointAt(0)) >>> 0
	return hash % AVATAR_TONE_COUNT
}

/** The logged-in user as shown by the top-bar avatar, from `frappe.boot.user`. */
export function getSessionUser(boot = globalThis.window?.frappe?.boot) {
	const user = boot?.user || {}
	const id = user.name || ""
	const fullName = user.full_name || [user.first_name, user.last_name].filter(Boolean).join(" ") || id
	const email = user.email && user.email !== id ? user.email : ""
	return {
		id,
		fullName,
		image: user.user_image || "",
		initials: getAbbreviation(fullName).toUpperCase(),
		tone: getAvatarTone(fullName),
		tooltip: [fullName, id, email].filter((line, index, lines) => line && lines.indexOf(line) === index).join("\n"),
	}
}

export function hasSystemManagerRole(boot = globalThis.window?.frappe?.boot) {
	const user = boot?.user || {}
	return user.name === "Administrator" || (user.roles || []).includes("System Manager")
}
