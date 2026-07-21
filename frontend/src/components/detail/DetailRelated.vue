<!-- DetailRelated — the `detail.related` single-record cross-DocType WORKBENCH
     (USE_CASE case (b), added 2026-07-21).

     Composes the OPEN document's linked records of OTHER DocTypes into its own
     detail screen: one host-styled section per related-set, each linked row
     rendered by the SAME row-scoped composite `cardTemplate` the list cards use
     (bind paths are plain fieldnames of the linked doctype). The layout only
     NAMES the sets — this host owns fetch, permissions and realtime.

     Data + permissions are base-owned. Every set is fetched via the
     permission-gated `yrp.yrp.api.ui_config.get_related` (frappe.has_permission
     + get_list) — arrangement NEVER grants capability (§15): a user without read
     on the linked doctype gets [] and that section renders NOTHING; row-level
     User Permissions trim the rows.

     Parity law: the host mounts this behind a v-if that is false whenever the
     layout carries no `detail.related[<doctype>]` — so an ordinary layout's
     detail screen is byte-identical to today. -->
<template>
	<div v-if="visibleSections.length" class="detail-related" data-testid="detail-related">
		<section
			v-for="s in visibleSections"
			:key="s.key"
			class="related-card"
			:data-testid="'related-' + s.key"
		>
			<header class="related-card__head">
				<span class="related-card__dot" />
				<span class="related-card__title">{{ s.title }}</span>
				<span v-if="s.rows.length > 1" class="related-card__count">{{ s.rows.length }}</span>
			</header>
			<div class="related-card__body">
				<article
					v-for="row in s.rows"
					:key="row.name"
					class="related-item"
				>
					<CompositeTree
						v-if="s.cardTemplate"
						:tree="s.cardTemplate"
						:scope="row"
						:date-format="dateFormat"
						:dark="isDark"
					/>
					<!-- Fallback interior when a set declares no cardTemplate: the
					     linked id + its status chip (honest, never blank). -->
					<div v-else class="related-item__fallback">
						<span class="related-item__id esd-mono">{{ row.name }}</span>
					</div>
				</article>
			</div>
		</section>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, watch } from "vue"
import { CompositeTree, collectBindPaths, useUiConfigStore } from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { useRealtime } from "@/composables/useRealtime"
import { useTheme } from "@/composables/useTheme"
import { callMethod } from "@/api/client"

defineOptions({ inheritAttrs: false })

const GET_RELATED = "yrp.yrp.api.ui_config.get_related"
const FIELDNAME_RE = /^[a-z0-9_]+$/
const DEFAULT_LIMIT = 5
const MAX_LIMIT = 20

const props = defineProps({
	// The doctype of the open document (the workbench's SOURCE).
	sourceDoctype: { type: String, default: "" },
	// The loaded source document — supplies each set's fromField value.
	sourceDoc: { type: Object, default: null },
	// The related-set list for THIS doctype (layout knob detail.related[<dt>]).
	related: { type: Array, default: () => [] },
})

const ui = useUiConfigStore()
const { canRead } = usePermissions()
const { isDark } = useTheme()
const { subscribeList } = useRealtime()

const dateFormat = computed(() => ui.active.dateFormat || "")

// Normalise the layout list into render descriptors (skip malformed entries the
// server validator only soft-warns about, so a typo never crashes the screen).
const sets = computed(() => {
	if (!Array.isArray(props.related)) return []
	const out = []
	props.related.forEach((entry, i) => {
		if (!entry || typeof entry !== "object") return
		const doctype = typeof entry.doctype === "string" ? entry.doctype.trim() : ""
		const fromField = typeof entry.fromField === "string" ? entry.fromField.trim() : ""
		const filterField = typeof entry.filterField === "string" ? entry.filterField.trim() : ""
		if (!doctype || !fromField || !filterField) return
		const cardTemplate =
			entry.cardTemplate && typeof entry.cardTemplate === "object" && !Array.isArray(entry.cardTemplate)
				? entry.cardTemplate
				: null
		let limit = Number(entry.limit)
		limit = Number.isInteger(limit) && limit >= 1 && limit <= MAX_LIMIT ? limit : DEFAULT_LIMIT
		out.push({
			key: `${i}-${doctype}`,
			doctype,
			fromField,
			filterField,
			title: typeof entry.title === "string" && entry.title.trim() ? entry.title : doctype,
			cardTemplate,
			limit,
		})
	})
	return out
})

// key → fetched rows.
const rowsByKey = reactive({})

// Only sections the user can read AND that returned rows actually render — no
// empty headers, no debug tables (one-glance workbench).
const visibleSections = computed(() =>
	sets.value
		.filter((s) => canRead(s.doctype))
		.map((s) => ({ ...s, rows: rowsByKey[s.key] || [] }))
		.filter((s) => s.rows.length)
)

// Fields to fetch = the cardTemplate's own plain-fieldname bind paths (the JSON
// NAMES fields, never a query); the server adds name/docstatus/modified.
function fieldsFor(set) {
	if (!set.cardTemplate) return []
	const out = new Set()
	for (const path of collectBindPaths(set.cardTemplate)) {
		if (FIELDNAME_RE.test(path)) out.add(path)
	}
	return [...out]
}

let requestSeq = 0
const rtDisposers = []

async function loadSet(set, seq) {
	const value = props.sourceDoc ? props.sourceDoc[set.fromField] : null
	if (value === null || value === undefined || value === "") {
		if (seq === requestSeq) rowsByKey[set.key] = []
		return
	}
	if (!canRead(set.doctype)) {
		if (seq === requestSeq) rowsByKey[set.key] = []
		return
	}
	try {
		const rows = await callMethod(GET_RELATED, {
			doctype: set.doctype,
			filter_field: set.filterField,
			filter_value: value,
			fields: JSON.stringify(fieldsFor(set)),
			limit: set.limit,
		})
		if (seq !== requestSeq) return
		rowsByKey[set.key] = Array.isArray(rows) ? rows : []
	} catch (err) {
		if (seq !== requestSeq) return
		console.warn(`[yrp-web] detail.related: get_related for "${set.doctype}" failed — section hidden`, err)
		rowsByKey[set.key] = []
	}
}

function disposeRealtime() {
	while (rtDisposers.length) {
		try {
			rtDisposers.pop()()
		} catch {
			/* noop */
		}
	}
}

function init() {
	const seq = ++requestSeq
	disposeRealtime()
	// Prune rows for sets that no longer exist (config/preview patched the list)
	// so rowsByKey never accumulates stale keys.
	const liveKeys = new Set(sets.value.map((s) => s.key))
	for (const key of Object.keys(rowsByKey)) {
		if (!liveKeys.has(key)) delete rowsByKey[key]
	}
	for (const set of sets.value) {
		loadSet(set, seq)
		if (canRead(set.doctype)) {
			// Base-owned socket: silently refresh a section when its linked
			// doctype changes anywhere (bounded, single-record).
			rtDisposers.push(subscribeList(set.doctype, () => loadSet(set, requestSeq)))
		}
	}
}

onMounted(init)

// Re-fetch whenever the open document, its identity, or the set list changes
// (config refresh / preview patches knobs in place).
watch(
	() => [
		props.sourceDoc?.name,
		props.sourceDoctype,
		JSON.stringify(props.related ?? null),
	].join("::"),
	() => init()
)

onUnmounted(disposeRealtime)
</script>

<style scoped>
.detail-related {
	display: flex;
	flex-direction: column;
	gap: 14px;
	margin-top: 4px;
}

/* Matches the native DocDetail .detail-card look so the workbench reads as one
   coherent screen (banded head + dot + accent title, hairline body). */
.related-card {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius, 12px);
	box-shadow: var(--esd-shadow-card);
	overflow: hidden;
}

.related-card__head {
	display: flex;
	align-items: center;
	gap: 9px;
	padding: 11px 16px;
	background: color-mix(in srgb, var(--esd-accent) 7%, transparent);
	border-bottom: 1px solid var(--esd-line);
}

.related-card__dot {
	width: 8px;
	height: 8px;
	border-radius: 50%;
	background: var(--esd-accent);
	flex: none;
}

.related-card__title {
	font-size: 12px;
	font-weight: 700;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--esd-accent);
}

.related-card__count {
	margin-left: auto;
	font-size: 11px;
	font-weight: 700;
	color: var(--esd-muted);
	background: color-mix(in srgb, var(--esd-accent) 12%, transparent);
	border-radius: 999px;
	padding: 1px 9px;
}

.related-card__body {
	display: flex;
	flex-direction: column;
	gap: 12px;
	padding: 14px 16px;
}

.related-item__fallback {
	display: flex;
	align-items: center;
}

.related-item__id {
	font-size: 12.5px;
	font-weight: 700;
	color: var(--esd-ink);
}
</style>
