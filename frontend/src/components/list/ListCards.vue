<!-- ListCards — the "cards" list-presentation variant (layout knob
     listViews[<DocType>].variant = "cards", spec §6.4 knobs-are-props).

     Behavioral reference: "custom ui/demos/_template.html" §7 renderCards with
     colourBy:"status" + cardFields:"columns" — status-TINTED card (wash
     background + 3px top border from the engine statusColors registry), record
     id small + status chip on the top row, BOLD title line, and every key
     column as a label:value row. Pure presentation: rows/columns/formatting
     arrive as props from the host (DynamicListPage or the record-list block),
     so data, permissions and filters stay in the existing fetch layer.

     Props (all display-only):
       rows       : Array — the fetched page of records
       columns    : Array of {field,label,type,isLink,linkTarget} key columns
       titleField : String — fieldname rendered as the bold title (excluded
                    from the kv rows); "" → title falls back to the docname
       titleOf    : (row) => String — resolved bold title text
       statusOf   : (row) => String — status chip text ("" = no chip/tint)
       cellValue  : (col, row) => String — the host's cell formatter (dates,
                    currency, resolved Link names)
       loading    : Boolean — render skeleton cards instead of rows
       cardTemplate : Object|null — OPTIONAL composite tree (USE_CASE §3(c),
                    Track 1 item 2) rendering EACH card's interior; binding
                    scope = the ROW record (bind paths are fieldnames, e.g.
                    {bind:"planned_quantity", format:"qty"}), same engine
                    grammar/binding resolver as the `composite` block. ABSENT
                    (null / not a plain object) → the default interior below
                    renders BYTE-IDENTICAL to today (parity law). The template
                    shapes ONLY the interior: the card shell — grid cell,
                    status tint, click → open(row), focus ring — stays host-
                    owned either way. The layout's dateFormat knob feeds the
                    tree's `date` formatter (composite-block parity; the
                    DEFAULT interior keeps the host cellValue's dd-mm-yyyy).
     Emits: open(row) — card click → detail (host owns navigation). -->
<template>
	<div class="lv-cards" role="list">
		<template v-if="loading && !rows.length">
			<div v-for="n in 6" :key="`sk-${n}`" class="lv-card is-skel" aria-hidden="true">
				<div class="lv-skel" style="width: 55%" />
				<div class="lv-skel" style="width: 80%" />
				<div class="lv-skel" style="width: 40%" />
			</div>
		</template>
		<template v-else>
			<article
				v-for="r in rows"
				:key="r.name"
				class="lv-card"
				:class="{ tinted: !!statusOf(r) }"
				:style="cardStyle(r)"
				role="listitem"
				tabindex="0"
				@click="$emit('open', r)"
				@keydown.enter="$emit('open', r)"
			>
				<!-- cardTemplate seam (Track 1 item 2): a composite tree shapes the
				     interior, scope = the row. Knob absent → the v-else branch IS
				     the pre-existing default markup, untouched (parity law). -->
				<CompositeTree
					v-if="hasCardTemplate"
					:tree="cardTemplate"
					:scope="r"
					:date-format="templateDateFormat"
					:dark="isDark"
				/>
				<template v-else>
					<div class="lv-card__top">
						<span class="lv-card__id">{{ r.name }}</span>
						<span v-if="statusOf(r)" class="lv-card__chip" :style="chipStyle(r)">
							<i class="lv-card__chip-dot" />{{ statusOf(r) }}
						</span>
					</div>
					<div class="lv-card__title">{{ titleOf(r) }}</div>
					<div v-for="c in kvColumns" :key="c.field" class="lv-card__kv">
						<span class="lv-card__k">{{ c.label }}</span>
						<span class="lv-card__v">{{ cellValue(c, r) }}</span>
					</div>
				</template>
			</article>
		</template>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { CompositeTree, statusChipStyle, statusColor, statusTint, useUiConfigStore } from "@yrp/web-engine"
import { useTheme } from "@/composables/useTheme"

const props = defineProps({
	rows: { type: Array, default: () => [] },
	columns: { type: Array, default: () => [] },
	titleField: { type: String, default: "" },
	titleOf: { type: Function, required: true },
	statusOf: { type: Function, required: true },
	cellValue: { type: Function, required: true },
	loading: { type: Boolean, default: false },
	cardTemplate: { type: Object, default: null },
})

defineEmits(["open"])

const { isDark } = useTheme()

// cardTemplate seam: a plain-object tree activates the template branch; any
// other shape (absent, null, array) keeps the default interior — the engine's
// CompositeTree still owns malformed-TREE honesty (shapeless root → the
// path-labelled fallback card, never a silent fall-back to the default look).
const hasCardTemplate = computed(
	() =>
		!!props.cardTemplate && typeof props.cardTemplate === "object" && !Array.isArray(props.cardTemplate)
)
// The layout's dateFormat knob feeds the tree's `date` formatter — the same
// wiring the composite home block uses (store read is template-branch-only:
// the default interior formats via the host's cellValue, untouched).
const uiStore = useUiConfigStore()
const templateDateFormat = computed(() => uiStore.active.dateFormat || "")

// kv rows = the key columns minus the two spots already occupied on the card:
// the bold title line and the status chip (the `status` column is the chip).
const kvColumns = computed(() =>
	props.columns.filter((c) => c.field !== props.titleField && c.field !== "status" && c.field !== "name")
)

// Demo renderCards tint: wash background (alpha .13 dark / .06 light) + a 3px
// top border in the status colour; statusless rows keep the plain card.
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
/* Demo .cards grid — auto-fill 252px min, host token gap/radius. */
.lv-cards {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(252px, 1fr));
	gap: 14px;
}

.lv-card {
	display: flex;
	flex-direction: column;
	gap: 8px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-top: 3px solid var(--esd-line);
	border-radius: var(--radius);
	padding: 14px;
	cursor: pointer;
	text-align: left;
	box-shadow: var(--esd-shadow-card);
	transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.lv-card:not(.is-skel):hover {
	transform: translateY(-2px);
	box-shadow: var(--esd-shadow-pop);
}

.lv-card:focus-visible {
	outline: 2px solid var(--esd-accent);
	outline-offset: 1px;
}

.lv-card__top {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 8px;
}

.lv-card__id {
	font-size: 10.5px;
	color: var(--esd-muted);
	font-weight: 700;
	letter-spacing: 0.04em;
}

.lv-card__chip {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	font-size: 11px;
	font-weight: 700;
	padding: 3px 10px;
	border-radius: 999px;
	white-space: nowrap;
}

.lv-card__chip-dot {
	width: 7px;
	height: 7px;
	border-radius: 50%;
	background: currentColor;
	flex: none;
}

.lv-card__title {
	font-weight: 700;
	font-size: 15px;
	line-height: 1.25;
	letter-spacing: -0.01em;
	color: var(--esd-ink);
	overflow-wrap: anywhere;
}

.lv-card__kv {
	display: flex;
	justify-content: space-between;
	gap: 10px;
	font-size: 12.5px;
}

.lv-card__k {
	color: var(--esd-muted);
	white-space: nowrap;
}

.lv-card__v {
	font-weight: 600;
	color: var(--esd-ink-2);
	text-align: right;
	overflow-wrap: anywhere;
}

.lv-skel {
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
