<template>
	<section v-if="supplier" class="delivery-person-suggestion" aria-labelledby="delivery-person-heading">
		<header>
			<div>
				<span>Delivery contact</span>
				<h3 id="delivery-person-heading">Delivery person</h3>
			</div>
			<Button
				v-if="canCreateDeliveryPerson"
				:label="creating ? 'Close form' : 'Create delivery person'"
				:icon="creating ? 'pi pi-times' : 'pi pi-plus'"
				severity="secondary"
				text
				:disabled="disabled || saving"
				@click="creating = !creating"
			/>
		</header>

		<div class="delivery-person-suggestion__search">
			<i class="pi pi-search" aria-hidden="true" />
			<InputText
				v-model="search"
				placeholder="Search delivery people…"
				aria-label="Search delivery people"
				:disabled="disabled"
				fluid
			/>
		</div>

		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<div v-if="loading" class="delivery-person-suggestion__loading" role="status">
			<i class="pi pi-spin pi-spinner" aria-hidden="true" /> Loading delivery people…
		</div>
		<div v-else-if="suggestions.length" class="delivery-person-suggestion__cards">
			<article v-for="person in suggestions" :key="person.delivery_mob_no">
				<div>
					<strong>{{ person.delivery_person || "Unnamed delivery person" }}</strong>
					<span>{{ person.delivery_mob_no || "No mobile number" }}</span>
				</div>
				<Button
					:label="person.delivery_mob_no === modelValue ? 'Applied' : 'Apply'"
					icon="pi pi-check"
					severity="secondary"
					outlined
					size="small"
					:disabled="disabled || !person.delivery_mob_no || person.delivery_mob_no === modelValue"
					@click="apply(person.delivery_mob_no)"
				/>
			</article>
		</div>
		<div v-else class="delivery-person-suggestion__empty">
			{{ search ? `No delivery people match “${search}”.` : "No recent delivery people were found." }}
		</div>

		<form v-if="canCreateDeliveryPerson && creating" class="delivery-person-suggestion__create" @submit.prevent="createPerson">
			<label for="delivery-person-name"><span>Name</span><InputText id="delivery-person-name" v-model="personName" :disabled="saving" fluid /></label>
			<label for="delivery-person-mobile"><span>Mobile</span><InputText id="delivery-person-mobile" v-model="mobileNumber" inputmode="numeric" :disabled="saving" fluid /></label>
			<Button label="Create and apply" icon="pi pi-check" type="submit" :loading="saving" :disabled="disabled" />
			<small v-if="createError" role="alert">{{ createError }}</small>
		</form>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import { onBeforeUnmount, ref, watch } from "vue"

import { getDeliveryPersonSuggestions } from "../../../api/hr.js"
import { createDoc } from "../../../api/frappe.js"

const props = defineProps({
	modelValue: { type: String, default: "" },
	supplier: { type: String, default: "" },
	canCreateDeliveryPerson: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "apply", "saving-change"])
const search = ref("")
const suggestions = ref([])
const loading = ref(false)
const error = ref("")
const creating = ref(false)
const saving = ref(false)
const personName = ref("")
const mobileNumber = ref("")
const createError = ref("")
let searchTimer = null
let loadSequence = 0

watch(() => props.supplier, (supplier) => {
	search.value = ""
	suggestions.value = []
	error.value = ""
	creating.value = false
	if (supplier) loadSuggestions("")
}, { immediate: true })

watch(search, (value) => {
	if (searchTimer) window.clearTimeout(searchTimer)
	searchTimer = window.setTimeout(() => loadSuggestions(value), 300)
})

async function loadSuggestions(query) {
	if (!props.supplier) return
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	try {
		const rows = await getDeliveryPersonSuggestions(props.supplier, query.trim())
		if (sequence === loadSequence) suggestions.value = Array.isArray(rows) ? rows : []
	} catch (reason) {
		if (sequence === loadSequence) {
			suggestions.value = []
			error.value = reason?.message || "Unable to load delivery people."
		}
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function apply(mobile) {
	emit("update:modelValue", mobile)
	emit("apply", mobile)
}

async function createPerson() {
	createError.value = ""
	if (!personName.value.trim() || !mobileNumber.value.trim()) {
		createError.value = "Enter a name and mobile number."
		return
	}
	saving.value = true
	emit("saving-change", true)
	try {
		const person = await createDoc("YRP Vendor Bill Delivery Person", {
			person_name: personName.value.trim(),
			mobile_no: mobileNumber.value.trim(),
		})
		const mobile = person?.mobile_no || person?.name || mobileNumber.value.trim()
		apply(mobile)
		personName.value = ""
		mobileNumber.value = ""
		creating.value = false
		await loadSuggestions("")
	} catch (reason) {
		createError.value = reason?.message || "Unable to create this delivery person."
	} finally {
		saving.value = false
		emit("saving-change", false)
	}
}

onBeforeUnmount(() => {
	if (searchTimer) window.clearTimeout(searchTimer)
})
</script>

<style scoped>
.delivery-person-suggestion { display: grid; grid-column: 1 / -1; gap: 10px; padding-top: 4px; border-top: 1px solid var(--erp-border); }
.delivery-person-suggestion > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.delivery-person-suggestion > header > div { display: grid; gap: 2px; }
.delivery-person-suggestion > header span { color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .055em; text-transform: uppercase; }
.delivery-person-suggestion h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.delivery-person-suggestion__search { position: relative; display: flex; align-items: center; }
.delivery-person-suggestion__search > i { position: absolute; left: 11px; z-index: 1; color: var(--erp-text-muted); }
.delivery-person-suggestion__search :deep(input) { padding-left: 34px; }
.delivery-person-suggestion__loading, .delivery-person-suggestion__empty { padding: 12px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); text-align: center; border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }
.delivery-person-suggestion__cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.delivery-person-suggestion__cards article { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 10px; padding: 10px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface-soft); }
.delivery-person-suggestion__cards article > div { display: grid; min-width: 0; gap: 2px; }
.delivery-person-suggestion__cards strong, .delivery-person-suggestion__cards span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.delivery-person-suggestion__cards strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.delivery-person-suggestion__cards span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-variant-numeric: tabular-nums; }
.delivery-person-suggestion__create { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)) auto; align-items: end; gap: 10px; padding: 11px; border: 1px solid var(--erp-accent-border); border-radius: var(--erp-control-radius); background: var(--erp-accent-soft); }
.delivery-person-suggestion__create label { display: grid; gap: 5px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.delivery-person-suggestion__create small { grid-column: 1 / -1; color: var(--erp-danger); }
@media (max-width: 700px) { .delivery-person-suggestion__cards, .delivery-person-suggestion__create { grid-template-columns: 1fr; } .delivery-person-suggestion__create small { grid-column: auto; } }
</style>
