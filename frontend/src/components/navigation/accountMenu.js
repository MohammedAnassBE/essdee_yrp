import { computed, ref } from "vue"

import { logOut } from "../../api/frappe.js"
import { logOutAllDevices } from "../../api/account.js"

export const ACCOUNT_CONFIRMATIONS = {
	logout: {
		title: "Log out?",
		message: "You will need to sign in again to continue.",
		confirmLabel: "Log out",
		confirmIcon: "pi pi-sign-out",
		severity: undefined,
	},
	"logout-all": {
		title: "Log out from all devices?",
		message: "This ends your sessions on every device, including this one.",
		confirmLabel: "Log out everywhere",
		confirmIcon: "pi pi-sign-out",
		severity: "danger",
	},
}

/** Holds the one pending account confirmation and runs its action on confirm. */
export function createAccountConfirmation(actions = { logout: logOut, "logout-all": logOutAllDevices }) {
	const pending = ref("")
	const busy = ref(false)
	const error = ref("")
	const current = computed(() => ACCOUNT_CONFIRMATIONS[pending.value] || null)

	function open(kind) {
		error.value = ""
		pending.value = kind
	}

	function cancel() {
		if (!busy.value) pending.value = ""
	}

	async function confirm() {
		busy.value = true
		error.value = ""
		try {
			await actions[pending.value]()
		} catch (failure) {
			error.value = failure.message
		} finally {
			busy.value = false
		}
	}

	return { pending, busy, error, current, open, cancel, confirm }
}
