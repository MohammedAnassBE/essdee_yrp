import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

globalThis.window = { location: { assign: () => {} } }
const { getAbbreviation, getAvatarTone, getSessionUser, hasSystemManagerRole } = await import("../src/components/navigation/sessionUser.js")
const { getAccountMenuItems } = await import("../src/components/navigation/accountMenu.js")

const boot = (user) => ({ user })
const actions = { changePassword: () => {}, logOutAllDevices: () => {} }

test("initials follow Frappe's get_abbr", () => {
	assert.equal(getAbbreviation("John Doe"), "JD")
	assert.equal(getAbbreviation("Jenny Jane Doe"), "JJ")
	assert.equal(getAbbreviation("  Jenny   Doe "), "JD")
	assert.equal(getAbbreviation("Administrator"), "A")
	assert.equal(getAbbreviation(""), "?")
})

test("avatar colour is stable per name and within the palette", () => {
	assert.equal(getAvatarTone("Test Planner"), getAvatarTone("Test Planner"))
	for (const name of ["", "A", "Administrator", "Test Planner", "Zoë Ü"]) {
		const tone = getAvatarTone(name)
		assert.ok(Number.isInteger(tone) && tone >= 0 && tone < 8)
	}
})

test("session user uses full name, image and a name + ID + email tooltip", () => {
	const user = getSessionUser(boot({ name: "planner@example.test", email: "planner@example.test", full_name: "test planning", user_image: "/files/me.png" }))
	assert.equal(user.initials, "TP")
	assert.equal(user.image, "/files/me.png")
	assert.equal(user.tooltip, "test planning\nplanner@example.test")

	const admin = getSessionUser(boot({ name: "Administrator", email: "admin@example.com", first_name: "Administrator" }))
	assert.equal(admin.fullName, "Administrator")
	assert.equal(admin.initials, "A")
	assert.equal(admin.image, "")
	assert.equal(admin.tooltip, "Administrator\nadmin@example.com")
})

test("Switch to Desk shows only for System Manager or Administrator", () => {
	const labels = (user) => getAccountMenuItems(actions, boot(user)).map((item) => item.label)
	assert.deepEqual(labels({ name: "Administrator", roles: [] }), ["Change Password", "Switch to Desk", "Log out from all devices"])
	assert.deepEqual(labels({ name: "sm@example.test", roles: ["System Manager"] }), ["Change Password", "Switch to Desk", "Log out from all devices"])
	assert.deepEqual(labels({ name: "planner@example.test", roles: ["Production Planner"] }), ["Change Password", "Log out from all devices"])
	assert.equal(hasSystemManagerRole(boot({})), false)
})

test("Switch to Desk does a full navigation to /desk", () => {
	const assigned = []
	globalThis.window = { location: { assign: (url) => assigned.push(url) } }
	const item = getAccountMenuItems(actions, boot({ name: "Administrator" })).find((entry) => entry.label === "Switch to Desk")
	item.command()
	assert.deepEqual(assigned, ["/desk"])
})

test("the avatar sits next to Log out and carries a tooltip", () => {
	const menu = source("../src/components/navigation/AccountMenu.vue")
	assert.ok(menu.indexOf("<UserAvatar />") < menu.indexOf("app-logout"))
	const avatar = source("../src/components/navigation/UserAvatar.vue")
	assert.match(avatar, /v-tooltip\.bottom="\{ value: user\.tooltip/)
	assert.match(avatar, /@error="imageFailed = true"/)
})
