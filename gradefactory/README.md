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
