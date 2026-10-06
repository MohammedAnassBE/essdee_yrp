<template>
	<aside class="work-order-activity-rail" aria-label="Work Order activity">
		<section v-for="section in sections" :key="section.key" class="work-order-activity-section">
			<header>
				<div><h2 :title="section.label">{{ section.label }}</h2><span>{{ section.rows.length }}</span></div>
				<div class="activity-actions">
					<Button :aria-label="`Filter ${section.label}`" icon="pi pi-filter" severity="secondary" text rounded size="small" @click="filtersOpen[section.key] = !filtersOpen[section.key]" />
					<Button v-if="section.permissions.can_create" label="New" aria-label="Create New" icon="pi pi-plus" size="small" @click="$emit('create', section.key)" />
				</div>
			</header>
			<div v-if="filtersOpen[section.key]" class="activity-filter">
				<i class="pi pi-search" />
				<input v-model="queries[section.key]" type="search" :aria-label="`Search ${section.label}`" placeholder="Filter by ID, item, lot…" />
			</div>
			<div class="activity-list">
				<button v-for="row in filteredRows(section)" :key="row.name" type="button" class="activity-card" @click="$emit('open', { type: section.key, row })">
					<div class="activity-card__top"><strong>{{ row.name }}</strong><span :class="`activity-status activity-status--${statusTone(row.docstatus)}`">{{ row.status }}</span></div>
					<span v-if="row.item || row.lot" class="activity-card__context">{{ [row.item, row.lot].filter(Boolean).join(" · ") }}</span>
					<div class="activity-card__meta"><span><i class="pi pi-calendar" /> {{ formatDate(row.posting_date) }}</span><span><i class="pi pi-clock" /> {{ formatTime(row.posting_time) }}</span></div>
					<i class="pi pi-chevron-right activity-card__chevron" />
				</button>
				<div v-if="!filteredRows(section).length" class="activity-empty"><i class="pi pi-inbox" /><span>No records</span></div>
			</div>
		</section>
	</aside>
</template>

<script setup>
import Button from "primevue/button"
import { computed, reactive } from "vue"

const props = defineProps({
	deliveryChallans: { type: Array, default: () => [] },
	goodsReceivedNotes: { type: Array, default: () => [] },
	permissions: { type: Object, default: () => ({}) },
})
defineEmits(["create", "open"])

const filtersOpen = reactive({ delivery_challan: false, goods_received_note: false })
const queries = reactive({ delivery_challan: "", goods_received_note: "" })
const sections = computed(() => [
	{ key: "delivery_challan", label: "Delivery Challans", rows: props.deliveryChallans, permissions: props.permissions.delivery_challan || {} },
	{ key: "goods_received_note", label: "Goods Received Notes", rows: props.goodsReceivedNotes, permissions: props.permissions.goods_received_note || {} },
].filter((section) => section.permissions.can_read !== false))

function filteredRows(section) {
	const query = queries[section.key].trim().toLowerCase()
	if (!query) return section.rows
	return section.rows.filter((row) => [row.name, row.item, row.lot, row.status].some((value) => String(value || "").toLowerCase().includes(query)))
}
function formatDate(value) { if (!value) return "—"; const [year, month, day] = String(value).slice(0, 10).split("-"); return day ? `${day}-${month}-${year}` : value }
function formatTime(value) { return value ? String(value).slice(0, 5) : "—" }
function statusTone(docstatus) { return Number(docstatus) === 1 ? "submitted" : Number(docstatus) === 2 ? "cancelled" : "draft" }
</script>

<style scoped>
.work-order-activity-rail { display: grid; grid-template-rows: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); height: 100%; min-height: 0; }
.work-order-activity-section { display: flex; min-height: 0; overflow: hidden; flex-direction: column; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.work-order-activity-section > header { display: flex; min-height: 49px; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 9px 7px 12px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }
.work-order-activity-section > header > div:first-child { display: flex; min-width: 0; align-items: center; gap: 7px; }
.work-order-activity-section h2 { overflow: hidden; margin: 0; font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.work-order-activity-section header span { display: inline-grid; min-width: 21px; height: 21px; padding: 0 6px; place-items: center; color: var(--erp-accent); font-size: var(--erp-font-size-min); font-weight: 800; background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); }
.activity-actions { display: flex; align-items: center; gap: 3px; }
.activity-actions :deep(.p-button) { min-height: 31px; }
.activity-actions :deep(.p-button-label) { font-size: var(--erp-font-size-min); white-space: nowrap; }
.activity-filter { position: relative; display: flex; align-items: center; padding: 7px 9px; border-bottom: 1px solid var(--erp-border); }
.activity-filter i { position: absolute; left: 18px; color: var(--erp-text-muted); font-size: 11px; }
.activity-filter input { width: 100%; min-height: 32px; padding: 0 9px 0 28px; color: var(--erp-text); font: inherit; font-size: var(--erp-font-size-min); background: var(--erp-surface); border: 1px solid var(--erp-border-strong); border-radius: 7px; outline: 0; }
.activity-filter input:focus { border-color: var(--erp-accent); box-shadow: 0 0 0 2px rgb(10 127 90 / 12%); }
.activity-list { flex: 1; min-height: 0; overflow-y: auto; padding: 0; scrollbar-gutter: stable; }
.activity-card { position: relative; display: grid; width: 100%; gap: 5px; margin: 0; padding: 11px 34px 11px 12px; color: inherit; font: inherit; text-align: left; background: var(--erp-surface); border: 0; border-bottom: 1px solid var(--erp-border); border-radius: 0; cursor: pointer; transition: background-color 160ms ease, padding-left 160ms ease; }
.activity-card:last-of-type { border-bottom: 0; }
.activity-card:hover { padding-left: 15px; background: color-mix(in srgb, var(--erp-accent-soft) 42%, white); }
.activity-card:focus-visible { outline: 2px solid color-mix(in srgb, var(--erp-accent) 72%, white); outline-offset: -2px; }
.activity-card__top { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 8px; }
.activity-card__top strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.activity-status { padding: 2px 6px; color: #5f6e66; font-size: var(--erp-font-size-min); font-weight: 800; text-transform: uppercase; background: #eef2f0; border-radius: var(--erp-pill-radius); }
.activity-status--submitted { color: #087744; background: #e1f6eb; }
.activity-status--cancelled { color: #b42318; background: #fde8e8; }
.activity-card__context { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); text-overflow: ellipsis; white-space: nowrap; }
.activity-card__meta { display: flex; align-items: center; gap: 10px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.activity-card__meta span { display: inline-flex; align-items: center; gap: 4px; }
.activity-card__meta i { font-size: 10px; }
.activity-card__chevron { position: absolute; top: 50%; right: 10px; color: #84978e; font-size: 11px; transform: translateY(-50%); }
.activity-empty { display: grid; min-height: 100px; place-items: center; align-content: center; gap: 6px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
@media (max-width: 1024px) { .work-order-activity-rail { grid-template-rows: minmax(280px, 1fr); grid-template-columns: repeat(2, minmax(0, 1fr)); height: 360px; } }
@media (max-width: 620px) { .work-order-activity-rail { grid-template-rows: repeat(2, minmax(260px, 1fr)); grid-template-columns: 1fr; height: 600px; } .activity-actions :deep(.p-button-label) { display: none; } }
</style>
