from apscheduler.schedulers.asyncio import AsyncIOScheduler


class SchedulerService:
    """APScheduler 기반 스케줄링 서비스"""

    def __init__(self):
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown()

    def add_cron_job(self, job_id: str, func, hour: int, minute: int = 0, **kwargs) -> None:
        """크론 기반 스케줄 작업 등록"""
        self._scheduler.add_job(func, "cron", id=job_id, hour=hour, minute=minute, **kwargs)

    def add_interval_job(self, job_id: str, func, seconds: int, **kwargs) -> None:
        """인터벌 기반 스케줄 작업 등록"""
        self._scheduler.add_job(func, "interval", id=job_id, seconds=seconds, **kwargs)

    def remove_job(self, job_id: str) -> None:
        self._scheduler.remove_job(job_id)
