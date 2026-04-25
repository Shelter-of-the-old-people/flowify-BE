"""SchedulerService 테스트.

APScheduler 기반 스케줄링 서비스의 CRUD 동작 검증.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.scheduler_service import DEFAULT_JOBSTORE_COLLECTION, SchedulerService


def _build_service():
    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    with (
        patch("app.services.scheduler_service.MongoDBJobStore") as mock_jobstore_cls,
        patch("app.services.scheduler_service.AsyncIOScheduler") as mock_scheduler_cls,
        patch("app.services.scheduler_service.settings") as mock_settings,
    ):
        mock_jobstore = MagicMock()
        mock_jobstore_cls.return_value = mock_jobstore
        mock_scheduler_cls.return_value = mock_scheduler
        mock_settings.MONGODB_URL = "mongodb://localhost:27017"
        mock_settings.MONGODB_DB_NAME = "flowify"

        service = SchedulerService()

    return service, mock_scheduler, mock_jobstore_cls, mock_scheduler_cls


def test_scheduler_initializes_mongodb_jobstore() -> None:
    """기본 scheduler는 MongoDB jobstore를 사용해 초기화됩니다."""
    _, _, mock_jobstore_cls, mock_scheduler_cls = _build_service()

    mock_jobstore_cls.assert_called_once_with(
        host="mongodb://localhost:27017",
        database="flowify",
        collection=DEFAULT_JOBSTORE_COLLECTION,
    )
    mock_scheduler_cls.assert_called_once()
    assert mock_scheduler_cls.call_args.kwargs["jobstores"] == {
        "default": mock_jobstore_cls.return_value
    }


def test_scheduler_start_stop() -> None:
    """running 상태에 따라 start/shutdown을 한 번씩만 호출합니다."""
    service, mock_scheduler, _, _ = _build_service()

    service.start()
    mock_scheduler.start.assert_called_once_with()

    mock_scheduler.running = True
    service.start()
    mock_scheduler.start.assert_called_once_with()

    service.shutdown()
    mock_scheduler.shutdown.assert_called_once_with()


def test_add_cron_job_and_get_job() -> None:
    """cron job 등록과 단건 조회 결과 직렬화를 검증합니다."""
    service, mock_scheduler, _, _ = _build_service()
    next_run = datetime(2026, 4, 25, 9, 0, 0)
    mock_scheduler.get_job.return_value = SimpleNamespace(
        id="job_cron",
        name="job_cron",
        next_run_time=next_run,
        trigger="cron[hour='9', minute='0']",
    )

    def run_job() -> None:
        return None

    service.add_cron_job(
        "job_cron",
        func=run_job,
        hour=9,
        minute=0,
        kwargs={"workflow_id": "wf_1"},
    )
    job = service.get_job("job_cron")

    mock_scheduler.add_job.assert_called_once_with(
        run_job,
        "cron",
        id="job_cron",
        hour=9,
        minute=0,
        kwargs={"workflow_id": "wf_1"},
    )
    assert job == {
        "id": "job_cron",
        "name": "job_cron",
        "next_run": next_run.isoformat(),
        "trigger": "cron[hour='9', minute='0']",
    }


def test_add_interval_job() -> None:
    """interval job 등록 시 APScheduler에 인자를 그대로 전달합니다."""
    service, mock_scheduler, _, _ = _build_service()

    def run_job() -> None:
        return None

    service.add_interval_job(
        "job_interval",
        func=run_job,
        seconds=300,
        kwargs={"workflow_id": "wf_2"},
    )

    mock_scheduler.add_job.assert_called_once_with(
        run_job,
        "interval",
        id="job_interval",
        seconds=300,
        kwargs={"workflow_id": "wf_2"},
    )


def test_remove_job() -> None:
    """job 삭제 요청을 scheduler에 위임합니다."""
    service, mock_scheduler, _, _ = _build_service()

    service.remove_job("job_to_remove")

    mock_scheduler.remove_job.assert_called_once_with("job_to_remove")


def test_get_jobs_returns_list() -> None:
    """등록된 여러 job을 직렬화해 리스트로 반환합니다."""
    service, mock_scheduler, _, _ = _build_service()
    first_run = datetime(2026, 4, 25, 9, 0, 0)
    second_run = datetime(2026, 4, 25, 10, 0, 0)
    mock_scheduler.get_jobs.return_value = [
        SimpleNamespace(
            id="job_1",
            name="job_1",
            next_run_time=first_run,
            trigger="cron[hour='9', minute='0']",
        ),
        SimpleNamespace(
            id="job_2",
            name="job_2",
            next_run_time=second_run,
            trigger="interval[0:05:00]",
        ),
    ]

    jobs = service.get_jobs()

    assert jobs == [
        {
            "id": "job_1",
            "name": "job_1",
            "next_run": first_run.isoformat(),
            "trigger": "cron[hour='9', minute='0']",
        },
        {
            "id": "job_2",
            "name": "job_2",
            "next_run": second_run.isoformat(),
            "trigger": "interval[0:05:00]",
        },
    ]
