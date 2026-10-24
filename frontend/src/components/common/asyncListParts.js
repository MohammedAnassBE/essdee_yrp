import { defineAsyncComponent } from "vue"

// Lazy: dialogs and date editors a list page renders only on demand (DatePicker, MultiSelect, FormField editors).
export const loadFormField = () => import("./FormField.vue")
export const FormField = defineAsyncComponent(loadFormField)
export const ListviewFilters = defineAsyncComponent(() => import("./ListviewFilters.vue"))
export const UserListviewColumns = defineAsyncComponent(() => import("./UserListviewColumns.vue"))
export const DateField = defineAsyncComponent(() => import("./DateField.vue"))
export const DateRangeFilter = defineAsyncComponent(() => import("./DateRangeFilter.vue"))
export const DateTimeField = defineAsyncComponent(() => import("./DateTimeField.vue"))
export const TimeField = defineAsyncComponent(() => import("./TimeField.vue"))
