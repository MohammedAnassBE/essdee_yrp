<template>
	<section
		v-if="showPanel"
		class="lot-section"
	>
		<header>
			<div>
				<span>Production Order on SD YRP Lot</span>
				<h2>Linked Production Order</h2>
			</div>
			<DocumentActionStrip :actions="actions" />
		</header>
		<dl
			v-if="ppo"
			class="merch-ipd-facts lot-section__body"
		>
			<div>
				<dt>Production Order</dt>
				<dd>
					<RouterLink :to="`/merch/production-orders/${encodeURIComponent(ppo.name)}`">
						{{ ppo.name }}
					</RouterLink>
					· <DocumentLink doctype="Item" :name="ppo.item" />
				</dd>
			</div>
			<div>
				<dt>PPO Status</dt>
				<dd>{{ ppo.status || "—" }}</dd>
			</div>
			<div>
				<dt>PPO Delivery Date</dt>
				<dd>{{ formatLotDate(ppo.delivery_date) }}</dd>
			</div>
			<div>
				<dt>PPO Quantity</dt>
				<dd>{{ quantity(ppo.quantity) }}</dd>
			</div>
			<div>
				<dt>This lot</dt>
				<dd>{{ quantity(ppo.lot_quantity) }}</dd>
			</div>
			<div>
				<dt>Other lots</dt>
				<dd>
					<span
						v-for="lot in ppo.other_lots"
						:key="lot.name"
					>
						<RouterLink :to="{ name: MERCH_ROUTES.lot, params: { lotId: lot.name } }">
							{{ lot.name }}
						</RouterLink>
						· {{ quantity(lot.quantity) }}
					</span>
					<span v-if="!ppo.other_lots?.length">—</span>
				</dd>
			</div>
		</dl>
		<p
			v-else
			class="lot-section__body"
		>
			No Production Order linked.
		</p>
	</section>
	<Dialog
		:visible="visible"
		header="Change PPO"
		modal
		:style="{ width: '480px', maxWidth: 'calc(100vw - 24px)' }"
		@update:visible="emit('update:visible', $event)"
	>
		<div class="merch-cloth-field">
			<label for="merch-lot-ppo">Production Order *</label>
			<LinkField
				v-model="selected"
				doctype="YRP Production Order"
				input-id="merch-lot-ppo"
				:filters="{ docstatus: 1, ...(item ? { item } : {}) }"
				:show-open-button="false"
				:disabled="acting"
			/>
			<small>Submitted PPOs for this item only</small>
			<small
				v-if="attempted && !selected"
				class="merch-field-error"
			>
				Production Order is required.
			</small>
		</div>
		<template #footer>
			<Button
				label="Cancel"
				text
				severity="secondary"
				:disabled="acting"
				@click="emit('update:visible', false)"
			/>
			<Button
				label="Link"
				:loading="acting"
				:disabled="acting"
				@click="link"
			/>
		</template>
	</Dialog>
</template>
<script setup>
import Button from "primevue/button"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import Dialog from "primevue/dialog"
import { computed, ref, watch } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import { MERCH_ROUTES } from "../merchViews.js"
import { formatLotDate } from "../../purchase/lot/lotViews.js"
const props = defineProps({
	ppo: { type: Object, default: null },
	item: { type: String, default: "" },
	visible: Boolean,
	showPanel: Boolean,
	acting: Boolean,
	capability: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "link"])
const selected = ref("")
const attempted = ref(false)
const actions = computed(() =>
	props.capability.visible
		? [
				{
					key: "change_ppo",
					label: props.capability.label,
					disabled: props.acting || !props.capability.allowed,
					disabledReason: props.capability.reason,
					command: () => emit("update:visible", true),
				},
			]
		: [],
)
watch(
	() => props.visible,
	() => {
		selected.value = ""
		attempted.value = false
	},
)
function link() {
	attempted.value = true
	if (selected.value) emit("link", { production_order: selected.value })
}
function quantity(value) {
	return value == null ? "—" : Number(value).toLocaleString("en-IN")
}
</script>
