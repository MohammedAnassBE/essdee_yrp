<!-- composite block — the bounded composition layer's home-block host
     (USE_CASE §3(c)/(d), Track 1 item 1).

     A layout composes a validated tree of the engine's 13 code-owned
     primitives (stack, grid, card, heading, text, kv-row, badge, stat,
     divider, icon, progress, image[site files], spacer) and binds leaf values
     by DOT-PATH into data THIS host fetched. The tree can never define DOM,
     queries or logic — rendering is @yrp/web-engine CompositeTree; this file
     owns exactly what every host block owns: fetch, permissions, realtime.

     Layout contract (knobs are props, spec §6.4):
       { "type": "composite", "props": {
           "source": {                       // which registry data feeds the scope
             "metrics": ["open_lots", ...],  //   ui_metrics registry names (optional)
             "doctype": "Work Order",        //   recent records of one doctype (optional)
             "limit": 5                      //   1–20, default 5 (with doctype only)
           },
           "tree": { "type": "stack", "children": [ ... ] } } }

     The binding scope this host supplies (dot-path roots — nothing else):
       metrics.<name>.value / metrics.<name>.label   — get_ui_metrics results
       rows.<index>.<fieldname>                       — recent records of
         source.doctype, newest-modified first, exactly like record-list: the
         SAME permission-gated list API, fields DERIVED from the tree's bind
         paths (the JSON names fields, never a query — no filters knob).

     Permissions (§15, arrangement never grants capability):
       - source.doctype without canRead → the block renders NOTHING;
         the server re-checks the list call regardless.
       - metrics are per-metric permission-gated server-side (ui_metrics);
         omitted metrics leave their bindings at the honest em-dash.
     Realtime: source.doctype rows silently refresh via subscribeList. -->
<template>
	<CompositeTree
		v-if="allowed"
		:tree="tree"
		:scope="scope"
		:date-format="ui.active.dateFormat || ''"
		:dark="isDark"
	/>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, watch } from "vue"
import { CompositeTree, collectBindPaths, useUiConfigStore } from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { useRealtime } from "@/composables/useRealtime"
import { useTheme } from "@/composables/useTheme"
import { getList, getMeta, callMethod } from "@/api/client"

defineOptions({ inheritAttrs: false })

// The metrics endpoint (same registry summary-tiles reads).
const METRICS_METHOD = "yrp.yrp.api.ui_metrics.get_ui_metrics"
const FIELDNAME_RE = /^[a-z0-9_]+$/

const props = defineProps({
	// Host-fetched data sources feeding the binding scope (layout knob).
	source: { type: Object, default: null },
	// The validated primitive tree (layout knob; engine renders it).
	tree: { type: Object, default: null },
})

const ui = useUiConfigStore()
const { canRead } = usePermissions()
const { isDark } = useTheme()
const { subscribeList } = useRealtime()

const scope = reactive({ metrics: {}, rows: [] })

const listDoctype = computed(() => {
	const dt = props.source?.doctype
	return typeof dt === "string" && dt.trim() ? dt : ""
})
const metricKeys = computed(() => {
	const keys = props.source?.metrics
	return Array.isArray(keys) ? keys.filter((k) => typeof k === "string" && k) : []
})
const limit = computed(() => {
	const n = Number(props.source?.limit)
	return Number.isInteger(n) && n >= 1 && n <= 20 ? n : 5
})

// canRead gate: a declared list source the user can't read hides the whole
// block (record-list parity). Metrics-only / static trees always render.
const allowed = computed(() => !!props.tree && (!listDoctype.value || canRead(listDoctype.value)))

// Fields to fetch = the tree's own bind paths under rows.<i>.<field> —
// the JSON names fields (like record-list columns), never a query.
const boundRowFields = computed(() => {
	const fields = new Set()
	for (const path of collectBindPaths(props.tree || {})) {
		const seg = path.split(".")
		if (seg[0] === "rows" && /^\d+$/.test(seg[1] || "") && FIELDNAME_RE.test(seg[2] || "")) {
			fields.add(seg[2])
		}
	}
	return [...fields]
})

let requestSeq = 0 // stale-response guard for both fetches
let rtDispose = null

async function loadMetrics(seq) {
	const wanted = metricKeys.value
	if (!wanted.length) {
		if (seq === requestSeq) scope.metrics = {}
		return
	}
	try {
		const res = await callMethod(METRICS_METHOD, { keys: wanted })
		if (seq !== requestSeq) return
		if (Array.isArray(res?.warnings) && res.warnings.length)
			console.warn("[yrp-web] composite: metrics warnings:", res.warnings)
		const list = Array.isArray(res) ? res : Array.isArray(res?.metrics) ? res.metrics : []
		const out = {}
		for (const m of list) {
			if (m && typeof m === "object" && m.key != null)
				out[String(m.key)] = { label: m.label ?? String(m.key), value: m.value ?? null }
		}
		scope.metrics = out // omitted (unknown/unpermitted) keys stay unresolved → em-dash
	} catch (err) {
		if (seq !== requestSeq) return
		console.warn("[yrp-web] composite: get_ui_metrics failed — metric bindings stay em-dash", err)
		scope.metrics = {}
	}
}

async function loadRows(seq, silent = false) {
	const dt = listDoctype.value
	if (!dt || !allowed.value) {
		if (seq === requestSeq) scope.rows = []
		return
	}
	try {
		// Meta round-trip (record-list parity): only real meta fields go into
		// the fields param, so a typo'd bind path can't 500 the list call.
		const docs = await getMeta(dt)
		if (seq !== requestSeq) return
		const metaFields = new Set((docs?.[0]?.fields || []).map((f) => f.fieldname))
		const fields = ["name", "docstatus", "modified"]
		for (const f of boundRowFields.value) {
			if (metaFields.has(f) && !fields.includes(f)) fields.push(f)
		}
		const res = await getList(dt, {
			fields,
			order_by: "modified desc",
			limit_page_length: limit.value,
		})
		if (seq !== requestSeq) return
		scope.rows = res.data || []
	} catch (err) {
		if (seq !== requestSeq) return
		console.warn(`[yrp-web] composite: list fetch for "${dt}" failed — row bindings stay em-dash`, err)
		if (!silent) scope.rows = []
	}
}

function resubscribe() {
	if (rtDispose) {
		rtDispose()
		rtDispose = null
	}
	const dt = listDoctype.value
	if (dt && allowed.value) {
		// Silent row refresh on any change of the doctype (base-owned socket).
		rtDispose = subscribeList(dt, () => loadRows(requestSeq, true))
	}
}

function init() {
	const seq = ++requestSeq
	loadMetrics(seq)
	loadRows(seq)
	resubscribe()
}

onMounted(init)

// Knobs are patched IN PLACE on config refresh / preview — re-init on any
// source change; a tree change can alter the bound row fields, so refetch
// rows for the same doctype too (cheap, bounded).
watch(
	() => [JSON.stringify(props.source ?? null), boundRowFields.value.join("|")].join("::"),
	() => init()
)

onUnmounted(() => {
	if (rtDispose) rtDispose()
})
</script>
