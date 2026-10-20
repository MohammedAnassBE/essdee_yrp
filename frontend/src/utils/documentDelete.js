export function canDeleteDocument({ name, docstatus, permissions }) {
	return Boolean(name && permissions?.delete && Number(docstatus) !== 1)
}

export function getDeleteRedirectTarget(redirectTo, backTo) {
	return redirectTo || backTo || "/"
}
