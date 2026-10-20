import { createApp } from "vue"
import PrimeVue from "primevue/config"
import AuditPendingDesk from "./AuditPendingDesk.vue"

export class AuditPendingFinishingPlansWrapper {
	constructor(wrapper) {
		this.$wrapper = window.jQuery(wrapper)
		this.app = createApp(AuditPendingDesk).use(PrimeVue, { unstyled: true })
		this.vue = this.app.mount(this.$wrapper.get(0))
	}
}
