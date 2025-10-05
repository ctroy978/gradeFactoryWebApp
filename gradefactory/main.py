import argparse
import sys
import os

from .utils import load_api_keys
from .processing import run_processing
from .grading import run_grading

# Get the absolute path of the directory containing this script
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Standardized folder paths made absolute
ESSAYS_TO_GRADE_FOLDER = os.path.join(os.path.dirname(APP_DIR), "essays_to_grade")
GRADED_ESSAYS_FOLDER = os.path.join(os.path.dirname(APP_DIR), "graded_essays")

def main():
    parser = argparse.ArgumentParser(description="GradeFactory: A tool for processing and grading handwritten essays.")

    # Workflow flags
    parser.add_argument("--process", action="store_true", help="Run the processing workflow (OCR and text correction). Requires --input-folder.")
    parser.add_argument("--grade", action="store_true", help="Run the grading workflow. Requires --rubric.")
    parser.add_argument("--full-pipeline", action="store_true", help="Run the full workflow from processing to grading. Requires --input-folder and --rubric.")

    # Path and model flags
    parser.add_argument("--input-folder", type=str, help="Path to the folder containing the raw, multi-page PDF essays.")
    parser.add_argument("--rubric", type=str, help="Path to the rubric file (PDF or JSON).")
    parser.add_argument("--name", action="store_true", help="Use student's name as the filename for processed essays.")

    # If no arguments are provided, print help
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # Basic validation
    if args.process and not args.input_folder:
        parser.error("--process requires --input-folder.")

    if args.grade and not args.rubric:
        parser.error("--grade requires --rubric.")

    if args.full_pipeline and (not args.input_folder or not args.rubric):
        parser.error("--full-pipeline requires --input-folder and --rubric.")

    # --- Workflow Execution ---
    try:
        xai_api_key = load_api_keys()

        if args.process:
            run_processing(args.input_folder, ESSAYS_TO_GRADE_FOLDER, args.name, xai_api_key)

        elif args.grade:
            run_grading(ESSAYS_TO_GRADE_FOLDER, GRADED_ESSAYS_FOLDER, args.rubric, xai_api_key)

        elif args.full_pipeline:
            run_processing(args.input_folder, ESSAYS_TO_GRADE_FOLDER, args.name, xai_api_key)
            run_grading(ESSAYS_TO_GRADE_FOLDER, GRADED_ESSAYS_FOLDER, args.rubric, xai_api_key)

    except (ValueError, FileNotFoundError, IOError, RuntimeError) as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
