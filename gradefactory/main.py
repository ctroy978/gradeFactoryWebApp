import argparse
import sys
from pathlib import Path

from .pipeline import GradeFactoryPipeline
from .utils import load_api_keys

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
ESSAYS_TO_GRADE_FOLDER = BASE_DIR / "essays_to_grade"
GRADED_ESSAYS_FOLDER = BASE_DIR / "graded_essays"

PIPELINE = GradeFactoryPipeline(
    processed_dir=ESSAYS_TO_GRADE_FOLDER,
    graded_dir=GRADED_ESSAYS_FOLDER,
)

def main():
    parser = argparse.ArgumentParser(description="GradeFactory: A tool for processing and grading handwritten essays.")

    parser.add_argument("--process", action="store_true", help="Run the processing workflow (OCR and text correction). Requires --input-folder.")
    parser.add_argument("--grade", action="store_true", help="Run the grading workflow. Requires --rubric.")
    parser.add_argument("--full-pipeline", action="store_true", help="Run the full workflow from processing to grading. Requires --input-folder and --rubric.")

    parser.add_argument("--input-folder", type=str, help="Path to the folder containing the raw, multi-page PDF essays.")
    parser.add_argument("--rubric", type=str, help="Path to the rubric file (PDF or JSON).")
    parser.add_argument("--name", action="store_true", help="Use student's name as the filename for processed essays.")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    if args.process and not args.input_folder:
        parser.error("--process requires --input-folder.")

    if args.grade and not args.rubric:
        parser.error("--grade requires --rubric.")

    if args.full_pipeline and (not args.input_folder or not args.rubric):
        parser.error("--full-pipeline requires --input-folder and --rubric.")

    try:
        xai_api_key = load_api_keys()

        if args.process:
            result = PIPELINE.run_processing(
                args.input_folder,
                name_flag=args.name,
                xai_api_key=xai_api_key,
            )
            sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)

        elif args.grade:
            result = PIPELINE.run_grading(
                ESSAYS_TO_GRADE_FOLDER,
                rubric_path=Path(args.rubric),
                xai_api_key=xai_api_key,
            )
            sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)

        elif args.full_pipeline:
            result = PIPELINE.run_full_pipeline(
                args.input_folder,
                rubric_path=Path(args.rubric),
                name_flag=args.name,
                xai_api_key=xai_api_key,
            )
            if result.processing:
                sys.stdout.write(result.processing.stdout)
                if result.processing.stderr:
                    sys.stderr.write(result.processing.stderr)
            if result.grading:
                sys.stdout.write(result.grading.stdout)
                if result.grading.stderr:
                    sys.stderr.write(result.grading.stderr)

    except (ValueError, FileNotFoundError, IOError, RuntimeError) as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
