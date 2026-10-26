import traceback
from unittest import mock

import frappe
import frappe.realtime
import frappe.utils.background_jobs as background_jobs
from frappe.database.database import IMPLICIT_COMMIT_QUERY_TYPES

from essdee_yrp.migration.cpd_import.importer import TARGET

BLOCKED_QUERY_TYPES = IMPLICIT_COMMIT_QUERY_TYPES | {"commit"}
WATCHED_DOCTYPES = (
	"YRP Stock Ledger Entry",
	"YRP Bin",
	"YRP Repost Item Valuation",
	"Comment",
	"Version",
	"Error Log",
	"Email Queue",
	"Notification Log",
	"Deleted Document",
	"Series",
	"SD YRP Lot",
	"SD YRP Lot Fabric Conversion",
)
REFERENCE_COLUMNS = (
	("reference_doctype", "reference_name"),
	("ref_doctype", "docname"),
	("voucher_type", "voucher_no"),
)
RQ_REGISTRIES = (
	"started_job_registry",
	"finished_job_registry",
	"failed_job_registry",
	"deferred_job_registry",
	"scheduled_job_registry",
)


class DryRunViolation(Exception):
	"""A statement that would end the dry run's transaction."""


class DryRunGuard:
	"""Keep a dry run inside one transaction: no commit, DDL, background job, realtime event or email."""

	def __init__(self):
		self.commits = []
		self.blocked = []
		self.jobs = []
		self.realtime = []
		self.patches = []

	def __enter__(self):
		db = frappe.local.db
		self.mute_emails = frappe.flags.mute_emails
		frappe.flags.mute_emails = True
		self.patches = [
			mock.patch.object(db, "commit", self.skip_commit),
			mock.patch.object(db, "rollback", self.get_guarded_rollback(db.rollback)),
			mock.patch.object(db, "check_implicit_commit", self.block_query),
			mock.patch.object(background_jobs, "enqueue", self.record_job),
			mock.patch.object(frappe, "enqueue", self.record_job),
			mock.patch.object(frappe.realtime, "emit_via_redis", self.record_realtime),
		]
		for patch in self.patches:
			patch.start()
		return self

	def __exit__(self, *exc_info):
		for patch in reversed(self.patches):
			patch.stop()
		frappe.flags.mute_emails = self.mute_emails
		return False

	def skip_commit(self, *args, **kwargs):
		self.commits.append(get_caller())

	def get_guarded_rollback(self, rollback):
		def guarded_rollback(*, save_point=None, chain=False):
			if save_point:
				return rollback(save_point=save_point)
			self.blocked.append(f"full rollback from {get_caller()}")
			raise DryRunViolation("Full rollback inside the dry run")

		return guarded_rollback

	def block_query(self, query, query_type):
		if query_type in BLOCKED_QUERY_TYPES:
			self.blocked.append(f"{query[:120]} from {get_caller()}")
			raise DryRunViolation(f"Dry run blocked a {query_type} statement: {query[:120]}")

	def record_job(self, method, *args, **kwargs):
		name = method if isinstance(method, str) else f"{method.__module__}.{method.__qualname__}"
		self.jobs.append(f"{name} (after_commit={bool(kwargs.get('enqueue_after_commit'))})")

	def record_realtime(self, event, message, room):
		self.realtime.append(f"{event} -> {room}")

	def get_report_lines(self):
		lines = ["## Dry-run guard\n"]
		for title, rows in (
			("Commit calls skipped", self.commits),
			("Blocked statements (would end the transaction)", self.blocked),
			("Background jobs intercepted (not queued)", self.jobs),
			("Realtime events intercepted (not sent)", self.realtime),
		):
			lines.append(f"- {title}: {len(rows)}")
			lines += [f"  - {row} x{rows.count(row)}" for row in sorted(set(rows))]
		return [*lines, ""]


def get_caller():
	"""First app frame outside this package and Frappe's database layer."""
	for frame in reversed(traceback.extract_stack()[:-2]):
		if "/cpd_import/" not in frame.filename and "/frappe/database/" not in frame.filename:
			return f"{frame.filename.split('/apps/')[-1]}:{frame.lineno} {frame.name}"
	return "unknown"


def get_watched_tables():
	tables = []
	for doctype in TARGET.values():
		tables.append(doctype)
		tables += [field.options for field in frappe.get_meta(doctype).get_table_fields()]
	return sorted({*tables, *WATCHED_DOCTYPES})


def get_snapshot():
	"""Row count, max(modified) and CHECKSUM TABLE per watched table, plus RQ job counts."""
	tables = {}
	for doctype in get_watched_tables():
		table = f"`tab{doctype}`"
		has_modified = doctype != "Series"
		count, modified = frappe.db.sql(
			f"select count(*), {'max(modified)' if has_modified else 'null'} from {table}"
		)[0]
		checksum = frappe.db.sql(f"checksum table {table}")[0][1]
		tables[doctype] = [count, str(modified), checksum]
	counts, jobs = get_rq_state()
	return {"at": str(frappe.db.sql("select now(6)")[0][0]), "tables": tables, "rq": counts, "rq_jobs": jobs}


def get_rows_created_since(doctype, since):
	"""Rows another session wrote while the dry run was open, so a changed table can be attributed."""
	if doctype == "Series":
		return []
	columns = [c for c in REFERENCE_COLUMNS if frappe.get_meta(doctype).has_field(c[0])]
	fields = ", ".join(f"`{field}`" for pair in columns[:1] for field in pair)
	rows = frappe.db.sql(
		f"select name, creation, owner{', ' + fields if fields else ''} from `tab{doctype}` where creation >= %s",
		since,
	)
	return [[doctype, *(str(value) for value in row)] for row in rows]


def get_rq_state():
	"""Job counts per queue and registry, plus every job id with its site and method."""
	counts, jobs = {}, {}
	for name in background_jobs.get_queue_list():
		queue = background_jobs.get_queue(name)
		ids = {"queued": queue.get_job_ids()}
		ids |= {key.replace("_job_registry", ""): getattr(queue, key).get_job_ids() for key in RQ_REGISTRIES}
		for key, job_ids in ids.items():
			counts[f"{name} {key}"] = len(job_ids)
			jobs |= {job_id: f"{name} {key}" for job_id in job_ids}
	return counts, jobs


def get_new_jobs(before, after):
	"""Describe RQ jobs that appeared while the dry run was open."""
	from rq.job import Job

	rows = []
	for job_id in sorted(set(after["rq_jobs"]) - set(before["rq_jobs"])):
		try:
			kwargs = Job.fetch(job_id, connection=background_jobs.get_redis_conn()).kwargs
		except Exception:
			kwargs = {}
		rows.append([job_id, after["rq_jobs"][job_id], kwargs.get("site", "?"), kwargs.get("job_name", "?")])
	return rows


def get_snapshot_diff(before, after):
	rows = []
	for section in ("tables", "rq"):
		for key in sorted(set(before[section]) | set(after[section])):
			old, new = before[section].get(key), after[section].get(key)
			rows.append([section, key, old, new, "same" if old == new else "**CHANGED**"])
	return rows
