<template>
	<div
		v-if="materialGroups.length"
		class="material-requirement-groups requirement-groups"
		:class="`material-requirement-groups--${kind}`"
	>
		<section
			v-for="group in materialGroups"
			:key="group.key"
			class="material-requirement-group"
			:class="kind === 'accessory' ? 'accessory-requirement-group' : 'cloth-requirement-group'"
		>
			<header class="material-requirement-group__header requirement-group__header">
				<div class="material-requirement-group__identity requirement-group__identity">
					<strong :title="group.accessory || group.item">
						<template v-if="group.accessory">{{ group.accessory }}</template><DocumentLink v-else doctype="Item" :name="group.item" :label="group.item || 'Unspecified item'" />
					</strong>
					<span v-if="group.accessory" :title="group.item">
						<DocumentLink doctype="Item" :name="group.item" :label="group.item || 'Unspecified item'" />
					</span>
				</div>
				<div class="material-requirement-group__meta requirement-group__meta">
					<span class="material-requirement-group__type">{{ group.clothType || "Unspecified type" }}</span>
					<span class="material-requirement-group__count">{{ variantCount(group.rows.length) }}</span>
				</div>
			</header>

			<div class="material-requirement-table-wrap requirement-table-scroll" role="region" tabindex="0" :aria-label="`${kind === 'accessory' ? 'Accessory' : 'Cloth'} requirements for ${group.accessory || group.item || 'this item'}`">
				<table class="material-requirement-table requirement-table">
					<thead>
						<tr>
							<th
								v-for="column in columns"
								:key="column.field"
								:class="{ 'material-requirement-table__number': column.numeric }"
							>
								{{ column.label }}
							</th>
							<th v-if="editable" class="material-requirement-table__actions">Actions</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="entry in group.rows" :key="entry.row.name || entry.row.cloth_item_variant || entry.sourceIndex">
							<td
								v-for="column in columns"
								:key="column.field"
								:class="[
									{ 'material-requirement-table__number': column.numeric },
									column.cellClass ? column.cellClass(entry.row) : '',
								]"
							>
								{{ formatValue(column, entry.row) }}
							</td>
							<td v-if="editable" class="material-requirement-table__actions">
								<Button icon="pi pi-pencil" severity="secondary" text rounded :aria-label="`Edit ${kind}`" @click="emit('edit', entry.row, entry.sourceIndex)" />
								<Button icon="pi pi-trash" severity="danger" text rounded :aria-label="`Delete ${kind}`" :loading="busyKey === `${kind}-${entry.sourceIndex}`" @click="emit('delete', entry.sourceIndex)" />
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import Button from "primevue/button"
import { computed } from "vue"

const props = defineProps({
	rows: { type: Array, default: () => [] },
	columns: { type: Array, default: () => [] },
	kind: { type: String, default: "cloth" },
	editable: { type: Boolean, default: false },
	busyKey: { type: String, default: "" },
})
const emit = defineEmits(["edit", "delete"])

const materialGroups = computed(() => {
	const grouped = new Map()
	for (const [sourceIndex, row] of props.rows.entries()) {
		const accessory = props.kind === "accessory" ? clean(row.accessory) : ""
		const item = clean(row.item || row.cloth_item || row.cloth_item_variant)
		const clothType = clean(row.cloth_type)
		const key = [accessory, item, clothType].join("\u0000")
		if (!grouped.has(key)) grouped.set(key, { key, accessory, item, clothType, rows: [] })
		grouped.get(key).rows.push({ row, sourceIndex })
	}
	return Array.from(grouped.values())
})

function clean(value) { return String(value || "").trim() }
function variantCount(count) { return `${count} ${count === 1 ? "variant" : "variants"}` }
function formatValue(column, row) {
	const value = row?.[column.field]
	return column.format ? column.format(value, row) : value ?? "—"
}
</script>

<style scoped>
.material-requirement-groups { display: grid; gap: 10px; min-width: 0; }
.material-requirement-group { overflow: hidden; min-width: 0; background: var(--erp-surface); }
.material-requirement-group__header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 14px; padding: 8px 10px 8px 12px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }
.material-requirement-group__identity { display: grid; min-width: 0; gap: 2px; }
.material-requirement-group__identity strong,
.material-requirement-group__identity span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.material-requirement-group__identity strong { color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: 600; line-height: 1.25; }
.material-requirement-group__identity span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 600; }
.material-requirement-group__meta { display: flex; flex: 0 0 auto; align-items: center; justify-content: flex-end; gap: 6px; }
.material-requirement-group__type,
.material-requirement-group__count { display: inline-flex; min-height: 24px; align-items: center; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 500; white-space: nowrap; }
.material-requirement-table-wrap { max-height: none; overflow-x: auto; overflow-y: visible; scrollbar-color: var(--erp-border-strong) transparent; scrollbar-width: thin; }
.material-requirement-table-wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.material-requirement-table { width: 100%; min-width: 660px; border-collapse: collapse; color: var(--erp-text); font-size: var(--erp-font-size-table); font-variant-numeric: tabular-nums; }
.material-requirement-table th,
.material-requirement-table td { padding: 8px 9px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.material-requirement-table th { color: var(--erp-text-secondary); background: var(--erp-surface-muted); font-size: var(--erp-font-size-min); font-weight: 700; white-space: nowrap; }
.material-requirement-table tbody tr:last-child td { border-bottom: 0; }
.material-requirement-table th:last-child,
.material-requirement-table td:last-child { border-right: 0; }
.material-requirement-table__number { text-align: right !important; }
.material-requirement-table .requirement-balance { font-weight: 700; }
.material-requirement-table .requirement-balance--positive { color: var(--erp-success-text); background: var(--erp-success-soft); }
.material-requirement-table .requirement-balance--negative { color: var(--erp-danger); background: var(--erp-danger-soft); }
.material-requirement-table .requirement-balance--zero { color: var(--erp-text-muted); background: var(--erp-surface-soft); }
.material-requirement-table__actions { width: 78px; text-align: right !important; white-space: nowrap; }
.material-requirement-table__actions :deep(.p-button) { width: 1.8rem; height: 1.8rem; }
@media (max-width: 700px) {
	.material-requirement-group__header { align-items: flex-start; flex-direction: column; }
	.material-requirement-group__meta { justify-content: flex-start; }
	.material-requirement-table-wrap { -webkit-mask-image: linear-gradient(to right, var(--erp-text) 0, var(--erp-text) calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, var(--erp-text) 0, var(--erp-text) calc(100% - 18px), transparent 100%); }
	.material-requirement-table__actions :deep(.p-button) { width: 2.25rem; height: 2.25rem; }
}
</style>
