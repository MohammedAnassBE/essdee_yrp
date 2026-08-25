# Copyright (c) 2026, Essdee and contributors

from __future__ import annotations

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.translate import print_language
from frappe.utils import add_days, get_datetime, get_url, now


class ShortenedLink(Document):
	def validate(self):
		if self.type == "Print PDF":
			if not self.document_type or not self.document_linked:
				frappe.throw(_("Document Type and Document are required for a PDF link."))
			target = frappe.get_doc(self.document_type, self.document_linked)
			if self.is_new():
				target.check_permission("read")
		elif self.type == "Link":
			_validate_redirect_url(self.link)
		else:
			frappe.throw(_("Unsupported shortened-link type."))

	def is_expired(self):
		return bool(self.link_expiry and get_datetime() >= get_datetime(self.link_expiry))

	def redirect(self):
		if self.is_expired():
			frappe.respond_as_web_page(
				_("Link Expired"),
				_("The resource you are looking for is no longer available."),
				http_status_code=410,
				indicator_color="red",
			)
			return
		if self.type == "Print PDF":
			self.download_document_pdf()
		else:
			self.redirect_link()

	def download_document_pdf(self):
		from frappe.utils.pdf import get_pdf

		html = render_document_print(self.document_type, self.document_linked)
		frappe.local.response.filename = "{0}.pdf".format(
			self.document_linked.replace(" ", "-").replace("/", "-")
		)
		frappe.local.response.filecontent = get_pdf(html)
		frappe.local.response.type = "pdf"

	def redirect_link(self):
		_validate_redirect_url(self.link)
		frappe.local.response.type = "redirect"
		frappe.local.response.location = self.link


def _validate_redirect_url(url):
	parsed = urlparse((url or "").strip())
	if parsed.scheme not in {"http", "https"} or not parsed.netloc:
		frappe.throw(_("Link must be an absolute HTTP or HTTPS URL."))


def render_document_print(doctype, docname, print_format=None):
	"""Render a configured print target without the legacy localhost API/token hop."""
	doc = frappe.get_doc(doctype, docname)
	default_letterhead = frappe.db.get_value(
		"Letter Head", {"disabled": 0, "is_default": 1}, "name"
	)
	with print_language(None):
		html = frappe.get_print(
			doctype,
			docname,
			print_format,
			doc=doc,
			letterhead=default_letterhead,
			no_letterhead=0,
		)
	return html.decode("utf-8") if isinstance(html, bytes) else html


@frappe.whitelist()
def get_print_pdf(doctype, docname, print_format=None):
	"""Authenticated preview helper; unlike F15 it cannot bypass DocType permission."""
	frappe.get_doc(doctype, docname).check_permission("print")
	return render_document_print(doctype, docname, print_format)


def create_print_sl(doctype, docname):
	target = frappe.get_doc(doctype, docname)
	target.check_permission("read")
	expires_in = frappe.db.get_single_value("MRP Settings", "link_expiry_days") or 14
	doc = frappe.get_doc(
		{
			"doctype": "Shortened Link",
			"type": "Print PDF",
			"document_type": doctype,
			"document_linked": docname,
			"link_expiry": add_days(now(), expires_in),
		}
	)
	doc.insert()
	return doc.name


def get_short_link(doctype, docname):
	if not doctype or not docname:
		return None
	name = create_print_sl(doctype, docname)
	domain = (frappe.db.get_single_value("MRP Settings", "shortned_url_domain") or "").strip()
	if domain:
		return f"{domain.rstrip('/')}/{name}"
	return get_url(
		"/api/method/essdee_yrp.essdee_yrp.doctype.shortened_link.shortened_link.parse_short_link"
		f"?token={name}"
	)


@frappe.whitelist(allow_guest=True)
def parse_short_link(token=None, hash=None):
	"""Resolve an unguessable public token and perform its configured action."""
	name = token or hash
	if not name or not frappe.db.exists("Shortened Link", name):
		raise frappe.DoesNotExistError(_("Invalid shortened link."))
	doc = frappe.get_doc("Shortened Link", name)
	if doc.is_expired():
		doc.redirect()
		return
	frappe.db.sql(
		"UPDATE `tabShortened Link` SET link_views=COALESCE(link_views, 0) + 1 WHERE name=%s",
		name,
	)
	doc.redirect()
