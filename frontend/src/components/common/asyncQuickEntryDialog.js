import { defineAsyncComponent } from "vue"

// Lazy: QuickEntryDialog renders FormField, which renders LinkField.
export default defineAsyncComponent(() => import("./QuickEntryDialog.vue"))
