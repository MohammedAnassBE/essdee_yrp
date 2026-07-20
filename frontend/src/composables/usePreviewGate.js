// usePreviewGate — the arrangement gates' permission source, preview-aware
// (spec §10 "perm-accurate sidebar").
//
// Outside a View-as preview these are EXACTLY usePermissions' canRead/canCreate
// (parity law — zero behaviour change for every existing render). While an SM
// previews via store.previewAs(), the store carries previewPermHints computed
// SERVER-SIDE as the target user over the resolved config's nav + quickCreate
// doctypes (§4.2) — the four arrangement gates (sidebar, topnav pills, command
// palette, home quick-create CTAs) consult those hints instead, so the SM sees
// the target's true arrangement ∩ access, not their own admin superset.
//
// Capability is untouched: these gates decide what is ADVERTISED, never what
// the session may do — data and real permissions stay the SM's own (§15).
import { useUiConfigStore } from "@yrp/web-engine"
import { usePermissions } from "./usePermissions"

export function usePreviewGate() {
	const ui = useUiConfigStore()
	const { canRead, canCreate } = usePermissions()

	function gateRead(doctype) {
		if (ui.previewPermHints) return (ui.previewPermHints.can_read || []).includes(doctype)
		return canRead(doctype)
	}

	function gateCreate(doctype) {
		if (ui.previewPermHints) return (ui.previewPermHints.can_create || []).includes(doctype)
		return canCreate(doctype)
	}

	return { gateRead, gateCreate }
}
