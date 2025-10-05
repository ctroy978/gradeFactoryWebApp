from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Sequence, Tuple

from .pipeline import GradeFactoryPipeline, JobPaths, StageResult
from .utils import load_api_keys


JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


@dataclass
class StageSnapshot:
    name: str
    status: str = JOB_STATUS_PENDING
    stdout: str = ""
    stderr: str = ""
    output_files: List[str] = field(default_factory=list)


@dataclass
class JobRecord:
    job_id: str
    job_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    paths: JobPaths
    stages: Dict[str, StageSnapshot]
    error: Optional[str] = None


class JobManager:
    """Coordinates background execution of GradeFactory pipeline jobs."""

    def __init__(self, pipeline: Optional[GradeFactoryPipeline] = None, max_workers: int = 2) -> None:
        self.pipeline = pipeline or GradeFactoryPipeline()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.jobs: Dict[str, JobRecord] = {}
        self._lock = Lock()
        self._api_key = load_api_keys()

    def shutdown(self, wait: bool = False) -> None:
        self.executor.shutdown(wait=wait)


    def create_job(self, job_type: str) -> JobRecord:
        paths = self.pipeline.create_job_workspace()
        now = datetime.now(timezone.utc)
        stages = self._initial_stages(job_type)
        record = JobRecord(
            job_id=paths.job_id,
            job_type=job_type,
            status=JOB_STATUS_PENDING,
            created_at=now,
            updated_at=now,
            paths=paths,
            stages=stages,
        )
        with self._lock:
            self.jobs[record.job_id] = record
        return record

    def list_jobs(self) -> List[JobRecord]:
        with self._lock:
            return list(self.jobs.values())

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self.jobs.get(job_id)

    def snapshot(self, job_id: str) -> Optional[Dict[str, object]]:
        record = self.get_job(job_id)
        if not record:
            return None
        return self._serialize_job(record)

    def write_files(self, job: JobRecord, files: Sequence[Tuple[str, bytes]], destination: Path) -> List[str]:
        destination.mkdir(parents=True, exist_ok=True)
        stored: List[str] = []
        for index, (filename, data) in enumerate(files, start=1):
            safe_name = Path(filename or f"upload_{index}.pdf").name
            target = destination / safe_name
            target.write_bytes(data)
            stored.append(str(target.relative_to(job.paths.root)))
        return stored

    def write_rubric(self, job: JobRecord, filename: str, data: bytes) -> Path:
        job.paths.rubric.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename or "rubric").name
        target = job.paths.rubric / safe_name
        target.write_bytes(data)
        return target

    def start_processing_job(self, job_id: str, *, name_flag: bool = True) -> None:
        self._submit(self._run_processing_job, job_id, name_flag)

    def start_grading_job(self, job_id: str, rubric_path: Path) -> None:
        self._submit(self._run_grading_job, job_id, rubric_path)

    def start_full_pipeline(self, job_id: str, rubric_path: Path, *, name_flag: bool = True) -> None:
        self._submit(self._run_full_pipeline, job_id, rubric_path, name_flag)

    def _submit(self, fn, job_id: str, *args) -> None:
        self.executor.submit(fn, job_id, *args)

    def _run_processing_job(self, job_id: str, name_flag: bool) -> None:
        self._mark_job_running(job_id)
        self._mark_stage_status(job_id, "processing", JOB_STATUS_RUNNING)
        try:
            record = self.get_job(job_id)
            if not record:
                raise ValueError(f"Job {job_id} not found")
            result = self.pipeline.run_processing(
                record.paths.raw_input,
                output_folder=record.paths.processed,
                name_flag=name_flag,
                xai_api_key=self._api_key,
            )
            self._complete_stage(job_id, "processing", result)
            self._mark_job_completed(job_id)
        except Exception as exc:
            self._fail_stage(job_id, "processing", exc)

    def _run_grading_job(self, job_id: str, rubric_path: Path) -> None:
        self._mark_job_running(job_id)
        self._mark_stage_status(job_id, "grading", JOB_STATUS_RUNNING)
        try:
            record = self.get_job(job_id)
            if not record:
                raise ValueError(f"Job {job_id} not found")
            result = self.pipeline.run_grading(
                record.paths.processed,
                output_folder=record.paths.graded,
                rubric_path=rubric_path,
                xai_api_key=self._api_key,
            )
            self._complete_stage(job_id, "grading", result)
            self._mark_job_completed(job_id)
        except Exception as exc:
            self._fail_stage(job_id, "grading", exc)

    def _run_full_pipeline(self, job_id: str, rubric_path: Path, name_flag: bool) -> None:
        self._mark_job_running(job_id)
        self._mark_stage_status(job_id, "processing", JOB_STATUS_RUNNING)
        try:
            record = self.get_job(job_id)
            if not record:
                raise ValueError(f"Job {job_id} not found")
            processing = self.pipeline.run_processing(
                record.paths.raw_input,
                output_folder=record.paths.processed,
                name_flag=name_flag,
                xai_api_key=self._api_key,
            )
            self._complete_stage(job_id, "processing", processing)
        except Exception as exc:
            self._fail_stage(job_id, "processing", exc)
            return

        self._mark_stage_status(job_id, "grading", JOB_STATUS_RUNNING)
        try:
            grading = self.pipeline.run_grading(
                record.paths.processed,
                output_folder=record.paths.graded,
                rubric_path=rubric_path,
                xai_api_key=self._api_key,
            )
            self._complete_stage(job_id, "grading", grading)
            self._mark_job_completed(job_id)
        except Exception as exc:
            self._fail_stage(job_id, "grading", exc)

    def _initial_stages(self, job_type: str) -> Dict[str, StageSnapshot]:
        stages: Dict[str, StageSnapshot] = {}
        if job_type in {"process", "full"}:
            stages["processing"] = StageSnapshot("processing")
        if job_type in {"grade", "full"}:
            stages["grading"] = StageSnapshot("grading")
        return stages

    def _mark_job_running(self, job_id: str) -> None:
        with self._lock:
            record = self.jobs.get(job_id)
            if not record:
                return
            if record.status == JOB_STATUS_PENDING:
                record.status = JOB_STATUS_RUNNING
            record.updated_at = datetime.now(timezone.utc)

    def _mark_job_completed(self, job_id: str) -> None:
        with self._lock:
            record = self.jobs.get(job_id)
            if not record:
                return
            if all(stage.status == JOB_STATUS_COMPLETED for stage in record.stages.values()):
                record.status = JOB_STATUS_COMPLETED
                record.updated_at = datetime.now(timezone.utc)

    def _mark_stage_status(self, job_id: str, stage_name: str, status: str) -> None:
        with self._lock:
            record = self.jobs.get(job_id)
            if not record:
                return
            stage = record.stages.get(stage_name)
            if not stage:
                return
            stage.status = status
            record.updated_at = datetime.now(timezone.utc)

    def _complete_stage(self, job_id: str, stage_name: str, result: StageResult) -> None:
        with self._lock:
            record = self.jobs.get(job_id)
            if not record:
                return
            stage = record.stages.get(stage_name)
            if not stage:
                return
            stage.status = JOB_STATUS_COMPLETED
            stage.stdout = result.stdout
            stage.stderr = result.stderr
            stage.output_files = [
                self._relative_output(record.paths.root, Path(path)) for path in result.output_files
            ]
            record.updated_at = datetime.now(timezone.utc)

    def _fail_stage(self, job_id: str, stage_name: str, exc: Exception) -> None:
        message = str(exc)
        with self._lock:
            record = self.jobs.get(job_id)
            if not record:
                return
            record.status = JOB_STATUS_FAILED
            record.error = message
            record.updated_at = datetime.now(timezone.utc)
            stage = record.stages.get(stage_name)
            if stage:
                stage.status = JOB_STATUS_FAILED
                if stage.stderr:
                    stage.stderr += f"
{message}"
                else:
                    stage.stderr = message

    def _relative_output(self, job_root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(job_root))
        except ValueError:
            return str(path)

    def _serialize_job(self, record: JobRecord) -> Dict[str, object]:
        return {
            "id": record.job_id,
            "type": record.job_type,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "error": record.error,
            "stages": [
                {
                    "name": stage.name,
                    "status": stage.status,
                    "stdout": stage.stdout,
                    "stderr": stage.stderr,
                    "output_files": stage.output_files,
                }
                for stage in record.stages.values()
            ],
            "paths": {
                "raw_input": str(record.paths.raw_input),
                "processed": str(record.paths.processed),
                "graded": str(record.paths.graded),
                "rubric": str(record.paths.rubric),
            },
        }
