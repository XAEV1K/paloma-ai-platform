"""Scheduler: the platform's heartbeat.

Registered maintenance jobs (CRM sync, knowledge reindex, daily
analytics) run on their schedules — the piece that makes the runtime
feel *alive* rather than invoked.
"""

from scheduler.scheduler import Job, JobResult, MaintenanceReport, Scheduler

__all__ = ["Job", "JobResult", "MaintenanceReport", "Scheduler"]
