<!-- story-scroller block — the last missing demo topology (USE_CASE §4 Track 1
     item 7). A horizontal snap feed (or vertical side rail) of the most recent
     records of ONE doctype, each a "story" chip: a status-dot avatar with the
     record code + a few fields.

       { "type": "story-scroller", "props": {
           "source": "Work Order",              // the DocType to scroll
           "fields": ["item", "process_name"],  // sub-lines per chip (optional)
           "limit": 12,                         // how many recent records
           "orientation": "horizontal" } }      // | "vertical"

     Same host-owned plumbing as record-list — nothing new: getList off the
     existing list API (server re-checks permission on every call), silent
     realtime refresh via subscribeList, statusColors for the dot, and
     tap-through to the /web route when one exists. The canRead gate renders
     NOTHING without permission — arrangement never grants capability (§15).
     The JSON names source/fields/limit/orientation; it never names a query. -->
<template>
	<div
		v-if="allowed"
		class="ss-rail"
		:class="orientation === 'vertical' ? 'ss-vertical' : 'ss-horizontal'"
	>
		<template v-if="loading">
			<div v-for="n in skeletonCount" :key="`sk-${n}`" class="ss-story ss-skel-story">
				<div class="ss-avatar ss-skel" />
				<div class="ss-skel ss-skel-label" />
			</div>
		</template>
		<template v-else-if="rowsData.length">
			<button
				v-for="r in rowsData"
				:key="r.name"
				type="button"
				class="ss-story"
				:class="{ 'ss-openable': !!route }"
				@click="openRecord(r)"
			>
				<span class="ss-avatar" :style="avatarStyle(r)">
					<span class="ss-avatar-dot" />
				</span>
				<span class="ss-label">{{ r.name }}</span>
				<span v-for="f in subFields" :key="f.field" class="ss-sub">{{ cellValue(f, r) }}</span>
			</button>
		</template>
		<div v-else class="ss-empty">No records yet</div>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from "vue"
import { useRouter } from "vue-router"
import { formatDate, statusChipStyle } from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { useRealtime } from "@/composables/useRealtime"
import { useTheme } from "@/composables/useTheme"
import { getRegistryByDoctype } from "@/config/doctypes"
import { getList, getMeta } from "@/api/client"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	source: { type: String, required: true }, // the DocType to scroll
	fields: { type: Array, default: null }, // sub-line fieldnames per chip
	limit: { type: Number, default: 12 }, // how many recent records
	orientation: {
		type: String,
		default: "horizontal",
		validator: (v) => ["horizontal", "vertical"].includes(v),
	},
})

const router = useRouter()
const { canRead } = usePermissions()
const { isDark } = useTheme()

// canRead gate: no read permission ⇒ the block renders NOTHING (§15).
const allowed = computed(() => !!props.source && canRead(props.source))

const registry = computed(() => getRegistryByDoctype(props.source) || null)
const route = computed(() => registry.value?.route || "")
const isWorkflow = computed(() => registry.value?.isWorkflow || false)

const meta = shallowRef(null)
const rowsData = ref([])
const loading = ref(false)

const metaFieldSet = computed(() => new Set((meta.value?.fields || []).map((f) => f.fieldname)))
const isSubmittable = computed(
	() => registry.value?.isSubmittable || Number(meta.value?.is_submittable) === 1,
)

const boundedLimit = computed(() => {
	const n = Number(props.limit)
	if (!Number.isFinite(n)) return 12
	return Math.min(30, Math.max(1, Math.round(n)))
})
const skeletonCount = computed(() => Math.min(6, boundedLimit.value))

function colType(ft) {
	if (ft === "Date") return "Date"
	if (ft === "Datetime") return "Datetime"
	if (ft === "Currency") return "Currency"
	return undefined
}

// Sub-line descriptors: the fields prop, resolved against meta (unknown fields
// drop silently — the server validator already warned at save).
const subFields = computed(() => {
	if (!Array.isArray(props.fields) || !props.fields.length) return []
	const byName = new Map((meta.value?.fields || []).map((f) => [f.fieldname, f]))
	const out = []
	for (const name of props.fields) {
		const f = byName.get(name)
		if (f) out.push({ field: f.fieldname, type: colType(f.fieldtype) })
	}
	return out
})

const DOCSTATUS_LABELS = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }
function statusOf(r) {
	if (isWorkflow.value && r.workflow_state) return r.workflow_state
	if (typeof r.status === "string" && r.status) return r.status
	if (isSubmittable.value) return DOCSTATUS_LABELS[r.docstatus] || ""
	return ""
}

function avatarStyle(r) {
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
	return row[col.field] ?? "—"
}

// ── fetch (existing list API — server re-checks permission regardless) ──
const fetchFields = computed(() => {
	const fields = ["name", "docstatus", "modified"]
	for (const f of subFields.value) if (!fields.includes(f.field)) fields.push(f.field)
	if (metaFieldSet.value.has("status") && !fields.includes("status")) fields.push("status")
	if (isWorkflow.value && !fields.includes("workflow_state")) fields.push("workflow_state")
	return fields
})

// Stale-response guard: only the LATEST fetch may write rows.
let fetchSeq = 0

async function fetchRows(silent = false) {
	if (!allowed.value) return
	const seq = ++fetchSeq
	if (!silent) loading.value = true
	try {
		const res = await getList(props.source, {
			fields: fetchFields.value,
			order_by: "modified desc",
			limit_page_length: boundedLimit.value,
		})
		if (seq !== fetchSeq) return
		rowsData.value = res.data || []
	} catch (_) {
		if (seq !== fetchSeq) return
		if (!silent) rowsData.value = []
	} finally {
		if (seq === fetchSeq) loading.value = false
	}
}

function openRecord(row) {
	if (!route.value || !row?.name) return
	router.push(`/${route.value}/${encodeURIComponent(row.name)}`)
}

// ── realtime: silent refresh when any record of this doctype changes ──
const { subscribeList } = useRealtime()
let rtDispose = null

// Full (re-)init: ScreenRenderer patches props in place on a config refresh, so
// a source change must reset meta/rows, refetch and swap the realtime room.
async function init() {
	if (rtDispose) {
		rtDispose()
		rtDispose = null
	}
	meta.value = null
	rowsData.value = []
	fetchSeq++
	loading.value = false
	if (!allowed.value) return
	const dt = props.source
	loading.value = true
	try {
		const docs = await getMeta(dt)
		if (dt !== props.source) return
		meta.value = docs?.[0] || null
	} catch (_) {
		if (dt !== props.source) return
		meta.value = null
	}
	await fetchRows()
	if (dt !== props.source) return
	rtDispose = subscribeList(dt, () => fetchRows(true))
}

onMounted(init)

// source patched in place → full re-init.
watch(() => props.source, () => init())

// fields/limit only change WHAT is fetched for the same doctype → refetch rows.
watch(
	() => [JSON.stringify(props.fields ?? null), props.limit].join("|"),
	() => {
		if (!meta.value) return
		fetchRows()
	},
)

onUnmounted(() => {
	if (rtDispose) rtDispose()
})
</script>

<style scoped>
.ss-rail {
	display: flex;
	gap: 14px;
	padding: 14px;
}

.ss-horizontal {
	flex-direction: row;
	overflow-x: auto;
	scroll-snap-type: x mandatory;
}

.ss-vertical {
	flex-direction: column;
	overflow-y: auto;
	max-height: 420px;
}

.ss-story {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 4px;
	flex: none;
	width: 92px;
	background: none;
	border: 0;
	padding: 0;
	font-family: inherit;
	scroll-snap-align: start;
	text-align: center;
}

.ss-vertical .ss-story {
	flex-direction: row;
	width: auto;
	justify-content: flex-start;
	text-align: left;
}

.ss-openable {
	cursor: pointer;
}

.ss-avatar {
	width: 48px;
	height: 48px;
	border-radius: 50%;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	flex: none;
	border: 2px solid currentColor;
}

.ss-avatar-dot {
	width: 12px;
	height: 12px;
	border-radius: 50%;
	background: currentColor;
}

.ss-label {
	font-size: 12px;
	font-weight: 700;
	color: var(--esd-ink);
	max-width: 88px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.ss-sub {
	font-size: 11px;
	color: var(--esd-muted);
	max-width: 88px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.ss-vertical .ss-label,
.ss-vertical .ss-sub {
	max-width: none;
}

.ss-openable:hover .ss-label {
	color: var(--esd-accent-700);
}

.ss-empty {
	color: var(--esd-muted);
	font-size: 13px;
	padding: 8px;
}

.ss-skel {
	background: linear-gradient(90deg, var(--esd-slate-50), var(--esd-line), var(--esd-slate-50));
	background-size: 200% 100%;
	animation: ss-shimmer 1.2s infinite;
}

.ss-skel-story {
	pointer-events: none;
}

.ss-skel-label {
	width: 60px;
	height: 10px;
	border-radius: 5px;
}

@keyframes ss-shimmer {
	from {
		background-position: 200% 0;
	}
	to {
		background-position: -200% 0;
	}
}
</style>
