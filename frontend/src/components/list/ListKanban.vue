<!-- ListKanban — the "kanban" list-presentation variant (layout knob
     listViews[<DocType>].variant = "kanban" + listViews[<DocType>].groupBy).

     Behavioral reference: "custom ui/demos/_template.html" §7 renderKanban —
     one column per distinct group value (in fetched-row order) with a count
     header, status-tinted compact cards, click → detail. DISPLAY-ONLY v1: no
     drag between columns. Pure presentation over the host's fetch layer —
     grouping happens on the already-fetched (already permission-checked,
     already filtered) page of rows.

     Props:
       rows       : Array — the fetched page of records
       columns    : Array of {field,label,type,isLink,linkTarget} key columns
       titleField : String — fieldname of the bold card title (kv-excluded)
       titleOf    : (row) => String — resolved bold title text
       statusOf   : (row) => String — status chip text ("" = no chip/tint)
       cellValue  : (col, row) => String — the host's cell formatter
       groupOf    : (row) => String — the column a row belongs to (the host
                    resolves the groupBy field / status fallback + labels)
       groupField : String — the grouped fieldname, excluded from kv rows
                    ("" when grouping by the synthesized status)
       loading    : Boolean — render skeleton columns instead of rows
     Emits: open(row) — card click → detail (host owns navigation). -->
<template>
	<div class="lv-kanban">
		<template v-if="loading && !rows.length">
			<div v-for="n in 3" :key="`skc-${n}`" class="lv-kcol" aria-hidden="true">
				<div class="lv-kcol__head"><span class="lv-skel" style="width: 70px" /></div>
				<div v-for="m in 2" :key="`sk-${n}-${m}`" class="lv-kcard is-skel">
					<div class="lv-skel" style="width: 60%" />
					<div class="lv-skel" style="width: 85%" />
				</div>
			</div>
		</template>
		<template v-else>
			<div v-for="g in groups" :key="g.label" class="lv-kcol">
				<div class="lv-kcol__head">
					{{ g.label }}
					<span class="lv-kcol__count">{{ g.items.length }}</span>
				</div>
				<article
					v-for="r in g.items"
					:key="r.name"
					class="lv-kcard"
					:style="cardStyle(r)"
					tabindex="0"
					@click="$emit('open', r)"
					@keydown.enter="$emit('open', r)"
				>
					<div class="lv-kcard__top">
						<span class="lv-kcard__id">{{ r.name }}</span>
						<span v-if="statusOf(r)" class="lv-kcard__chip" :style="chipStyle(r)">
							<i class="lv-kcard__chip-dot" />{{ statusOf(r) }}
						</span>
					</div>
					<div class="lv-kcard__title">{{ titleOf(r) }}</div>
					<div v-for="c in kvColumns" :key="c.field" class="lv-kcard__kv">
						<span class="lv-kcard__k">{{ c.label }}</span>
						<span class="lv-kcard__v">{{ cellValue(c, r) }}</span>
					</div>
				</article>
			</div>
		</template>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { statusChipStyle, statusColor, statusTint } from "@yrp/web-engine"
import { useTheme } from "@/composables/useTheme"

const props = defineProps({
	rows: { type: Array, default: () => [] },
	columns: { type: Array, default: () => [] },
	titleField: { type: String, default: "" },
	titleOf: { type: Function, required: true },
	statusOf: { type: Function, required: true },
	cellValue: { type: Function, required: true },
	groupOf: { type: Function, required: true },
	groupField: { type: String, default: "" },
	loading: { type: Boolean, default: false },
})

defineEmits(["open"])

const { isDark } = useTheme()

// One column per DISTINCT group value, in fetched-row order (demo parity —
// the fetch layer's order_by decides which group appears first).
const groups = computed(() => {
	const byLabel = new Map()
	for (const r of props.rows) {
		const label = props.groupOf(r) || "—"
		if (!byLabel.has(label)) byLabel.set(label, { label, items: [] })
		byLabel.get(label).items.push(r)
	}
	return [...byLabel.values()]
})

// Compact card: kv rows exclude the title, the status chip, and the grouped
// field (its value is the column header — repeating it is noise).
const kvColumns = computed(() =>
	props.columns.filter(
		(c) => c.field !== props.titleField && c.field !== "status" && c.field !== "name" && c.field !== props.groupField
	)
)

function cardStyle(r) {
	const s = props.statusOf(r)
	if (!s) return null
	const dark = isDark.value
	return {
		background: statusTint(s, dark, dark ? 0.13 : 0.06),
		borderTopColor: statusColor(s, dark),
	}
}

function chipStyle(r) {
	return statusChipStyle(props.statusOf(r), isDark.value)
}
</script>

<style scoped>
/* Demo .kanban board — columns side by side, horizontal scroll when narrow. */
.lv-kanban {
	display: flex;
	gap: 14px;
	align-items: flex-start;
	overflow-x: auto;
	padding-bottom: 4px;
}

.lv-kcol {
	flex: 1;
	min-width: 232px;
	background: var(--esd-slate-50);
	border-radius: var(--radius);
	padding: 10px;
	display: flex;
	flex-direction: column;
	gap: 10px;
}

.lv-kcol__head {
	display: flex;
	align-items: center;
	gap: 8px;
	font-weight: 700;
	font-size: 13px;
	color: var(--esd-ink);
	padding: 2px 4px;
}

.lv-kcol__count {
	margin-left: auto;
	font-size: 11px;
	font-weight: 600;
	color: var(--esd-muted);
	background: var(--esd-card);
	padding: 1px 8px;
	border-radius: 999px;
}

.lv-kcard {
	display: flex;
	flex-direction: column;
	gap: 6px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-top: 3px solid var(--esd-line);
	border-radius: calc(var(--radius) - 2px);
	padding: 10px 12px;
	cursor: pointer;
	box-shadow: var(--esd-shadow-card);
	transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.lv-kcard:not(.is-skel):hover {
	transform: translateY(-1px);
	box-shadow: var(--esd-shadow-pop);
}

.lv-kcard:focus-visible {
	outline: 2px solid var(--esd-accent);
	outline-offset: 1px;
}

.lv-kcard__top {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 8px;
}

.lv-kcard__id {
	font-size: 10.5px;
	color: var(--esd-muted);
	font-weight: 700;
	letter-spacing: 0.04em;
}

.lv-kcard__chip {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	font-size: 10.5px;
	font-weight: 700;
	padding: 2px 9px;
	border-radius: 999px;
	white-space: nowrap;
}

.lv-kcard__chip-dot {
	width: 6px;
	height: 6px;
	border-radius: 50%;
	background: currentColor;
	flex: none;
}

.lv-kcard__title {
	font-weight: 650;
	font-size: 13.5px;
	line-height: 1.3;
	color: var(--esd-ink);
	overflow-wrap: anywhere;
}

.lv-kcard__kv {
	display: flex;
	justify-content: space-between;
	gap: 10px;
	font-size: 12px;
}

.lv-kcard__k {
	color: var(--esd-muted);
	white-space: nowrap;
}

.lv-kcard__v {
	font-weight: 600;
	color: var(--esd-ink-2);
	text-align: right;
	overflow-wrap: anywhere;
}

.lv-kempty {
	text-align: center;
	color: var(--esd-muted);
	font-size: 12.5px;
	padding: 14px 0;
}

.lv-skel {
	display: block;
	height: 12px;
	border-radius: 6px;
	background: linear-gradient(90deg, var(--esd-slate-50), var(--esd-line), var(--esd-slate-50));
	background-size: 200% 100%;
	animation: lv-shimmer 1.2s infinite;
}

@keyframes lv-shimmer {
	from {
		background-position: 200% 0;
	}
	to {
		background-position: -200% 0;
	}
}
</style>
