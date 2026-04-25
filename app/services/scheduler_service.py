from collections.abc import Callable
from typing import Any

from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

DEFAULT_JOBSTORE_COLLECTION = "scheduler_jobs"


class SchedulerService:
    """APScheduler 기반 스케줄링 서비스"""

    def __init__(self):
        self._scheduler = AsyncIOScheduler(jobstores=self._build_jobstores())

    @staticmethod
    def _build_jobstores() -> dict[str, MongoDBJobStore]:
        """MongoDB 기반 기본 jobstore를 구성합니다."""
        return {
            "default": MongoDBJobStore(
                host=settings.MONGODB_URL,
                database=settings.MONGODB_DB_NAME,
                collection=DEFAULT_JOBSTORE_COLLECTION,
            )
        }

    @staticmethod
    def _serialize_job(job: Any) -> dict[str, str | None]:
        """APScheduler Job 객체를 API 응답용 dict로 변환합니다."""
        return {
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }

    def start(self) -> None:
        """스케줄러가 아직 중지 상태일 때만 시작합니다."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        """스케줄러가 실행 중일 때만 종료합니다."""
        if self._scheduler.running:
            self._scheduler.shutdown()

    def add_cron_job(
        self,
        job_id: str,
        func: Callable[..., object],
        hour: int,
        minute: int = 0,
        **kwargs,
    ) -> None:
        """크론 기반 스케줄 작업 등록"""
        self._scheduler.add_job(func, "cron", id=job_id, hour=hour, minute=minute, **kwargs)

    def add_interval_job(
        self, job_id: str, func: Callable[..., object], seconds: int, **kwargs
    ) -> None:
        """인터벌 기반 스케줄 작업 등록"""
        self._scheduler.add_job(func, "interval", id=job_id, seconds=seconds, **kwargs)

    def remove_job(self, job_id: str) -> None:
        """지정한 ID의 스케줄 작업을 삭제합니다."""
        self._scheduler.remove_job(job_id)

    def get_jobs(self) -> list[dict[str, str | None]]:
        """등록된 모든 스케줄 작업 목록을 반환합니다."""
        return [self._serialize_job(job) for job in self._scheduler.get_jobs()]

    def get_job(self, job_id: str) -> dict[str, str | None] | None:
        """특정 스케줄 작업 정보를 반환합니다."""
        job = self._scheduler.get_job(job_id)
        if not job:
            return None
        return self._serialize_job(job)
