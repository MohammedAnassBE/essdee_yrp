import { useConfirm } from "primevue/useconfirm"

export function useActionConfirmation() {
	const confirmation = useConfirm()

	return ({
		header,
		message,
		acceptLabel,
		rejectLabel = "Keep Document",
		acceptSeverity = "danger",
		acceptIcon = "pi pi-exclamation-triangle",
		accept,
	}) => {
		const acceptProps = { label: acceptLabel, icon: acceptIcon }
		if (acceptSeverity !== "primary") acceptProps.severity = acceptSeverity

		confirmation.require({
			header,
			message,
			icon: "pi pi-exclamation-triangle",
			defaultFocus: "reject",
			acceptProps,
			rejectProps: { label: rejectLabel, severity: "secondary", text: true },
			accept,
		})
	}
}
