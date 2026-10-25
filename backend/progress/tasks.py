from django.tasks import task

from .review import generate_extras


@task(queue_name="practice")
def generate_review_extras(review_id: int) -> str:
    """Runs on the "practice" queue so it never waits behind lesson generation."""
    return generate_extras(review_id).extras
