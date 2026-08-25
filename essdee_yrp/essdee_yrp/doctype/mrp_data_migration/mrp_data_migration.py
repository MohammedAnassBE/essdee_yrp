# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from essdee_yrp.migration.config import get_migration_settings


RUNNING_STATUSES = {"Analysing", "Queued", "Running"}


ADAPTER_STATUS = "Configured Local-Bench Source"


class MRPDataMigration(Document):
	def before_insert(self):
		# All audit fields are server-owned, even when a document is created by
		# REST rather than Desk.
		self.status = "Draft"
		self.last_action = None
		self.last_started_on = None
		self.last_completed_on = None
		self.analysed_on = None
		self.analysed_by = None
		self.source_doctype_count = 0
		self.target_doctype_count = 0
		self.identity_count = 0
		self.mapped_count = 0
		self.custom_count = 0
		self.blocker_count = 0
		self.total_source_records = 0
		self.processed_records = 0
		self.skipped_records = 0
		self.failed_records = 0
		self.report_json = None
		self.checkpoint_json = None
		self.error_log = None
		self.set("migration_details", [])

	def validate(self):
		# These are code-owned endpoints. A crafted request must not turn the
		# schema analyser into an arbitrary filesystem/site connection surface.
		settings = get_migration_settings()
		self.source_site = settings.source_site
		self.source_app = settings.source_app
		self.target_site = settings.target_site
		self.target_apps = ", ".join(settings.target_apps)
		self.adapter_status = ADAPTER_STATUS
		if not self.is_new() and not self.flags.in_migration_action:
			frappe.throw(
				_("MRP Data Migration is an audit record. Update it only through its migration actions."),
				title=_("Direct Update Blocked"),
			)

	@frappe.whitelist()
	def analyse(self):
		self._check_action_access()
		if self.is_new():
			frappe.throw(_("Save this migration run before analysing the schemas."))

		started_on = now_datetime()
		self.flags.in_migration_action = True
		self.status = "Analysing"
		self.last_action = "Analyse"
		self.last_started_on = started_on
		self.last_completed_on = None

		try:
			from essdee_yrp.migration.live import (
				F15SourceBridge,
				build_live_schema_analysis,
			)

			settings = get_migration_settings()
			source = F15SourceBridge(settings)
			_plan, payload = build_live_schema_analysis(settings, source)
			self._apply_analysis(payload)
		except Exception:
			self.status = "Failed"
			self.failed_records = 0
			self.last_completed_on = now_datetime()
			self.error_log = frappe.get_traceback()
			self.save()
			raise

		self.last_completed_on = now_datetime()
		self.save()
		return {
			"status": self.status,
			"source_doctypes": self.source_doctype_count,
			"target_doctypes": self.target_doctype_count,
			"blockers": self.blocker_count,
			"reads_site_data": True,
			"writes_site_data": False,
		}

	@frappe.whitelist()
	def dry_run(self):
		return self._enqueue("dry_run", allowed_statuses={"Ready", "Dry Run Complete", "Failed"})

	@frappe.whitelist()
	def migrate(self):
		return self._enqueue("migrate", allowed_statuses={"Dry Run Complete", "Failed"})

	@frappe.whitelist()
	def verify(self):
		return self._enqueue("verify", allowed_statuses={"Completed", "Verified"})

	def _apply_analysis(self, payload):
		kinds = payload["migration_kinds"]
		self.source_doctype_count = payload["source_doctypes"]
		self.target_doctype_count = payload["target_doctypes"]
		self.identity_count = kinds.get("identity", 0)
		self.mapped_count = kinds.get("mapped", 0)
		self.custom_count = kinds.get("custom", 0)
		self.blocker_count = payload["issue_count"]
		self.status = "Ready" if payload["ready"] else "Blocked"
		self.analysed_on = now_datetime()
		self.analysed_by = frappe.session.user
		self.report_json = json.dumps(payload, indent=2, sort_keys=True)
		self.error_log = "\n".join(payload["issues"])
		self.set("migration_details", [])
		for detail in payload["doctype_details"]:
			self.append(
				"migration_details",
				{
					"source_doctype": detail["source_doctype"],
					"target_doctype": detail["target_doctype"],
					"migration_kind": detail["migration_kind"],
					"dependency_group": detail["dependency_group"],
					"is_child": detail["is_child"],
					"status": detail["status"],
					"issue_count": len(detail["issues"]),
					"issue_summary": "\n".join(detail["issues"]),
					"mapping_json": json.dumps(
						{
							"dependencies": detail["dependencies"],
							"field_map": detail["field_map"],
							"table_option_map": detail["table_option_map"],
							"ignored_fields": detail["ignored_fields"],
							"custom_transformer": detail["custom_transformer"],
							"post_transformer": detail["post_transformer"],
							"value_transformers": detail["value_transformers"],
						},
						sort_keys=True,
					),
				},
			)

	def _enqueue(self, mode, *, allowed_statuses):
		self._check_action_access()
		if self.status in RUNNING_STATUSES:
			frappe.throw(_("A migration action is already running."))
		if self.status not in allowed_statuses:
			frappe.throw(
				_("{0} cannot run while the migration status is {1}.").format(
					mode.replace("_", " ").title(), self.status
				),
				title=_("Migration Action Not Ready"),
			)
		if self.blocker_count:
			frappe.throw(_("Resolve every schema blocker before running the migration."))
		if mode == "migrate" and self.status == "Failed" and self.last_action != "Migrate":
			frappe.throw(
				_("Run and complete the Dry Run before starting the write migration."),
				title=_("Dry Run Required"),
			)

		from essdee_yrp.migration.live import enqueue_job

		job = enqueue_job(self.name, mode)
		frappe.db.set_value(
			self.doctype,
			self.name,
			{"status": "Queued", "error_log": None},
			update_modified=False,
		)
		return {"status": "Queued", "job_id": job.id}

	def _check_action_access(self):
		frappe.only_for("System Manager")
		self.check_permission("write")
