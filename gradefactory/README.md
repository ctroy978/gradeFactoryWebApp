### Examples

- **Run the full pipeline (process and grade):**

  Place your raw multi-page PDF(s) in a folder (e.g., `my_raw_essays`).

  ```bash
  python -m gradefactory --full-pipeline --input-folder my_raw_essays --rubric path/to/my_rubric.json
  ```

- **Run only the processing step:**

  ```bash
  python -m gradefactory --process --input-folder my_raw_essays --name
  ```

  _(The `--name` flag will attempt to name the output files based on the student's name.)_

- **Run only the grading step (assuming you have already processed the essays):**

  ```bash
  python -m gradefactory --grade --rubric path/to/my_rubric.json
  ```

## Rubric Formats

GradeFactory supports rubrics in PDF or JSON format. The grading system can handle both general essays and essay test answers.

### JSON Rubric Structure

For JSON rubrics, the structure should include the rubric content. For essay tests, optionally include `"question"` and `"correct_answers"` fields.

**Example for General Essays:**

```json
{
  "rubric": "Your full rubric text here..."
}
```

**Example for Essay Tests:**

```json
{
  "rubric": "Your full grading rubric text here...",
  "question": "What is the significance of the Industrial Revolution?",
  "correct_answers": [
    "The Industrial Revolution marked a shift from agrarian economies to industrialized ones, leading to urbanization and technological advancements.",
    "It transformed societies by introducing mechanized production, changing labor dynamics, and paving the way for modern capitalism."
  ]
}
```

The `question` field provides the essay prompt for context. The `correct_answers` array provides sample correct responses to guide the AI in evaluating accuracy and relevance.
## Web API

A FastAPI service is available for triggering runs from a browser or intranet tool. Start it with uvicorn:

```bash
uvicorn gradefactory.api:app --host 0.0.0.0 --port 8000
```

### Endpoints

- `POST /jobs/process` — upload one or more raw PDF essays as `raw_files`. Optional `name_flag` form field mirrors the CLI flag.
- `POST /jobs/grade` — upload processed PDF essays as `processed_files` and a rubric file (PDF or JSON) as `rubric`.
- `POST /jobs/full` — upload raw PDF essays plus a rubric and run OCR + grading in one shot.
- `GET /jobs` — list active and completed jobs with their current status.
- `GET /jobs/{job_id}` — return detailed stage results (logs and generated files) for a single job.
- `GET /jobs/{job_id}/artifacts/{path}` — download any generated PDF/CSV relative to the job workspace (paths are returned in the job detail response).

### Job lifecycle

Each request is executed asynchronously in a background worker. Job status values are:

- `pending` — accepted and waiting for a worker.
- `running` — at least one stage is currently executing.
- `completed` — all required stages finished successfully.
- `failed` — a stage raised an error; check the stage `stderr` field in the job detail payload.

Artifacts for each job are stored under `jobs/<job_id>/` with subfolders:

- `raw/` — original uploads for processing.
- `processed/` — cleaned PDFs ready for grading.
- `graded/` — grading reports and the batch CSV summary.
- `rubric/` — the rubric that was uploaded with the job.

Returned artifact paths are relative to the job root so they can be passed straight into the download endpoint.

### Browser dashboard

A minimal web dashboard is bundled with the API. Once the uvicorn server is running, open `http://localhost:8000/` to upload PDFs, start jobs, and monitor progress. The page polls `/jobs` for updates and links directly to generated PDFs/CSVs via the download endpoint.
