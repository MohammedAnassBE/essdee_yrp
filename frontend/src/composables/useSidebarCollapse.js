/**
 * useSidebarCollapse — per-user collapse state for the SPA left-sidebar SECTIONS.
 *
 * The left sidebar (AppSidebar.vue) groups DocType links into named sections
 * (Procurement, Production, Stock, …). Each user can collapse a section to hide
 * its items; this composable owns the reactive "which sections are collapsed"
 * Set and persists it.
 *
 * PERSISTENCE: per-user and SERVER-SIDE (not localStorage). The set of collapsed
 * section names is stored in the "Essdee Sidebar Setting" DocType via the
 * whitelisted `essdee_yrp.api.sidebar_view` API, scoped to the session
 * user. A user collapses sections once and they persist across server restarts
 * AND across browsers/devices. Mirrors useChildTableColumns: a one-shot load
 * (the sidebar renders with everything expanded immediately, then the saved
 * collapsed set is merged in when the fetch resolves), a dirty guard so a late
 * load can't clobber a toggle the user just made, and a debounced save.
 *
 * Module-level singleton: one sidebar exists per page, so the reactive Set and
 * the load promise are shared across all callers/re-mounts.
 */
import { reactive } from "vue"
import { callMethod } from "@/api/client"

const GET_COLLAPSED = "essdee_yrp.api.sidebar_view.get_collapsed"
const SET_COLLAPSED = "essdee_yrp.api.sidebar_view.set_collapsed"

// Reactive Set of collapsed section (group) names. A name present here means the
// section is collapsed (its items hidden); absent means expanded. Module-level so
// the sidebar reuses one Set across re-renders/re-mounts.
const collapsed = reactive(new Set())

// One-shot load orchestration (mirrors useChildTableColumns.ensureLoaded). We
// fetch the saved collapsed set exactly once per page lifetime; concurrent first
// accesses share the single in-flight promise and re-renders never refetch.
let loadPromise = null

// Dirty guard: becomes true the moment the user toggles a section — i.e. the user
// acted (and fired a save) BEFORE the one-shot get_collapsed resolved. When that
// late server load lands, applyLoaded must NOT clobber the user's just-made local
// change with the stale server value.
let dirty = false

function applyLoaded(res) {
	// Late-load guard: the user already toggled before the fetch resolved → their
	// local state (and the save they fired) is authoritative; skip the stale merge.
	if (dirty) return
	const saved = res?.collapsed_sections
	if (!Array.isArray(saved)) return
	collapsed.clear()
	for (const name of saved) {
		if (typeof name === "string" && name) collapsed.add(name)
	}
}

// Kick the one-shot load. Safe to call repeatedly — only the first call fetches.
function ensureLoaded() {
	if (loadPromise) return loadPromise
	loadPromise = callMethod(GET_COLLAPSED, {})
		.then((res) => applyLoaded(res))
		.catch((err) => {
			// Network/permission failure: keep the in-memory state (everything
			// expanded by default). The sidebar still works; nothing is persisted
			// until the user next toggles (which retries the server write).
			console.warn("[essdee sidebar collapse] load failed", err)
		})
	return loadPromise
}

// Debounced save: a quick run of toggles coalesces into one server write once the
// user settles. The in-memory Set is already the source of truth for the live UI;
// the server write just makes it durable. Failures are swallowed (state still
// applies for this session) but surfaced for dev visibility.
let saveTimer = null
const SAVE_DEBOUNCE_MS = 400

function persistDebounced() {
	if (saveTimer) clearTimeout(saveTimer)
	saveTimer = setTimeout(() => {
		saveTimer = null
		callMethod(SET_COLLAPSED, { collapsed_sections: [...collapsed] }).catch((err) => {
			console.warn("[essdee sidebar collapse] save failed", err)
		})
	}, SAVE_DEBOUNCE_MS)
}

// Flip one section's collapsed state and persist (debounced). Marks the state
// dirty so a late get_collapsed can't revert this toggle.
function toggleSection(name) {
	if (!name) return
	dirty = true
	if (collapsed.has(name)) collapsed.delete(name)
	else collapsed.add(name)
	persistDebounced()
}

function isCollapsed(name) {
	return collapsed.has(name)
}

export function useSidebarCollapse() {
	// Load once on first use; re-renders reuse the cached promise.
	ensureLoaded()
	return { collapsed, isCollapsed, toggleSection }
}
