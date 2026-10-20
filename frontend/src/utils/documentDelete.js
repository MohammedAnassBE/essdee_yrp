export function canDeleteDocument({ name, docstatus, permissions }) {
	return Boolean(name && permissions?.delete && Number(docstatus) !== 1)
}

export function getDeleteRedirectTarget(redirectTo, backTo) {
	return redirectTo || backTo || "/"
}

export function documentDeletedToast(doctype, name, label = "") {
	return { severity: "success", summary: `${label || doctype} ${name} deleted`, life: 3500 }
}
