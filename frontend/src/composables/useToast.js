/**
 * Thin wrapper over PrimeVue's ToastService so app code keeps a stable
 * `success/error/warn/info` surface (same shape albion exposed) without
 * importing PrimeVue's `useToast` everywhere.
 */
import { useToast } from "primevue/usetoast"

export function useAppToast() {
	const toast = useToast()

	function show(severity, summary, detail, life = 4000) {
		toast.add({ severity, summary, detail, life })
	}

	return {
		// Q19: success takes an optional `life` so high-stakes confirmations
		// (Submit / Cancel / Delete / Amend / Approve) can linger ~6s — a state
		// change the user must actually register ("WO-00010 submitted") deserves
		// longer on screen than a routine field save. Toasts now appear top-right
		// (App.vue), offset below the topbar.
		success(summary, detail, life = 4000) {
			show("success", summary || "Success", detail, life)
		},
		error(summary, detail) {
			show("error", summary || "Error", detail, 6000)
		},
		warn(summary, detail) {
			show("warn", summary || "Warning", detail)
		},
		info(summary, detail) {
			show("info", summary || "Info", detail)
		},
	}
}
