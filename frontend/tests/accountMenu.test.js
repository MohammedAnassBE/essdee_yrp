import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

function mockServer(responses = {}) {
	const calls = []
	const assigned = []
	globalThis.window = { location: { assign: (url) => assigned.push(url), pathname: "/web", search: "", hash: "" }, csrf_token: "token" }
	globalThis.fetch = async (url, options) => {
		calls.push({ url, method: options.method, body: options.body ? JSON.parse(options.body) : undefined })
		const { status = 200, payload = {} } = responses[url] || {}
		return { ok: status < 400, status, json: async () => payload }
	}
	return { calls, assigned }
}

const { createAccountConfirmation, ACCOUNT_CONFIRMATIONS } = await import("../src/components/navigation/accountMenu.js")
const account = await import("../src/api/account.js")

test("Log out asks first: cancel keeps the session, confirm logs out", async () => {
	const ended = []
	const confirmation = createAccountConfirmation({ logout: async () => ended.push("logout") })
	confirmation.open("logout")
	assert.equal(confirmation.current.value.title, "Log out?")
	assert.equal(confirmation.current.value.confirmLabel, "Log out")
	confirmation.cancel()
	assert.equal(confirmation.current.value, null)
	assert.deepEqual(ended, [])

	confirmation.open("logout")
	await confirmation.confirm()
	assert.deepEqual(ended, ["logout"])
})

test("a failed confirmation action shows its error and re-enables the dialog", async () => {
	const confirmation = createAccountConfirmation({ logout: async () => { throw new Error("Server down") } })
	confirmation.open("logout")
	await confirmation.confirm()
	assert.equal(confirmation.error.value, "Server down")
	assert.equal(confirmation.busy.value, false)
	assert.equal(confirmation.current.value.title, "Log out?")
})

test("Log out from all devices has its own confirmation", () => {
	assert.equal(ACCOUNT_CONFIRMATIONS["logout-all"].title, "Log out from all devices?")
	assert.match(ACCOUNT_CONFIRMATIONS["logout-all"].message, /including this one/)
})

test("password form validation mirrors Frappe's update-password page", () => {
	const form = (oldPassword, newPassword, confirmPassword) => ({ oldPassword, newPassword, confirmPassword })
	assert.equal(account.getPasswordFormError(form("", "Abc!2345xyz", "Abc!2345xyz")), "Please enter your old password.")
	assert.equal(account.getPasswordFormError(form("old", "", "")), "Please enter your new password.")
	assert.equal(account.getPasswordFormError(form("same", "same", "same")), "New password cannot be same as old password")
	assert.equal(account.getPasswordFormError(form("old", "Abc!2345xyz", "Abc!2345xy")), "Passwords do not match")
	assert.equal(account.getPasswordFormError(form("old", "Abc!2345xyz", "Abc!2345xyz")), "")
})

test("changePassword posts old and new password to the update_password wrapper", async () => {
	const { calls } = mockServer({ "/api/method/essdee_yrp.api.account.update_password": { payload: { message: "/desk" } } })
	const redirect = await account.changePassword({ oldPassword: "old", newPassword: "Abc!2345xyz", confirmPassword: "Abc!2345xyz" })
	assert.equal(redirect, "/desk")
	assert.deepEqual(calls, [{
		url: "/api/method/essdee_yrp.api.account.update_password",
		method: "POST",
		body: { old_password: "old", new_password: "Abc!2345xyz" },
	}])
})

test("changePassword rejects invalid forms without calling the server", async () => {
	const { calls } = mockServer()
	await assert.rejects(account.changePassword({ oldPassword: "old", newPassword: "a", confirmPassword: "b" }), /Passwords do not match/)
	assert.deepEqual(calls, [])
})

test("a wrong current password is shown as an error without leaving the page", async () => {
	const { assigned } = mockServer({
		"/api/method/essdee_yrp.api.account.update_password": {
			status: 417,
			payload: { exc_type: "ValidationError", _server_messages: JSON.stringify([JSON.stringify({ message: "Your old password is incorrect." })]) },
		},
	})
	await assert.rejects(account.changePassword({ oldPassword: "wrong", newPassword: "Abc!2345xyz", confirmPassword: "Abc!2345xyz" }), /Your old password is incorrect\./)
	assert.deepEqual(assigned, [])
})

test("a weak password shows Frappe's policy feedback", async () => {
	mockServer({
		"/api/method/essdee_yrp.api.account.update_password": {
			status: 417,
			payload: { exc_type: "ValidationError", _server_messages: JSON.stringify([JSON.stringify({ message: "<div>This is a top-10 common password.</div><ul><li>Add another word or two.</li></ul>", title: "Password requirements not met" })]) },
		},
	})
	await assert.rejects(account.changePassword({ oldPassword: "old", newPassword: "password1", confirmPassword: "password1" }), /top-10 common password[\s\S]*Add another word/)
})

test("password strength uses Frappe's test_password_strength and the policy result", async () => {
	const { calls } = mockServer({
		"/api/method/frappe.core.doctype.user.user.test_password_strength": {
			payload: { message: { score: 1, feedback: { warning: "Too guessable", suggestions: ["Add a word"], password_policy_validation_passed: false } } },
		},
	})
	const strength = await account.getPasswordStrength("abc12345")
	assert.deepEqual(calls[0].body, { new_password: "abc12345" })
	assert.deepEqual(strength, { label: "Poor", tone: "danger", passed: false, warning: "Too guessable", suggestions: ["Add a word"] })
})

test("password strength is skipped for empty input and when the policy is off", async () => {
	const { calls } = mockServer({ "/api/method/frappe.core.doctype.user.user.test_password_strength": { payload: { message: {} } } })
	assert.equal(await account.getPasswordStrength(""), null)
	assert.equal(calls.length, 0)
	assert.equal(await account.getPasswordStrength("anything"), null)
})

test("Log out from all devices ends other sessions, then this one, then goes to /login", async () => {
	const { calls, assigned } = mockServer()
	await account.logOutAllDevices()
	assert.deepEqual(calls.map((call) => call.url), ["/api/method/essdee_yrp.api.account.logout_other_sessions", "/api/method/logout"])
	assert.deepEqual(assigned, ["/login"])
})

test("the header shows Log out and a ⋮ account menu with both items", () => {
	const app = source("../src/App.vue")
	assert.match(app, /<AccountMenu \/>/)
	assert.ok(app.indexOf("<AccountMenu") > app.indexOf('class="app-theme-toggle"'))
	const menu = source("../src/components/navigation/AccountMenu.vue")
	assert.match(menu, /class="app-theme-toggle app-logout"[^>]*@click="confirmation\.open\('logout'\)"/)
	assert.ok(menu.indexOf("app-account-menu-button") > menu.indexOf("app-logout"))
	assert.match(menu, /pi pi-ellipsis-v/)
	assert.match(menu, /label: "Change Password"/)
	assert.match(menu, /label: "Log out from all devices"/)
	assert.match(menu, /<DocumentConfirmationDialog/)
	assert.match(menu, /<ChangePasswordDialog/)
})
