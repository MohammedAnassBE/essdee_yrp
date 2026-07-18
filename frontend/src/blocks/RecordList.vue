<!-- record-list block — a bounded embed of the list-presentation renderers
     (spec §6.4 knobs-are-props; demo _template §7 record-list block).

     Layouts place a small live list of ANY readable DocType on a screen:

       { "type": "record-list", "props": {
           "doctype": "Work Order", "variant": "cards" | "kanban" | "table",
           "columns": ["item", "planned_quantity"],   // or [{field,label}]
           "groupBy": "process_name",                 // kanban only
           "titleField": "item",                      // optional bold title
           "pageSize": 8, "title": "Open Work Orders",
           "cardTemplate": { "type": "stack", ... } } }  // optional (below)

     cardTemplate (Track 1 item 2, cards/kanban only): an OPTIONAL composite
     tree rendered as each card's interior — scope = the ROW record (bind
     paths are fieldnames), same grammar as the `composite` block. Absent →
     the shipped card look, byte-identical. Extra fields the template binds
     are DERIVED from its bind paths and added to the fetch (meta-checked,
     exactly like the composite block) — the JSON names fields, never a
     query. Fetch/permissions/realtime/navigation stay host-owned unchanged.

     Bounded: one page (pageSize, default 8), no tabs/search/paginator — the
     "View all" link goes to the full list page (only when a /web route
     exists). Data comes from the SAME list API as every list; the canRead
     gate renders NOTHING without permission — arrangement never grants
     capability (spec §15). Realtime: silent row refresh via subscribeList. -->
<template>
	<div v-if="allowed" class="esd-card rl-card">
		<div class="rl-head">
			<span class="rl-title">{{ heading }}</span>
			<span class="rl-spacer" />
			<button v-if="route" class="rl-viewall" @click="viewAll">
				View all <i class="pi pi-arrow-right" />
			</button>
		</div>

		<!-- table (default) — compact bounded table -->
		<div v-if="effectiveVariant === 'table'" class="rl-scroll">
			<table class="rl-table">
				<thead>
					<tr>
						<th>Code</th>
						<th v-for="c in colDescs" :key="c.field">{{ c.label }}</th>
						<th v-if="hasStatusSignal">Status</th>
					</tr>
				</thead>
				<tbody>
					<template v-if="loading">
						<tr v-for="n in 4" :key="`sk-${n}`" class="rl-skel-row">
							<td><div class="rl-skel" style="width: 120px" /></td>
							<td v-for="c in colDescs" :key="c.field"><div class="rl-skel" style="width: 70px" /></td>
							<td v-if="hasStatusSignal"><div class="rl-skel" style="width: 64px" /></td>
						</tr>
					</template>
					<template v-else-if="rowsData.length">
						<tr
							v-for="r in rowsData"
							:key="r.name"
							:class="{ 'rl-openable': !!route }"
							@click="openRecord(r)"
						>
							<td class="rl-code">{{ r.name }}</td>
							<td v-for="c in colDescs" :key="c.field">{{ cellValue(c, r) }}</td>
							<td v-if="hasStatusSignal">
								<span v-if="statusOf(r)" class="rl-chip" :style="chipStyle(r)">
									<i class="rl-chip-dot" />{{ statusOf(r) }}
								</span>
								<span v-else>—</span>
							</td>
						</tr>
					</template>
					<tr v-else>
						<td :colspan="colDescs.length + (hasStatusSignal ? 2 : 1)" class="rl-empty">
							No records yet
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- cards / kanban — the shared presentation renderers -->
		<div v-else class="rl-body">
			<ListCards
				v-if="effectiveVariant === 'cards'"
				:rows="rowsData"
				:columns="colDescs"
				:title-field="resolvedTitleField"
				:title-of="titleOf"
				:status-of="statusOf"
				:cell-value="cellValue"
				:loading="loading"
				:card-template="cardTemplate"
				@open="openRecord"
			/>
			<ListKanban
				v-else
				:rows="rowsData"
				:columns="colDescs"
				:title-field="resolvedTitleField"
				:title-of="titleOf"
				:status-of="statusOf"
				:cell-value="cellValue"
				:group-of="groupOf"
				:group-field="resolvedGroupField"
				:loading="loading"
				:card-template="cardTemplate"
				@open="openRecord"
			/>
			<div v-if="!loading && !rowsData.length" class="rl-empty">No records yet</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from "vue"
import { useRouter } from "vue-router"
import { collectBindPaths, formatDate, statusChipStyle } from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { useRealtime } from "@/composables/useRealtime"
import { useTheme } from "@/composables/useTheme"
import { useLinkTitles } from "@/composables/useLinkTitles"
import { getRegistryByDoctype } from "@/config/doctypes"
import { getFieldLabel } from "@/config/fields"
import { getList, getMeta } from "@/api/client"
import ListCards from "@/components/list/ListCards.vue"
import ListKanban from "@/components/list/ListKanban.vue"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	doctype: { type: String, required: true },
	variant: {
		type: String,
		default: "table",
		validator: (v) => ["table", "cards", "kanban"].includes(v),
	},
	// Key columns: fieldnames (or {field,label} objects). Unknown fields drop
	// silently against meta; absent → the DocType's `in_list_view` defaults.
	columns: { type: Array, default: null },
	groupBy: { type: String, default: "" }, // kanban grouping field
	titleField: { type: String, default: "" }, // bold card title override
	pageSize: { type: Number, default: 8 },
	title: { type: String, default: "" }, // block heading override
	// Optional per-row composite tree (cards/kanban interiors — see header).
	cardTemplate: { type: Object, default: null },
})

const router = useRouter()
const { canRead } = usePermissions()
const { isDark } = useTheme()
const linkTitles = useLinkTitles()

// ── canRead gate: no read permission ⇒ the block renders NOTHING (§15). ──
const allowed = computed(() => !!props.doctype && canRead(props.doctype))

const registry = computed(() => getRegistryByDoctype(props.doctype) || null)
const route = computed(() => registry.value?.route || "")
const isWorkflow = computed(() => registry.value?.isWorkflow || false)
const heading = computed(() => props.title || registry.value?.label || props.doctype)

const meta = shallowRef(null)
const rowsData = ref([])
const loading = ref(false)

const metaFieldSet = computed(() => new Set((meta.value?.fields || []).map((f) => f.fieldname)))
const isSubmittable = computed(
	() => registry.value?.isSubmittable || Number(meta.value?.is_submittable) === 1,
)
const hasStatusSignal = computed(
	() => isSubmittable.value || isWorkflow.value || metaFieldSet.value.has("status"),
)

function colType(ft) {
	if (ft === "Date") return "Date"
	if (ft === "Datetime") return "Datetime"
	if (ft === "Currency") return "Currency"
	return undefined
}

// Column descriptors resolved against meta (same shape the page renderers use).
const colDescs = computed(() => {
	const fields = meta.value?.fields || []
	const byName = new Map(fields.map((f) => [f.fieldname, f]))
	const mk = (fieldname, label) => {
		const f = byName.get(fieldname)
		if (!f) return null // unknown field drops silently
		return {
			field: f.fieldname,
			label: label || getFieldLabel(props.doctype, f.fieldname) || f.label || f.fieldname,
			type: colType(f.fieldtype),
			isLink: f.fieldtype === "Link",
			linkTarget: f.fieldtype === "Link" ? f.options || "" : "",
		}
	}
	if (Array.isArray(props.columns) && props.columns.length) {
		const out = []
		for (const c of props.columns) {
			const desc =
				typeof c === "string" ? mk(c) : c && c.field ? mk(c.field, c.label) : null
			if (desc) out.push(desc)
		}
		return out
	}
	return fields
		.filter((f) => f.in_list_view && !f.hidden && f.fieldname !== "name")
		.map((f) => mk(f.fieldname))
		.filter(Boolean)
})

// Kanban group field: the prop when it's a real meta field, else "" → status.
const resolvedGroupField = computed(() =>
	props.groupBy && metaFieldSet.value.has(props.groupBy) ? props.groupBy : "",
)

// Kanban without a group source degrades to table (demo renderKanban parity).
// While meta is still loading, honor the requested variant so the skeleton
// matches the final presentation (no table→kanban layout jump on first paint).
const effectiveVariant = computed(() => {
	if (props.variant === "cards") return "cards"
	if (props.variant === "kanban") {
		if (!meta.value) return "kanban"
		return resolvedGroupField.value || hasStatusSignal.value ? "kanban" : "table"
	}
	return "table"
})

// Bold title: titleField prop > meta title_field > first non-status column.
const resolvedTitleField = computed(() => {
	if (props.titleField && metaFieldSet.value.has(props.titleField)) return props.titleField
	const mt = meta.value?.title_field
	if (mt && mt !== "name" && metaFieldSet.value.has(mt)) return mt
	const c = colDescs.value.find((col) => col.field !== "status")
	return c ? c.field : ""
})
const titleColDesc = computed(
	() => colDescs.value.find((c) => c.field === resolvedTitleField.value) || null,
)
const groupColDesc = computed(
	() => colDescs.value.find((c) => c.field === resolvedGroupField.value) || null,
)

const DOCSTATUS_LABELS = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }
function statusOf(r) {
	if (isWorkflow.value && r.workflow_state) return r.workflow_state
	if (typeof r.status === "string" && r.status) return r.status
	if (isSubmittable.value) return DOCSTATUS_LABELS[r.docstatus] || ""
	return ""
}

function chipStyle(r) {
	return statusChipStyle(statusOf(r), isDark.value)
}

function formatNumber(val) {
	if (val === null || val === undefined || val === "") return "—"
	const n = Number(val)
	return Number.isNaN(n) ? val : n.toLocaleString("en-IN")
}

function cellValue(col, row) {
	if (col.type === "Date" || col.type === "Datetime") return formatDate(row[col.field])
	if (col.type === "Currency") return formatNumber(row[col.field])
	if (col.isLink && row[col.field]) {
		return linkTitles.linkParts(col.linkTarget, row[col.field], row[`${col.field}_name`]).primary
	}
	return row[col.field] ?? "—"
}

function titleOf(row) {
	const f = resolvedTitleField.value
	if (!f) return row.name
	const v = titleColDesc.value ? cellValue(titleColDesc.value, row) : row[f]
	return v === null || v === undefined || v === "" || v === "—" ? row.name : String(v)
}

function groupOf(row) {
	if (!resolvedGroupField.value) return statusOf(row) || "—"
	const raw = row[resolvedGroupField.value]
	if (raw === null || raw === undefined || raw === "") return "—"
	return groupColDesc.value ? String(cellValue(groupColDesc.value, row)) : String(raw)
}

// cardTemplate-bound row fields (cards/kanban only): first segment of every
// bind path, meta-checked so a typo'd path can't 500 the list call — the
// composite block's boundRowFields posture, scope = the row itself here.
const TEMPLATE_FIELDNAME_RE = /^[a-z0-9_]+$/
const templateBoundFields = computed(() => {
	if (!props.cardTemplate || effectiveVariant.value === "table") return []
	const fields = new Set()
	for (const path of collectBindPaths(props.cardTemplate)) {
		const f = path.split(".")[0]
		if (TEMPLATE_FIELDNAME_RE.test(f) && metaFieldSet.value.has(f)) fields.add(f)
	}
	return [...fields]
})

// ── fetch (existing list API — server re-checks permission regardless) ──
const fetchFields = computed(() => {
	const fields = ["name", "docstatus", "modified"]
	for (const c of colDescs.value) if (!fields.includes(c.field)) fields.push(c.field)
	if (resolvedTitleField.value && !fields.includes(resolvedTitleField.value)) {
		fields.push(resolvedTitleField.value)
	}
	if (resolvedGroupField.value && !fields.includes(resolvedGroupField.value)) {
		fields.push(resolvedGroupField.value)
	}
	for (const f of templateBoundFields.value) if (!fields.includes(f)) fields.push(f)
	if (metaFieldSet.value.has("status") && !fields.includes("status")) fields.push("status")
	if (isWorkflow.value && !fields.includes("workflow_state")) fields.push("workflow_state")
	return fields
})

// Stale-response guard: every fetch (and every re-init) takes a fresh token;
// only the LATEST one may write rows — a slow response for the OUTGOING
// doctype can never clobber the incoming doctype's rows.
let fetchSeq = 0

async function fetchRows(silent = false) {
	if (!allowed.value) return
	const seq = ++fetchSeq
	if (!silent) loading.value = true
	try {
		const res = await getList(props.doctype, {
			fields: fetchFields.value,
			order_by: "modified desc",
			limit_page_length: Math.max(1, Number(props.pageSize) || 8),
		})
		if (seq !== fetchSeq) return // superseded by a newer fetch / re-init
		rowsData.value = res.data || []
		primeLinks()
	} catch (_) {
		if (seq !== fetchSeq) return
		if (!silent) rowsData.value = []
	} finally {
		// Only the current fetch may clear the skeleton (a superseded one would
		// hide the loading state the newer fetch still owns).
		if (seq === fetchSeq) loading.value = false
	}
}

// Batch-resolve Link columns to human names (same pattern as the list page).
function primeLinks() {
	const cols = [...colDescs.value]
	for (const extra of [titleColDesc.value, groupColDesc.value]) {
		if (extra && !cols.some((c) => c.field === extra.field)) cols.push(extra)
	}
	const linkCols = cols.filter((c) => c.isLink && c.linkTarget)
	if (!linkCols.length || !rowsData.value.length) return
	const pairs = []
	for (const row of rowsData.value) {
		for (const c of linkCols) {
			const v = row[c.field]
			if (v && !row[`${c.field}_name`]) pairs.push({ doctype: c.linkTarget, name: v })
		}
	}
	if (pairs.length) linkTitles.prime(pairs)
}

// ── navigation: only when a /web route exists (2026-07-07 link rule —
// never bounce into the Desk). No route → cards render but aren't links. ──
function openRecord(row) {
	if (!route.value || !row?.name) return
	router.push(`/${route.value}/${encodeURIComponent(row.name)}`)
}

function viewAll() {
	if (route.value) router.push(`/${route.value}`)
}

// ── realtime: silent refresh when any record of this doctype changes ──
const { subscribeList } = useRealtime()
let rtDispose = null

// Full (re-)init: ScreenRenderer patches block props IN PLACE on a config
// refresh (same block id ⇒ same component instance), so a doctype change must
// reset meta/rows, refetch, and swap the realtime subscription to the new
// doctype's room — otherwise the block keeps stale content and a stale
// subscription. Runs once on mount and again on every doctype prop change.
async function init() {
	if (rtDispose) {
		rtDispose()
		rtDispose = null
	}
	meta.value = null
	rowsData.value = []
	fetchSeq++ // invalidate any in-flight fetch for the outgoing doctype
	loading.value = false
	if (!allowed.value) return
	const dt = props.doctype
	loading.value = true
	try {
		const docs = await getMeta(dt)
		if (dt !== props.doctype) return // changed again mid-flight — that init owns the state
		meta.value = docs?.[0] || null
	} catch (_) {
		if (dt !== props.doctype) return
		meta.value = null
	}
	await fetchRows()
	if (dt !== props.doctype) return
	rtDispose = subscribeList(dt, () => fetchRows(true))
}

onMounted(init)

// doctype patched in place (config refresh / knob edit) → full re-init.
watch(() => props.doctype, () => init())

// Row-shaping knobs (columns/groupBy/titleField/pageSize/cardTemplate) only
// change WHAT is fetched/rendered for the SAME doctype → refetch rows; meta
// and the realtime subscription stay. JSON keys the columns array (and the
// cardTemplate tree — its bind paths feed templateBoundFields) by VALUE so an
// in-place replacement with equal content doesn't refetch.
watch(
	() =>
		[
			JSON.stringify(props.columns ?? null),
			props.groupBy,
			props.titleField,
			props.pageSize,
			JSON.stringify(props.cardTemplate ?? null),
		].join("|"),
	() => {
		if (!meta.value) return // init in flight — its fetch reads the latest props
		fetchRows()
	},
)

onUnmounted(() => {
	if (rtDispose) rtDispose()
})
</script>

<style scoped>
.rl-card {
	display: flex;
	flex-direction: column;
}

.rl-head {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 11px 14px;
	border-bottom: 1px solid var(--esd-line);
}

.rl-title {
	font-size: 13.5px;
	font-weight: 700;
	color: var(--esd-ink);
}

.rl-spacer {
	flex: 1;
}

.rl-viewall {
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
}

.rl-viewall i {
	font-size: 11px;
}

.rl-viewall:hover {
	text-decoration: underline;
}

.rl-body {
	padding: 14px;
}

.rl-scroll {
	overflow-x: auto;
}

.rl-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 13px;
}

.rl-table th {
	text-align: left;
	padding: 9px 16px;
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
	font-weight: 700;
	border-bottom: 1px solid var(--esd-line);
	white-space: nowrap;
}

.rl-table td {
	padding: 10px 16px;
	border-bottom: 1px solid var(--esd-line);
	white-space: nowrap;
}

.rl-table tbody tr:last-child td {
	border-bottom: 0;
}

.rl-table tbody tr.rl-openable {
	cursor: pointer;
	transition: background 0.12s;
}

.rl-table tbody tr.rl-openable:hover {
	background: var(--esd-slate-50);
}

.rl-code {
	font-weight: 600;
	color: var(--esd-accent-700);
}

.rl-chip {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	font-size: 11px;
	font-weight: 700;
	padding: 3px 10px;
	border-radius: 999px;
	white-space: nowrap;
}

.rl-chip-dot {
	width: 7px;
	height: 7px;
	border-radius: 50%;
	background: currentColor;
	flex: none;
}

.rl-empty {
	text-align: center;
	color: var(--esd-muted);
	padding: 22px;
	font-size: 13px;
}

.rl-skel {
	height: 12px;
	border-radius: 6px;
	background: linear-gradient(90deg, var(--esd-slate-50), var(--esd-line), var(--esd-slate-50));
	background-size: 200% 100%;
	animation: rl-shimmer 1.2s infinite;
}

@keyframes rl-shimmer {
	from {
		background-position: 200% 0;
	}
	to {
		background-position: -200% 0;
	}
}
</style>
