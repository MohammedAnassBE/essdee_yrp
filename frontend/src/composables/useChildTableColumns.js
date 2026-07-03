/**
 * useChildTableColumns — shared logic for the SPA's PrimeVue child-table grids.
 *
 * One place owns:
 *   • DEFAULT_WIDTHS — sensible per-fieldtype starting widths (px) so a column
 *     that the user has never resized still renders at a reasonable size with a
 *     FIXED table layout (no expand/shrink-on-focus jitter).
 *   • columnWidth(col) — resolve a column's default width from its fieldtype
 *     (falling back to a generic width).
 *   • a column-width store keyed by FIELDNAME (not position). We do NOT use
 *     PrimeVue's stateStorage="local" for widths: PrimeVue persists widths
 *     POSITIONALLY (one CSV restored by nth-child), but the SAME child table
 *     renders DIFFERENT column sets in view vs edit mode, and the chooser changes
 *     the visible column COUNT at runtime — a positional CSV then applies widths
 *     to the wrong columns and modes overwrite each other on every render. A
 *     field-keyed map ({fieldname: px}) is immune to both: a column keeps its
 *     width wherever it renders, regardless of position or count.
 *   • a column-visibility helper (default-visible set + a reactive selection).
 *
 * PERSISTENCE: per-user and SERVER-SIDE (not localStorage). The visible-column
 * selection and field-keyed width map for each (host-doctype, child-table) are
 * stored in the "Essdee Child Table View Setting" DocType via the whitelisted
 * `essdee_yrp.api.child_table_view` API, scoped to the session user. A
 * user sets columns once and they persist across server restarts AND across
 * browsers/devices. The server already scopes by session user, so the in-memory
 * caches below are keyed by (doctype, child_table) only.
 *
 * Loading is async: on first access of a table's visibility Set or width map we
 * render with DEFAULTS (default-visible columns — the child DocType's
 * `in_list_view` fields, else the first 5 non-hidden/non-read-only fields — plus
 * per-fieldtype default widths) and kick off a one-shot `get_view` fetch in the
 * background; when it resolves we mutate
 * the SAME reactive objects in place so Vue re-renders with the saved values. A
 * brief default-then-applied flash on first paint is acceptable and intended.
 *
 * Used by DocDetail.vue at all three child-table render sites: the dedicated
 * generic editableChildTables edit grids, and the
 * view-mode childTables tabs.
 */
import { reactive } from "vue"
import { callMethod } from "@/api/client"

const GET_VIEW = "essdee_yrp.api.child_table_view.get_view"
const SAVE_VIEW = "essdee_yrp.api.child_table_view.save_view"

// Per-fieldtype default column widths (px). Tuned for a fixed table layout —
// numeric/flag columns are tight; text/link columns get more room. Anything not
// listed falls back to FALLBACK_WIDTH.
export const DEFAULT_WIDTHS = {
	Link: 200,
	"Dynamic Link": 200,
	Data: 180,
	Select: 160,
	"Small Text": 220,
	Text: 220,
	"Long Text": 220,
	"Text Editor": 240,
	Code: 240,
	Int: 140,
	Float: 150,
	Currency: 150,
	Percent: 150,
	Check: 70,
	Date: 140,
	Datetime: 170,
	Time: 120,
}
export const FALLBACK_WIDTH = 160
// The trailing action column (delete / add-row) is a small fixed width.
export const ACTION_COL_WIDTH = 56
// Frappe-style width editor units shown in the Columns popover. Ten units is
// treated as the usable child-table width; each unit maps to a stable px value
// for the existing PrimeVue fixed-width grid.
export const WIDTH_UNIT_PX = 100
export const MAX_TABLE_WIDTH_UNITS = 10
export const MIN_COLUMN_WIDTH_UNITS = 1

function defaultColumnWidthPx(col) {
	const ft = col?.fieldtype || ""
	return DEFAULT_WIDTHS[ft] || FALLBACK_WIDTH
}

function pxToWidthUnits(px) {
	const n = Number(px)
	if (!Number.isFinite(n) || n <= 0) return MIN_COLUMN_WIDTH_UNITS
	return Math.max(MIN_COLUMN_WIDTH_UNITS, Math.round(n / WIDTH_UNIT_PX))
}

function widthUnitsToPx(units) {
	const n = Number(units)
	if (!Number.isFinite(n) || n <= 0) return WIDTH_UNIT_PX
	return Math.max(MIN_COLUMN_WIDTH_UNITS, Math.round(n)) * WIDTH_UNIT_PX
}

// Resolve a column's default width from its raw Frappe `fieldtype` (the only key
// that matches DEFAULT_WIDTHS — `col.type` is a display type like "link"/"number"
// that never matches a raw type such as "Link"/"Float"), falling back to the
// generic width. Returns a CSS length string ("180px"). `fieldtype` is always
// populated by childEditColumns, so there is no need for a display-type branch.
export function columnWidth(col) {
	return `${defaultColumnWidthPx(col)}px`
}

// Stable cache key per (host-doctype, child-table fieldname). The server scopes
// rows by session user, so the user is NOT part of the key.
function stateKeyFor(doctype, fieldname) {
	return `${doctype}:${fieldname}`
}

// ── Server load orchestration ────────────────────────────────────────────────
// We fetch each table's saved view exactly once (per page lifetime). `loadState`
// tracks the in-flight / settled fetch per key so re-renders never refetch and
// concurrent first accesses (the visibility Set and the width map are requested
// independently) share one request. When the fetch resolves we mutate the SAME
// reactive objects created on first access, so the grid re-renders with the saved
// values without anything having to re-call the getters.
const loadState = reactive({}) // key -> { promise, done }

// Per-key "dirty" guard. A key becomes dirty the moment the user toggles a
// column or drags a width — i.e. the user has acted on (and fired a save for)
// this table BEFORE the one-shot get_view resolved. When that late server load
// finally lands, applyLoadedState must NOT clobber the user's just-made local
// change with the stale server value. Keyed exactly like the stores
// (stateKeyFor → "doctype:fieldname"); untouched keys (new users, tables the
// user never interacts with) are never in this set and load normally.
const dirtyKeys = new Set()

// Per-(visibility-)key marker: the server returned a NON-EMPTY saved selection
// and applyLoadedState applied it. Keyed exactly like `selections` (visKeyFor).
// Used by useVisibleColumns' empty-set recovery to avoid re-seeding a selection
// the server already authoritatively populated (it can never have been left empty
// by that path, but the marker keeps the two code paths from racing each other).
const serverAppliedKeys = new Set()

function markDirty(doctype, fieldname) {
	dirtyKeys.add(stateKeyFor(doctype, fieldname))
}

function ensureLoaded(doctype, fieldname, columns, maxDefault) {
	const key = stateKeyFor(doctype, fieldname)
	if (loadState[key]) {
		// Already in-flight/settled: don't refetch (one-shot). But DO record the
		// freshest known column list / maxDefault on the entry, so that if the
		// width-only path kicked the fetch first (without columns), a later
		// visibility-path call that DOES have columns still drives the
		// visibility merge correctly when the fetch resolves. No-op once the
		// fetch already resolved.
		const e = loadState[key]
		if (columns) e.columns = columns
		if (maxDefault !== undefined) e.maxDefault = maxDefault
		return e.promise
	}

	const entry = { promise: null, done: false, columns, maxDefault }
	entry.promise = callMethod(GET_VIEW, {
		parent_doctype: doctype,
		child_table: fieldname,
	})
		.then((res) => {
			applyLoadedState(doctype, fieldname, entry.columns, entry.maxDefault, res)
		})
		.catch((err) => {
			// Network/permission failure: keep the in-memory defaults already
			// rendered. The grid still works; nothing is persisted until the
			// user next toggles/resizes (which retries the server write).
			// Swallowed for UX resilience, but surfaced so failures are visible
			// in dev.
			console.warn("[essdee child-table view] load failed", err)
		})
		.finally(() => {
			entry.done = true
		})
	loadState[key] = entry
	return entry.promise
}

// Merge a server `get_view` payload into the live reactive stores. Stale/removed
// fieldnames are dropped against the current column set; an empty/absent saved
// selection leaves the default-visible set untouched.
function applyLoadedState(doctype, fieldname, columns, maxDefault, res) {
	// Late-load guard: if the user already toggled/resized this table before the
	// one-shot get_view resolved, their local state (and the save they already
	// fired) is authoritative — skip merging the now-stale server value, which
	// would otherwise revert the user's in-flight change. The key was already
	// marked loaded by ensureLoaded, so it never refetches regardless of this
	// early return. New users / untouched keys are never dirty and merge normally.
	if (dirtyKeys.has(stateKeyFor(doctype, fieldname))) return

	const valid = new Set((columns || []).map((c) => c.fieldname))

	// Visibility — only override the seeded default if the server returned a
	// non-empty, still-valid selection.
	const visKey = visKeyFor(doctype, fieldname)
	const visSet = selections[visKey]
	const savedVis = res?.visible_columns
	if (visSet && Array.isArray(savedVis) && savedVis.length) {
		const list = savedVis.filter((fn) => valid.has(fn))
		if (list.length) {
			visSet.clear()
			for (const fn of list) visSet.add(fn)
			// Mark this key as server-authoritative so the empty-set race recovery
			// in useVisibleColumns leaves the applied selection alone.
			serverAppliedKeys.add(visKey)
		}
	}

	// Widths — replace any seeded (empty) map with the saved {fieldname: px},
	// dropping malformed/non-positive entries.
	const wKey = widthKeyFor(doctype, fieldname)
	const wStore = widthStores[wKey]
	const savedW = res?.column_widths
	if (wStore && savedW && typeof savedW === "object") {
		for (const k of Object.keys(wStore)) delete wStore[k]
		for (const [fn, px] of Object.entries(savedW)) {
			const n = Number(px)
			if (Number.isFinite(n) && n > 0) wStore[fn] = Math.round(n)
		}
	}
}

// Push the current full view (visibility + widths) for a table to the server.
// Fire-and-forget — the in-memory stores are already the source of truth for the
// live UI; the server write just makes the choice durable. Failures are silently
// ignored (the user's selection still applies for this session).
function persistView(doctype, fieldname) {
	const visSet = selections[visKeyFor(doctype, fieldname)]
	const wStore = widthStores[widthKeyFor(doctype, fieldname)]
	const visible_columns = visSet ? [...visSet] : []
	const column_widths = wStore ? { ...wStore } : {}
	return callMethod(SAVE_VIEW, {
		parent_doctype: doctype,
		child_table: fieldname,
		visible_columns,
		column_widths,
	}).catch((err) => {
		/* server unreachable — selection still applies in-memory this session.
		   Swallowed for UX resilience, but surfaced so failures are visible. */
		console.warn("[essdee child-table view] save failed", err)
	})
}

// Debounced resize saves: a drag fires many @column-resize-end-adjacent updates;
// coalesce per (doctype, child-table) so we write once the drag settles.
const saveTimers = {}
const RESIZE_SAVE_DEBOUNCE_MS = 400

function persistViewDebounced(doctype, fieldname) {
	const key = stateKeyFor(doctype, fieldname)
	if (saveTimers[key]) clearTimeout(saveTimers[key])
	saveTimers[key] = setTimeout(() => {
		delete saveTimers[key]
		persistView(doctype, fieldname)
	}, RESIZE_SAVE_DEBOUNCE_MS)
}

// ── Column-visibility selection ──────────────────────────────────────────────
// We keep our OWN "which columns are visible" selection (PrimeVue has no built-in
// column toggle) seeded from a default-visible set, and only render the selected
// columns. `selections` is a module-level reactive cache keyed by stateKey so the
// same table reuses one Set across re-renders.
const selections = reactive({})

function visKeyFor(doctype, fieldname) {
	return `${stateKeyFor(doctype, fieldname)}:visible`
}

// Default-visible column set — the canonical child-table structure: the fields
// the child DocType marks `in_list_view`, in field order; or, when NONE is
// flagged, the first 5 fields that are neither hidden nor read-only. The column
// objects passed in carry the child-doctype meta flags (`in_list_view`/`hidden`/
// `read_only`) — `childColumnsFromMeta` in DocDetail.vue threads them through —
// so the default is computed from those flags, not a positional first-N cut.
// `maxDefault` is the fallback cap (first-N when nothing is in_list_view).
// A user's SAVED selection always overrides this default (applyLoadedState).
// All `columns` remain available to toggle on via the chooser regardless.
export function defaultVisibleFieldnames(columns, maxDefault = 5) {
	const cols = Array.isArray(columns) ? columns : []
	const fitWithinBudget = (candidates) => {
		const out = []
		let used = 0
		for (const col of candidates) {
			const units = pxToWidthUnits(defaultColumnWidthPx(col))
			if (out.length && used + units > MAX_TABLE_WIDTH_UNITS) continue
			out.push(col.fieldname)
			used += units
			if (used >= MAX_TABLE_WIDTH_UNITS) break
		}
		return out
	}
	const inListView = fitWithinBudget(cols.filter((c) => c.in_list_view))
	if (inListView.length) return inListView
	// No in_list_view fields → first N non-hidden, non-read-only fields, in order.
	const firstN = fitWithinBudget(cols.filter((c) => !c.hidden && !c.read_only).slice(0, maxDefault))
	if (firstN.length) return firstN
	// Last resort (a table whose every non-hidden field is read-only): show the
	// first N non-hidden columns so the grid never renders zero columns.
	return fitWithinBudget(cols.filter((c) => !c.hidden).slice(0, maxDefault))
}

// Get (or initialise) the reactive Set of visible fieldnames for a table.
// On first access WITH real columns it seeds from the default-visible set and
// kicks off the one-shot server fetch; when that resolves the saved selection
// (if any) is merged into THIS same Set in place. The result is always a subset
// of the current columns.
//
// EMPTY-META RACE GUARD: in view mode a child-table panel can render BEFORE the
// child meta lands, so the first call arrives with `columns === []`. If we cached
// an empty Set then, the later call WITH real columns would hit the `if (!
// selections[key])` guard and skip seeding — leaving a permanently empty visible
// Set that filters every populated column out (zero columns render). To prevent
// that we:
//   1. Never CACHE a Set when `columns` is empty — return a transient empty Set
//      so the first call WITH real columns performs the real seeding.
//   2. Defense-in-depth: if a cached Set is somehow already empty while real
//      columns are now present, re-seed it IN PLACE (clear + add) from the
//      default-visible set — but ONLY when the key is not dirty (user hasn't
//      toggled) and the server hasn't already applied a non-empty saved
//      selection. A user can't deliberately persist an empty set (the chooser's
//      "never hide the last column" rule blocks it), so an empty cached set here
//      can only be a brand-new-user race artefact, which is exactly the target.
export function useVisibleColumns(doctype, fieldname, columns, maxDefault = 5) {
	const key = visKeyFor(doctype, fieldname)
	const hasColumns = Array.isArray(columns) && columns.length > 0

	if (!selections[key]) {
		if (!hasColumns) {
			// Columns not ready yet (empty-meta race): hand back a transient empty
			// Set WITHOUT caching it, so the first call with real columns seeds.
			return reactive(new Set())
		}
		selections[key] = reactive(new Set(defaultVisibleFieldnames(columns, maxDefault)))
	} else if (hasColumns && selections[key].size === 0) {
		// Cached set is empty but real columns are now available — recover from a
		// race-seeded empty set. Skip when the user toggled (dirty) or the server
		// already applied a non-empty saved selection (serverAppliedKeys).
		if (!dirtyKeys.has(stateKeyFor(doctype, fieldname)) && !serverAppliedKeys.has(key)) {
			const set = selections[key]
			set.clear()
			for (const fn of defaultVisibleFieldnames(columns, maxDefault)) set.add(fn)
		}
	}

	ensureLoaded(doctype, fieldname, columns, maxDefault)
	return selections[key]
}

// Persist a table's visible-column selection to the server (called after a
// chooser toggle). Saves the full current view (visibility + widths) immediately.
export function persistVisibleColumns(doctype, fieldname /* , visibleSet */) {
	// User acted on this table → its local state is now authoritative; guard
	// against a late get_view reverting this change.
	markDirty(doctype, fieldname)
	persistView(doctype, fieldname)
}

// ── Column-width overrides (field-keyed, NOT positional) ─────────────────────
// We persist the widths the user drags ourselves, keyed by column FIELDNAME, so
// a column keeps its width wherever it renders — regardless of its position or of
// how many columns are visible. This sidesteps PrimeVue's positional stateStorage
// CSV (which corrupts widths across view↔edit modes and after a visibility
// toggle). A column present in both view and edit modes deliberately SHARES one
// width — that consistency is the point of keying by fieldname.
//
// `widthStores` is a module-level reactive cache keyed by the width key so the
// same table reuses one width map across re-renders (and across render sites).
const widthStores = reactive({})

function widthKeyFor(doctype, fieldname) {
	return `${stateKeyFor(doctype, fieldname)}:widths`
}

// Get (or initialise) the reactive { <columnFieldname>: <px:number> } map for a
// table. On first access it starts empty (defaults apply) and kicks off the
// one-shot server fetch; when that resolves the saved widths are merged into THIS
// same map in place. Keyed by (doctype, child-table fieldname).
export function useColumnWidths(doctype, fieldname, columns) {
	const key = widthKeyFor(doctype, fieldname)
	if (!widthStores[key]) {
		widthStores[key] = reactive({})
	}
	// Kick the one-shot loader unconditionally so a render site that shows widths
	// WITHOUT the visibility path (width-only) still loads the saved widths. The
	// loader is cached per key, so this never refetches; when columns are absent
	// the entry's columns are filled in by the visibility path's call (see
	// ensureLoaded) before the fetch resolves, keeping the visibility merge
	// correct.
	ensureLoaded(doctype, fieldname, columns)
	return widthStores[key]
}

// Record a single column's user-dragged width (px) and persist the whole view.
// Called from the DataTable @column-resize-end handler; the server write is
// DEBOUNCED so a drag doesn't spam the API.
export function persistColumnWidth(doctype, fieldname, columnFieldname, px) {
	const n = Number(px)
	if (!columnFieldname || !Number.isFinite(n) || n <= 0) return
	// User dragged a width → this table's local state is now authoritative;
	// guard against a late get_view reverting it (marked at the moment of the
	// user action, before the debounced save fires).
	markDirty(doctype, fieldname)
	const store = useColumnWidths(doctype, fieldname)
	store[columnFieldname] = Math.round(n)
	persistViewDebounced(doctype, fieldname)
}

export function persistColumnWidthUnits(doctype, fieldname, columnFieldname, units) {
	persistColumnWidth(doctype, fieldname, columnFieldname, widthUnitsToPx(units))
}

// Resolve the width (CSS length) to apply to a column: the user's field-keyed
// override if present, else the per-fieldtype default from columnWidth().
export function resolvedColumnWidth(doctype, fieldname, col) {
	const store = useColumnWidths(doctype, fieldname)
	const override = col?.fieldname ? store[col.fieldname] : undefined
	if (Number.isFinite(override) && override > 0) return `${override}px`
	return columnWidth(col)
}

export function resolvedColumnWidthUnits(doctype, fieldname, col) {
	const store = useColumnWidths(doctype, fieldname)
	const override = col?.fieldname ? store[col.fieldname] : undefined
	const px = Number.isFinite(override) && override > 0 ? override : defaultColumnWidthPx(col)
	return pxToWidthUnits(px)
}
