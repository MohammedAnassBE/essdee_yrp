# Copyright (c) 2021, Essdee and contributors
# For license information, please see license.txt

from frappe.contacts.address_and_contact import (
	delete_contact_and_address,
	load_address_and_contact,
)
from frappe.model.document import Document


class SDYRPLocation(Document):
	def onload(self):
		"""Expose this Location's Address and Contact records to the Desk form."""
		load_address_and_contact(self)

	def on_trash(self):
		# The F15 controller passed Supplier here, which could target unrelated
		# links. Location owns only addresses and contacts linked to Location.
		delete_contact_and_address(self.doctype, self.name)


Location = SDYRPLocation
