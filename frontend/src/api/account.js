import { callMethod, logOut } from "./frappe.js"

const USER_METHODS = "frappe.core.doctype.user.user"
const STRENGTH_LABELS = [
	{ label: "Poor", tone: "danger" },
	{ label: "Poor", tone: "danger" },
	{ label: "Average", tone: "warn" },
	{ label: "Good", tone: "info" },
	{ label: "Great", tone: "success" },
]

/** Client checks from Frappe's update-password page; the server re-checks everything. */
export function getPasswordFormError({ oldPassword, newPassword, confirmPassword }) {
	if (!oldPassword) return "Please enter your old password."
	if (!newPassword) return "Please enter your new password."
	if (oldPassword === newPassword) return "New password cannot be same as old password"
	if (newPassword !== confirmPassword) return "Passwords do not match"
	return ""
}

/** Frappe's System Settings strength check; null when empty or the policy is off. */
export async function getPasswordStrength(newPassword) {
	if (!newPassword) return null
	const result = await callMethod(`${USER_METHODS}.test_password_strength`, { new_password: newPassword }, { silent: true })
	if (result?.score === undefined || result?.score === null) return null
	const feedback = result.feedback || {}
	return {
		...STRENGTH_LABELS[result.score],
		passed: Boolean(feedback.password_policy_validation_passed),
		warning: feedback.warning || "",
		suggestions: feedback.suggestions || [],
	}
}

/** Runs Frappe's update_password via a wrapper that keeps this session on a wrong old password. */
export async function changePassword(form) {
	const formError = getPasswordFormError(form)
	if (formError) throw new Error(formError)
	return callMethod(
		"essdee_yrp.api.account.update_password",
		{ old_password: form.oldPassword, new_password: form.newPassword },
		{ silent: true },
	)
}

/** Ends every other session with Frappe's forced logout, then this one, then goes to /login. */
export async function logOutAllDevices() {
	await callMethod("essdee_yrp.api.account.logout_other_sessions")
	await logOut()
}
