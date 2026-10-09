import { onBeforeUnmount, ref } from "vue"

export function dateRangeError(fromDate, toDate, missing = "Please select From Date and To Date") {
	if (!fromDate || !toDate) return missing
	if (fromDate > toDate) return "From Date cannot be after To Date"
	return ""
}

export function useReportRequest() {
	const loading = ref(false)
	const generated = ref(false)
	const error = ref("")
	let sequence = 0

	async function run(validationMessage, request, onSuccess) {
		if (validationMessage) {
			error.value = validationMessage
			return
		}
		const current = ++sequence
		loading.value = true
		error.value = ""
		try {
			const data = await request()
			if (current !== sequence) return
			onSuccess(data)
			generated.value = true
		} catch (reason) {
			if (current === sequence) error.value = reason?.message || "Unable to generate this report."
		} finally {
			if (current === sequence) loading.value = false
		}
	}

	function clear() {
		sequence += 1
		loading.value = false
		generated.value = false
		error.value = ""
	}

	onBeforeUnmount(() => { sequence += 1 })
	return { loading, generated, error, run, clear }
}
