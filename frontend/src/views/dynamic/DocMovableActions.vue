<!--
  DocMovableActions — the MOVABLE document-action affordances of DocDetail,
  extracted ONCE and re-hosted by the `actions` placement knob (spec §6.4;
  server vocab yrp/api/ui_config.py ACTIONS_*):

    placement "header"   → inside .head-actions, exactly where they render today
    placement "inline"   → a strip at the bottom of the main detail column
    placement "floating" → a FAB cluster pinned bottom-right (viewport on the
                           full page; inside the panel when embedded)

  Movable set (registry name → affordance):
    create_dc / create_grn → the primary forward CTA (Create DC / Create GRN)
    more_menu              → the "More" overflow toggle
    ewaybill_menu          → the e-Waybill menu toggle
    send_sms               → Send SMS
    send_whatsapp          → Send WhatsApp
    cancel_doc             → Cancel

  PARITY LAW: this file is a byte-for-byte extraction of the header buttons —
  same PrimeVue Buttons, same labels/icons/severities/aria wiring. ALL gating
  (docstatus, isDeliveryChallan, canCreate/canCancel, WhatsApp map,
  doc.supplier) stays in DocDetail's computeds and arrives as the show* props;
  every click relays to DocDetail's EXISTING handlers/menus/modals (mounted
  once there) — zero logic lives here. Core lifecycle (Edit/Save/Submit/
  Delete/Amend/Workflow) is NOT part of this component and never moves.

  Multi-root fragment on purpose: in the header the buttons must stay direct
  flex children of .head-actions (gap layout + pixel parity).
-->
<template>
	<!-- Primary forward CTA (Create DC / Create GRN) — Q11 tooltip wrapper. -->
	<span
		v-if="primaryForward"
		v-tooltip.bottom="primaryForward.tooltip"
		class="cta-wrap"
	>
		<Button
			:label="primaryForward.label"
			:icon="primaryForward.icon"
			size="small"
			class="forward-cta"
			:disabled="primaryForward.disabled"
			:loading="primaryForward.loadingKey && acting === primaryForward.loadingKey"
			@click="primaryForward.handler"
		/>
	</span>

	<!-- Overflow: secondary create-next actions + Print + Open in Desk. -->
	<Button
		v-if="showMore"
		type="button"
		label="More"
		icon="pi pi-ellipsis-h"
		iconPos="right"
		size="small"
		severity="secondary"
		outlined
		aria-haspopup="true"
		aria-controls="dd_more_menu"
		@click="(e) => emit('toggle-more', e)"
	/>

	<!-- Delivery Challan e-Waybill lifecycle menu toggle. -->
	<Button
		v-if="showEwb"
		type="button"
		label="e-Waybill"
		icon="pi pi-truck"
		size="small"
		severity="secondary"
		outlined
		aria-haspopup="true"
		aria-controls="dd_ewb_menu"
		@click="(e) => emit('toggle-ewb', e)"
	/>

	<Button
		v-if="showSms"
		label="Send SMS"
		icon="pi pi-comment"
		size="small"
		severity="secondary"
		outlined
		@click="emit('open-sms')"
	/>

	<Button
		v-if="showWhatsApp"
		label="Send WhatsApp"
		icon="pi pi-whatsapp"
		size="small"
		severity="secondary"
		outlined
		@click="emit('open-whatsapp')"
	/>

	<!-- Destructive, set apart from the forward CTA. -->
	<Button
		v-if="showCancel"
		label="Cancel"
		icon="pi pi-ban"
		size="small"
		severity="danger"
		outlined
		:loading="acting === 'cancel'"
		@click="emit('cancel')"
	/>
</template>

<script setup>
import Button from "primevue/button"
import Tooltip from "primevue/tooltip"

const vTooltip = Tooltip

defineProps({
	// The FIRST allowed forward action ({label, icon, handler, disabled,
	// tooltip, loadingKey}) or null — DocDetail's primaryForward, untouched.
	primaryForward: { type: Object, default: null },
	// DocDetail's in-flight action key ("cancel", "wo-dc", …) or null.
	acting: { type: String, default: null },
	// Per-affordance visibility — DocDetail's EXACT former v-if conditions
	// (AND the actions.items filter), computed there, consumed here.
	showMore: { type: Boolean, default: false },
	showEwb: { type: Boolean, default: false },
	showSms: { type: Boolean, default: false },
	showWhatsApp: { type: Boolean, default: false },
	showCancel: { type: Boolean, default: false },
})

// Menu toggles relay the ORIGINAL click event — PrimeVue popup Menus anchor
// to event.currentTarget, so the menu opens on whichever placement hosts the
// button (emits are synchronous; currentTarget is still live).
const emit = defineEmits(["toggle-more", "toggle-ewb", "open-sms", "open-whatsapp", "cancel"])
</script>

<style scoped>
/* Byte-for-byte copies of DocDetail's scoped rules for these two hooks —
   scoped styles don't cross the component boundary, and the primary CTA must
   keep its subtle lift in the header default (parity). */
.cta-wrap {
	display: inline-flex;
}
.forward-cta {
	box-shadow: 0 1px 2px var(--esd-shadow);
}
</style>
