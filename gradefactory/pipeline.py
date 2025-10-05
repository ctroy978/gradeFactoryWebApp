from __future__ import annotations

import io
import uuid
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .grading import run_grading
from .processing import run_processing


@dataclass
class StageResult:
    output_files: List[Path]
    stdout: str
    stderr: str


@dataclass
class PipelineResult:
    processing: Optional[StageResult]
    grading: Optional[StageResult]


@dataclass
class JobPaths:
    job_id: str
    root: Path
    raw_input: Path
    processed: Path
    graded: Path
    rubric: Path
    artifacts: Path


class GradeFactoryPipeline:
    """Convenience wrapper that orchestrates processing and grading runs."""

    def __init__(
        self,
        processed_dir: Optional[Path] = None,
        graded_dir: Optional[Path] = None,
        jobs_root: Optional[Path] = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self.processed_dir = Path(processed_dir) if processed_dir else base_dir / "essays_to_grade"
        self.graded_dir = Path(graded_dir) if graded_dir else base_dir / "graded_essays"
        self.jobs_root = Path(jobs_root) if jobs_root else base_dir / "jobs"

        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.graded_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)

    def create_job_workspace(self, job_id: Optional[str] = None) -> JobPaths:
        job_identifier = job_id or uuid.uuid4().hex
        job_root = self.jobs_root / job_identifier
        raw_dir = job_root / "raw"
        processed_dir = job_root / "processed"
        graded_dir = job_root / "graded"
        rubric_dir = job_root / "rubric"
        artifacts_dir = job_root / "artifacts"

        for path in (job_root, raw_dir, processed_dir, graded_dir, rubric_dir, artifacts_dir):
            path.mkdir(parents=True, exist_ok=True)

        return JobPaths(job_identifier, job_root, raw_dir, processed_dir, graded_dir, rubric_dir, artifacts_dir)

    def run_processing(
        self,
        input_folder: Path,
        *,
        output_folder: Optional[Path] = None,
        name_flag: bool = True,
        xai_api_key: Optional[str] = None,
    ) -> StageResult:
        input_path = Path(input_folder)
        if not input_path.is_dir():
            raise FileNotFoundError(f"Input folder not found: {input_path}")

        destination = Path(output_folder) if output_folder else self.processed_dir
        destination.mkdir(parents=True, exist_ok=True)

        before = {p.name for p in destination.iterdir() if p.is_file()}

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            run_processing(str(input_path), str(destination), name_flag, xai_api_key)

        stdout_value = stdout_buffer.getvalue()
        stderr_value = stderr_buffer.getvalue()

        after = {p.name: p for p in destination.iterdir() if p.is_file()}
        new_files = [after[name] for name in sorted(after.keys()) if name not in before]

        return StageResult(new_files, stdout_value, stderr_value)

    def run_grading(
        self,
        input_folder: Path,
        *,
        output_folder: Optional[Path] = None,
        rubric_path: Path,
        xai_api_key: Optional[str] = None,
    ) -> StageResult:
        input_path = Path(input_folder)
        if not input_path.is_dir():
            raise FileNotFoundError(f"Input folder not found: {input_path}")

        rubric = Path(rubric_path)
        if not rubric.exists():
            raise FileNotFoundError(f"Rubric file not found: {rubric}")

        destination = Path(output_folder) if output_folder else self.graded_dir
        destination.mkdir(parents=True, exist_ok=True)

        before = {p.name for p in destination.iterdir() if p.is_file()}

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            run_grading(str(input_path), str(destination), str(rubric), xai_api_key)

        stdout_value = stdout_buffer.getvalue()
        stderr_value = stderr_buffer.getvalue()

        after = {p.name: p for p in destination.iterdir() if p.is_file()}
        new_files = [after[name] for name in sorted(after.keys()) if name not in before]

        return StageResult(new_files, stdout_value, stderr_value)

    def run_full_pipeline(
        self,
        input_folder: Path,
        *,
        rubric_path: Path,
        name_flag: bool = True,
        xai_api_key: Optional[str] = None,
        processed_output: Optional[Path] = None,
        graded_output: Optional[Path] = None,
    ) -> PipelineResult:
        target_processed = Path(processed_output) if processed_output else self.processed_dir
        target_graded = Path(graded_output) if graded_output else self.graded_dir

        processing_result = self.run_processing(
            input_folder,
            output_folder=target_processed,
            name_flag=name_flag,
            xai_api_key=xai_api_key,
        )

        grading_result = self.run_grading(
            target_processed,
            output_folder=target_graded,
            rubric_path=rubric_path,
            xai_api_key=xai_api_key,
        )

        return PipelineResult(processing_result, grading_result)
