from django.tasks import task

from .services import run_job


@task
def run_generation_job(job_id: int) -> str:
    """Background worker entry point (django-tasks-db `db_worker`)."""
    return run_job(job_id).status
