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

    def get_jobs(self) -> list[dict]:
        """등록된 모든 스케줄 작업 목록을 반환합니다."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def get_job(self, job_id: str) -> dict | None:
        """특정 스케줄 작업 정보를 반환합니다."""
        job = self._scheduler.get_job(job_id)
        if not job:
            return None
        return {
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
