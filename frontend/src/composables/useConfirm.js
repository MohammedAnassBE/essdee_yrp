/**
 * Thin wrapper over PrimeVue's ConfirmationService. Exposes a single
 * `require({ message, header, accept, reject, ... })` call that mirrors
 * albion's confirm API so views stay portable.
 */
import { useConfirm } from "primevue/useconfirm"

export function useAppConfirm() {
	const confirm = useConfirm()

	return {
		require(opts = {}) {
			confirm.require({
				header: opts.header || "Please confirm",
				message: opts.message || "Are you sure?",
				icon: opts.icon || "pi pi-exclamation-triangle",
				acceptLabel: opts.acceptLabel || "Confirm",
				rejectLabel: opts.rejectLabel || "Cancel",
				acceptClass: opts.acceptClass,
				accept: opts.accept,
				reject: opts.reject,
			})
		},
	}
}
