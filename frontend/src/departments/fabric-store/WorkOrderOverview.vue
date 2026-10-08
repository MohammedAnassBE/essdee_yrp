<template>
	<div class="work-order-overview">
		<section
			v-for="group in groups"
			:key="group.key"
			class="work-order-overview__section"
			:class="{ 'work-order-overview__section--wide': group.wide }"
			:aria-labelledby="`work-order-overview-${group.key}`"
		>
			<header>
				<div class="work-order-overview__section-icon" aria-hidden="true"><i :class="group.icon" /></div>
				<div>
					<h2 :id="`work-order-overview-${group.key}`">{{ group.label }}</h2>
					<p>{{ group.description }}</p>
				</div>
			</header>
			<dl class="work-order-overview__facts">
				<div v-for="field in group.fields" :key="field.fieldname" :class="{ 'work-order-overview__fact--wide': isWide(field) }">
					<dt>{{ field.label }}</dt>
					<dd :title="String(formatValue(field))">{{ formatValue(field) }}</dd>
				</div>
			</dl>
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { plainTextFromHtml } from "../../utils/documentValues.js"

const props = defineProps({ details: { type: Array, default: () => [] } })

const definitions = [
	{
		key: "identity",
		label: "Order identity",
		description: "Production reference and execution mode",
		icon: "pi pi-id-card",
		fields: ["naming_series", "production_detail", "process_name", "is_rework", "parent_wo", "rework_type", "includes_packing", "no_receivables"],
	},
	{
		key: "delivery",
		label: "Supplier & delivery",
		description: "Commercial party and material destination",
		icon: "pi pi-truck",
		fields: ["supplier_name", "supplier", "supplier_type", "delivery_location", "delivery_location_name", "supplier_address", "supplier_address_details", "delivery_address", "delivery_address_details", "terms_and_condition"],
	},
	{
		key: "schedule",
		label: "Schedule",
		description: "Planned and actual production dates",
		icon: "pi pi-calendar",
		fields: ["planned_start_date", "planned_end_date", "expected_delivery_date", "start_date", "end_date"],
	},
	{
		key: "status",
		label: "Status & notes",
		description: "Operational state, closure and instructions",
		icon: "pi pi-clipboard",
		fields: ["open_status", "close_reason", "sd_close_reason", "close_other_reason", "close_remarks", "closed_by", "comments"],
	},
]

const groups = computed(() => {
	const byName = new Map(props.details.map((field) => [field.fieldname, field]))
	const claimed = new Set()
	const result = definitions.flatMap((definition) => {
		const fields = definition.fields.map((fieldname) => byName.get(fieldname)).filter(Boolean)
		if (!fields.length) return []
		fields.forEach((field) => claimed.add(field.fieldname))
		return [{ ...definition, fields }]
	})
	const dimensions = props.details.filter((field) => !claimed.has(field.fieldname))
	if (dimensions.length) {
		result.push({
			key: "dimensions",
			label: "Stock dimensions",
			description: "Attributes used to identify this production stock",
			icon: "pi pi-box",
			fields: dimensions,
			wide: true,
		})
	}
	return result
})

const multilineFieldtypes = new Set(["Small Text", "Text", "Long Text", "Text Editor", "Code"])

function isWide(field) {
	return multilineFieldtypes.has(field.fieldtype) && /address|comments?|notes?|remarks?|terms?/i.test(field.fieldname)
}

function formatValue(field) {
	if (["Date", "Datetime"].includes(field.fieldtype) && field.value) {
		const [year, month, day] = String(field.value).slice(0, 10).split("-")
		if (day) return `${day}-${month}-${year}${field.fieldtype === "Datetime" ? ` · ${String(field.value).slice(11, 19)}` : ""}`
	}
	if (field.fieldtype === "Check") return Number(field.value) ? "Yes" : "No"
	if (["Currency", "Float", "Int", "Percent"].includes(field.fieldtype)) return Number(field.value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
	return field.value === null || field.value === undefined || field.value === "" ? "—" : plainTextFromHtml(field.value)
}
</script>

<style scoped>
.work-order-overview { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: var(--erp-space-3); }
.work-order-overview__section { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.work-order-overview__section--wide { grid-column: 1 / -1; }
.work-order-overview__section > header { display: flex; min-height: 64px; align-items: center; gap: 10px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface-soft) 78%, white); }
.work-order-overview__section-icon { display: inline-grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center; color: var(--erp-accent-hover); border: 1px solid var(--erp-accent-border); border-radius: 9px; background: var(--erp-accent-soft); }
.work-order-overview__section-icon i { font-size: .88rem; }
.work-order-overview__section header > div:last-child { min-width: 0; }
.work-order-overview__section h2 { margin: 0; color: var(--erp-text); font-size: 14px; font-weight: 760; letter-spacing: -.01em; }
.work-order-overview__section p { margin: 2px 0 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); line-height: 1.35; }
.work-order-overview__facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }
.work-order-overview__facts > div { display: grid; min-width: 0; min-height: 62px; align-content: center; gap: 4px; padding: 10px 13px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.work-order-overview__facts > div:nth-child(2n) { border-right: 0; }
.work-order-overview__facts > div:nth-last-child(-n + 2) { border-bottom: 0; }
.work-order-overview__facts > .work-order-overview__fact--wide { grid-column: 1 / -1; border-right: 0; }
.work-order-overview__facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .035em; text-transform: uppercase; }
.work-order-overview__facts dd { min-width: 0; margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; line-height: 1.4; overflow-wrap: anywhere; text-overflow: ellipsis; white-space: nowrap; }
.work-order-overview__fact--wide dd { white-space: pre-line; }
@media (max-width: 760px) { .work-order-overview { grid-template-columns: 1fr; } .work-order-overview__section--wide { grid-column: auto; } }
</style>
