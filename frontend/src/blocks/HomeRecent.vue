<!-- home-recent block — recent records over the key submittable doctypes.

     Extracted 1:1 from views/home/HomePage.vue (build step 4). Tabs stay
     gated on canRead + catalog isSubmittable (so the docstatus badge can
     never mislabel a non-submittable doctype as "Draft").

     Knobs (spec §6.4 — defaults reproduce today's behavior exactly):
       doctypes    : Array<String> — tab list. Default = today's literal
                     RECENT list (also what the Default layout passes).
       recentStyle : "table" (default — today's tabbed table, byte-identical)
                     | "tiles" — the Demo-7 tile card ("custom ui/demos/
                     _template.html" renderHome recentStyle:"tiles"):
                     status-TINTED background + top border via the engine
                     statusColors registry, doc id small + status chip on the
                     top row, BOLD title line (meta title_field, else the most
                     meaningful field — e.g. WO item · process — falling back
                     to the docname), "Updated <date>" honouring the layout's
                     dateFormat knob.
     Realtime: the active tab's doctype is subscribed via subscribeList — rows
     refresh silently (no skeleton, no popup) when any record changes. -->
<template>
	<div v-if="recentTabs.length" class="esd-card recent-card">
		<div class="recent-bar">
			<div class="recent-tabs">
				<button
					v-for="t in recentTabs"
					:key="t.doctype"
					class="recent-tab"
					:class="{ active: t.doctype === activeTab }"
					@click="selectTab(t.doctype)"
				>
					Recent {{ t.label }}
				</button>
			</div>
			<button class="recent-viewall" @click="viewAll">View all <i class="pi pi-arrow-right" /></button>
		</div>

		<!-- "table" (default) — today's DOM, unchanged -->
		<div v-if="recentStyle !== 'tiles'" class="recent-scroll">
			<table class="recent-table">
				<thead>
					<tr>
						<th>Code</th>
						<th>Status</th>
						<th>Updated</th>
					</tr>
				</thead>
				<tbody>
					<template v-if="recentLoading">
						<tr v-for="n in 4" :key="`sk-${n}`" class="recent-skel-row">
							<td><div class="recent-skel" style="width: 130px" /></td>
							<td><div class="recent-skel" style="width: 72px" /></td>
							<td><div class="recent-skel" style="width: 48px" /></td>
						</tr>
					</template>
					<template v-else-if="recentRows.length">
						<tr v-for="r in recentRows" :key="r.name" @click="openRecord(r.name)">
							<td>
								<router-link
									v-if="recordPath(r.name)"
									:to="recordPath(r.name)"
									class="recent-code"
									@click.stop
								>{{ r.name }}</router-link>
								<span v-else class="recent-code">{{ r.name }}</span>
							</td>
							<td>
								<span class="badge" :class="docStatusClass(r.docstatus)">
									{{ docStatusLabel(r.docstatus) }}
								</span>
							</td>
							<td class="recent-date">{{ fmtDate(r.modified) }}</td>
						</tr>
					</template>
					<tr v-else>
						<td colspan="3" class="recent-empty">Nothing recent yet</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- "tiles" — the Demo-7 status-tinted card grid -->
		<div v-else class="recent-tiles">
			<template v-if="recentLoading">
				<div v-for="n in 6" :key="`tsk-${n}`" class="recent-tile is-skel">
					<div class="recent-skel" style="width: 60%" />
					<div class="recent-skel" style="width: 40%" />
				</div>
			</template>
			<template v-else-if="recentRows.length">
				<button
					v-for="r in recentRows"
					:key="r.name"
					class="recent-tile"
					:style="tileStyle(r)"
					@click="openRecord(r.name)"
				>
					<span class="recent-tile__top">
						<span class="recent-tile__id">{{ r.name }}</span>
						<span class="recent-tile__chip" :style="chipStyle(r)">
							<i class="recent-tile__chip-dot" />{{ rowStatus(r) }}
						</span>
					</span>
					<span class="recent-tile__title">{{ tileTitle(r) }}</span>
					<span class="recent-tile__date">Updated {{ tileDate(r.modified) }}</span>
				</button>
			</template>
			<div v-else class="recent-empty recent-tiles__empty">Nothing recent yet</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import {
	formatDate,
	statusChipStyle,
	statusColor,
	statusTint,
	useUiConfigStore,
} from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { useRealtime } from "@/composables/useRealtime"
import { useTheme } from "@/composables/useTheme"
import { getRegistryByDoctype } from "@/config/doctypes"
import { getList, getMeta } from "@/api/client"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	// Default = today's literal RECENT list in HomePage.vue.
	doctypes: {
		type: Array,
		default: () => ["Work Order", "Delivery Challan", "Goods Received Note", "Stock Entry"],
	},
	recentStyle: {
		type: String,
		default: "table",
		validator: (v) => ["table", "tiles"].includes(v),
	},
})

const router = useRouter()
const { canRead } = usePermissions()
const { isDark } = useTheme()
const ui = useUiConfigStore()

const tilesMode = computed(() => props.recentStyle === "tiles")

const recentTabs = computed(() =>
	// Gate on isSubmittable so the docstatus badge can never silently mislabel a
	// non-submittable doctype as "Draft" if the doctypes prop names one.
	props.doctypes
		.filter((dt) => canRead(dt) && getRegistryByDoctype(dt)?.isSubmittable)
		.map((dt) => ({ doctype: dt, label: dt, route: getRegistryByDoctype(dt)?.route || "" }))
		.filter((t) => t.route)
)
const activeTab = ref("")
const recentRows = ref([])
const recentLoading = ref(false)

// ── tiles mode: per-doctype meta info (title fields + status availability) ──
// Cached for the session; a meta failure degrades to the base fields (docname
// title, docstatus chip) instead of breaking the card.
const metaInfo = new Map() // doctype -> { hasStatus, titleFields }
// Meaningful-title candidates, in preference order AFTER the doctype's own
// meta title_field ("e.g. WO item/process" — the locked example).
const TITLE_CANDIDATES = ["item_name", "item", "lot", "work_order", "supplier", "purpose"]

async function loadMetaInfo(dt) {
	if (metaInfo.has(dt)) return metaInfo.get(dt)
	let info = { hasStatus: false, titleFields: [] }
	try {
		const docs = await getMeta(dt)
		const meta = docs?.[0] || {}
		const names = new Set((meta.fields || []).map((f) => f.fieldname))
		const primary = [meta.title_field, ...TITLE_CANDIDATES].find(
			(f) => f && f !== "name" && names.has(f)
		)
		const titleFields = primary ? [primary] : []
		if (names.has("process_name") && primary !== "process_name") titleFields.push("process_name")
		info = { hasStatus: names.has("status"), titleFields }
	} catch (e) {
		// degrade silently — the tile falls back to docname + docstatus
	}
	metaInfo.set(dt, info)
	return info
}

// Fetch rows for a tab. `silent` (realtime refresh) keeps the current rows on
// screen — no skeleton flash — and swaps them once the new page arrives.
async function fetchRows(dt, silent = false) {
	if (!silent) {
		recentLoading.value = true
		recentRows.value = []
	}
	let fields = ["name", "docstatus", "modified"]
	if (tilesMode.value) {
		const info = await loadMetaInfo(dt)
		if (dt !== activeTab.value) return
		fields = [...new Set([...fields, ...(info.hasStatus ? ["status"] : []), ...info.titleFields])]
	}
	try {
		const res = await getList(dt, {
			fields,
			order_by: "modified desc",
			limit_page_length: 6,
		})
		if (dt !== activeTab.value) return // stale response — tab changed mid-flight
		recentRows.value = res.data || []
	} catch (e) {
		if (dt === activeTab.value) recentRows.value = []
	} finally {
		if (dt === activeTab.value) recentLoading.value = false
	}
}

async function selectTab(dt) {
	activeTab.value = dt
	resubscribeRealtime()
	await fetchRows(dt)
}

// ── Realtime: silent row refresh on any change in the ACTIVE tab's doctype.
// subscribeList debounces (>=500ms); other tabs refetch on selection anyway.
const { subscribeList } = useRealtime()
let rtDispose = null
function resubscribeRealtime() {
	if (rtDispose) {
		rtDispose()
		rtDispose = null
	}
	if (activeTab.value) {
		const dt = activeTab.value
		rtDispose = subscribeList(dt, () => {
			if (dt === activeTab.value) fetchRows(dt, true)
		})
	}
}
onUnmounted(() => {
	if (rtDispose) rtDispose()
})

// ── tiles mode: status + tint + title helpers (engine statusColors registry) ──
// Status = the doctype's own `status` value when it has one (WO's lifecycle
// Select), else the docstatus label — the same source the table badge uses.
function rowStatus(r) {
	return (typeof r.status === "string" && r.status) || docStatusLabel(r.docstatus)
}

// Demo tile: tinted wash background + 3px top border in the status colour
// (rgba alpha .13 dark / .06 light — _template.html renderHome), plus the
// regular hairline on the other sides.
function tileStyle(r) {
	const s = rowStatus(r)
	const dark = isDark.value
	return {
		background: statusTint(s, dark, dark ? 0.13 : 0.06),
		borderTop: `3px solid ${statusColor(s, dark)}`,
	}
}

function chipStyle(r) {
	return statusChipStyle(rowStatus(r), isDark.value)
}

// BOLD title line: meta title_field / meaningful field (+ process when the
// doctype has one — "WO item · process"), falling back to the docname.
function tileTitle(r) {
	const info = metaInfo.get(activeTab.value)
	const parts = (info?.titleFields || [])
		.map((f) => r[f])
		.filter((v) => typeof v === "string" && v.trim())
	return parts.length ? parts.join(" · ") : r.name
}

// "Updated <date>" honouring the layout's dateFormat knob (Demo 7: dd-mm-yyyy).
function tileDate(value) {
	return formatDate(value, ui.active.dateFormat)
}

function activeRoute() {
	return recentTabs.value.find((t) => t.doctype === activeTab.value)?.route || ""
}

function recordPath(name) {
	const r = activeRoute()
	return r ? `/${r}/${encodeURIComponent(name)}` : ""
}

function openRecord(name) {
	const path = recordPath(name)
	if (path) router.push(path)
}

function viewAll() {
	const route = activeRoute()
	if (route) router.push(`/${route}`)
}

function docStatusLabel(ds) {
	return ds === 2 ? "Cancelled" : ds === 1 ? "Submitted" : "Draft"
}
function docStatusClass(ds) {
	return ds === 2 ? "is-cancelled" : ds === 1 ? "is-submitted" : "is-draft"
}
function fmtDate(s) {
	if (!s) return "—"
	const d = new Date(String(s).replace(" ", "T"))
	if (isNaN(d.getTime())) return s
	return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" })
}

onMounted(() => {
	if (recentTabs.value.length) selectTab(recentTabs.value[0].doctype)
})

// Live knob support (KnobsPanel table↔tiles): tiles need status/title fields
// the table fetch skips, so a runtime style switch refetches the active tab.
// Never fires on a normal mount/render — only when the prop actually changes.
watch(
	() => props.recentStyle,
	() => {
		if (activeTab.value) fetchRows(activeTab.value)
	}
)
</script>

<style scoped>
/* Styles lifted verbatim from HomePage.vue. The old `margin-top: 18px` is
   gone: vertical rhythm between home blocks now comes from the ScreenRenderer
   grid gap (HomePage shell pins it to the same 18px). */
.recent-bar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	border-bottom: 1px solid var(--esd-line);
	padding: 0 8px 0 6px;
}
.recent-tabs {
	display: flex;
	gap: 2px;
	overflow-x: auto;
}
.recent-tab {
	padding: 11px 13px;
	font-size: 13px;
	font-weight: 600;
	color: var(--esd-muted);
	background: transparent;
	border: 0;
	border-bottom: 2px solid transparent;
	margin-bottom: -1px;
	cursor: pointer;
	font-family: inherit;
	white-space: nowrap;
}
.recent-tab.active {
	color: var(--esd-accent-700);
	border-bottom-color: var(--esd-accent);
}
.recent-viewall {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	background: transparent;
	border: 0;
	color: var(--esd-accent-700);
	font-size: 12.5px;
	font-weight: 600;
	cursor: pointer;
	font-family: inherit;
	white-space: nowrap;
	flex-shrink: 0;
}
.recent-viewall i {
	font-size: 11px;
}
.recent-viewall:hover {
	text-decoration: underline;
}

.recent-scroll {
	overflow-x: auto;
}
.recent-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 13px;
}
.recent-table th {
	text-align: left;
	padding: 9px 16px;
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
	font-weight: 700;
	border-bottom: 1px solid var(--esd-line);
}
.recent-table td {
	padding: 10px 16px;
	border-bottom: 1px solid var(--esd-line);
}
.recent-table tbody tr:last-child td {
	border-bottom: 0;
}
.recent-table tbody tr:not(.recent-skel-row) {
	cursor: pointer;
	transition: background 0.12s;
}
.recent-table tbody tr:not(.recent-skel-row):hover {
	background: var(--esd-slate-50);
}
.recent-code {
	font-weight: 600;
	color: var(--esd-accent-700);
}
.recent-date {
	color: var(--esd-muted);
}
.recent-empty {
	text-align: center;
	color: var(--esd-muted);
	padding: 26px;
}

.badge {
	display: inline-flex;
	align-items: center;
	font-size: 11.5px;
	font-weight: 700;
	padding: 3px 9px;
	border-radius: 999px;
}
.badge.is-submitted {
	color: var(--esd-success);
	background: var(--esd-success-50);
}
.badge.is-draft {
	color: var(--esd-muted);
	background: var(--esd-slate-50);
}
.badge.is-cancelled {
	color: var(--esd-danger);
	background: var(--esd-danger-50);
}

.recent-skel {
	height: 12px;
	border-radius: 6px;
	background: linear-gradient(90deg, var(--esd-slate-50), var(--esd-line), var(--esd-slate-50));
	background-size: 200% 100%;
	animation: recent-shimmer 1.2s infinite;
}
@keyframes recent-shimmer {
	from {
		background-position: 200% 0;
	}
	to {
		background-position: -200% 0;
	}
}

/* ── "tiles" variant — the Demo-7 status-tinted card (demo .card.tinted) ── */
.recent-tiles {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(252px, 1fr));
	gap: 14px;
	padding: 14px;
}
.recent-tile {
	display: flex;
	flex-direction: column;
	align-items: stretch;
	gap: 8px;
	background: var(--esd-card); /* overridden inline by the status tint */
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	padding: 14px;
	cursor: pointer;
	font-family: inherit;
	text-align: left;
	box-shadow: var(--esd-shadow-card);
	transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.recent-tile:not(.is-skel):hover {
	transform: translateY(-2px);
	box-shadow: var(--esd-shadow-pop);
}
.recent-tile__top {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 8px;
}
.recent-tile__id {
	font-size: 10.5px;
	color: var(--esd-muted);
	font-weight: 700;
	letter-spacing: 0.04em;
}
.recent-tile__chip {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	font-size: 11px;
	font-weight: 700;
	padding: 3px 10px;
	border-radius: 999px;
	white-space: nowrap;
}
.recent-tile__chip-dot {
	width: 7px;
	height: 7px;
	border-radius: 50%;
	background: currentColor;
	flex: none;
}
.recent-tile__title {
	font-weight: 700;
	font-size: 15px;
	line-height: 1.25;
	letter-spacing: -0.01em;
	color: var(--esd-ink);
}
.recent-tile__date {
	font-size: 11.5px;
	color: var(--esd-muted);
}
.recent-tiles__empty {
	grid-column: 1 / -1;
}
</style>
