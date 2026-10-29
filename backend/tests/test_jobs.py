"""
Tests for job state machine using an in-memory SQLite database.
"""
import json
import pytest
from sqlmodel import SQLModel, Session, create_engine

from app.jobs.models import Job


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    yield eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def test_create_job(session):
    job = Job(pipeline_id="test_pipe", task="image_to_image", params_json='{"prompt":"test"}')
    session.add(job)
    session.commit()
    session.refresh(job)
    assert job.id
    assert job.status == "queued"
    assert job.progress == 0
    assert job.attempts == 0


def test_job_params_json(session):
    params = {"prompt": "hello", "seed": 42, "steps": 20}
    job = Job(pipeline_id="p", task="t", params_json=json.dumps(params))
    session.add(job)
    session.commit()
    session.refresh(job)
    loaded = json.loads(job.params_json)
    assert loaded["prompt"] == "hello"
    assert loaded["seed"] == 42


def test_job_status_transitions(session):
    job = Job(pipeline_id="p", task="t")
    session.add(job)
    session.commit()
    session.refresh(job)

    # Simulate transitions
    for status in ("preparing", "running", "postprocessing", "done"):
        job.status = status
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.status == status


def test_job_failure(session):
    job = Job(pipeline_id="p", task="t")
    session.add(job)
    session.commit()

    job.status = "failed"
    job.error = "CUDA out of memory"
    session.add(job)
    session.commit()
    session.refresh(job)

    assert job.status == "failed"
    assert "memory" in job.error.lower()
