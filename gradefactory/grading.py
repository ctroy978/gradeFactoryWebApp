import os
import sys
import csv
import re
import concurrent.futures
from collections import OrderedDict
import requests

from .prompts import GRADING_PROMPT, MODERATOR_PROMPT
from .utils import get_rubric_data, extract_text_from_pdf, save_to_pdf

def get_evaluation(api_key, prompt, temperature, rubric_text, question, correct_answers, paper_text):
    """
    Gets evaluation from Grok model.
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    question_text = f"Question:\n{question}\n\n" if question else ""
    answers_text = f"Correct Answers:\n" + "\n".join([f"- {ans}" for ans in correct_answers]) + "\n\n" if correct_answers else ""
    full_prompt = f"""Calibrate evaluations for community college freshmen: Be fair, constructive, and motivational. Typical papers should score 10-15/20, not failing unless severely deficient.\n\n{prompt}\n\n{question_text}{answers_text}Rubric:\n{rubric_text}\n\nStudent Paper:\n{paper_text}"""
    data = {"messages": [{"role": "user", "content": full_prompt}], "model": "grok-4-fast-reasoning", "stream": False, "temperature": temperature}
    response = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=data)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def moderate_evaluations(api_key, evaluation_a, evaluation_b, rubric_text, question, correct_answers, paper_text):
    """
    Moderates two evaluations using Grok.
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    question_text = f"Question:\n{question}\n\n" if question else ""
    answers_text = f"Correct Answers:\n" + "\n".join([f"- {ans}" for ans in correct_answers]) + "\n\n" if correct_answers else ""
    prompt = f"""Calibrate evaluations for community college freshmen: Be fair, constructive, and motivational. Typical papers should score 10-15/20, not failing unless severely deficient.\n\n{MODERATOR_PROMPT}\n\n{question_text}{answers_text}Rubric:\n{rubric_text}\nStudent Paper:\n{paper_text}\nEvaluation from Grader A:\n{evaluation_a}\nEvaluation from Grader B:\n{evaluation_b}"""
    data = {"messages": [{"role": "user", "content": prompt}], "model": "grok-4-fast-reasoning", "stream": False, "temperature": 0.7}
    response = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=data)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def parse_score_summary(evaluation_text):
    """Extracts rubric criterion and total scores (earned, max) from the moderator output."""
    criterion_pattern = re.compile(r'^\s*([^:\n]+):\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\b', re.MULTILINE)
    total_pattern = re.compile(r'^\s*(?:Total|Overall(?:\s+Score)?|Final\s+Score):\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\b', re.IGNORECASE | re.MULTILINE)

    criterion_scores = OrderedDict()
    for match in criterion_pattern.finditer(evaluation_text):
        label = match.group(1).strip()
        if label.lower() == 'total':
            continue
        earned = float(match.group(2))
        maximum = float(match.group(3))
        if label not in criterion_scores:
            criterion_scores[label] = (earned, maximum)

    total_score = None
    total_match = total_pattern.search(evaluation_text)
    if total_match:
        total_score = (float(total_match.group(1)), float(total_match.group(2)))
    elif criterion_scores:
        earned_sum = sum(score[0] for score in criterion_scores.values())
        max_sum = sum(score[1] for score in criterion_scores.values())
        total_score = (earned_sum, max_sum)

    return criterion_scores, total_score

def format_score_tuple(score_tuple):
    """Converts a (earned, max) tuple to a display string."""
    if not score_tuple:
        return ""

    earned, maximum = score_tuple

    def fmt(value):
        if value is None:
            return ""
        if isinstance(value, (int, float)) and float(value).is_integer():
            return str(int(round(float(value))))
        if isinstance(value, (int, float)):
            return f"{value:.2f}".rstrip('0').rstrip('.')
        return str(value)

    return f"{fmt(earned)}/{fmt(maximum)}"

def save_batch_summary(output_folder, criteria, batch_results):
    """Writes a CSV table summarizing rubric scores for the batch."""
    summary_path = os.path.join(output_folder, "batch_scores.csv")
    header = ["Essay"] + criteria + ["Total"]

    with open(summary_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)
        for result in batch_results:
            row = [result['filename']]
            for criterion in criteria:
                score = result['scores'].get(criterion)
                row.append(format_score_tuple(score))
            row.append(format_score_tuple(result['total']))
            writer.writerow(row)

    print(f"\nBatch score summary saved to {summary_path}")

def evaluate_paper(rubric_data, paper_text, xai_api_key):
    """
    Evaluates the student paper using a multi-agent system with Grok.
    rubric_data: dict with 'rubric', 'question', 'correct_answers'
    """
    try:
        rubric_text = rubric_data['rubric']
        question = rubric_data['question']
        correct_answers = rubric_data['correct_answers']
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            if not xai_api_key:
                raise ValueError("XAI_API_KEY is required.")
            future_a = executor.submit(get_evaluation, xai_api_key, GRADING_PROMPT, 0.4, rubric_text, question, correct_answers, paper_text)
            future_b = executor.submit(get_evaluation, xai_api_key, GRADING_PROMPT, 0.8, rubric_text, question, correct_answers, paper_text)

            evaluation_a = future_a.result()
            evaluation_b = future_b.result()

        final_evaluation = moderate_evaluations(xai_api_key, evaluation_a, evaluation_b, rubric_text, question, correct_answers, paper_text)
        
        return evaluation_a, evaluation_b, final_evaluation

    except Exception as e:
        raise RuntimeError(f"Error during API call: {e}")

def run_grading(input_folder, output_folder, rubric_path, xai_api_key=None):
    """
    Evaluates a batch of papers in a folder using Grok.
    """
    print("--- Starting Grading Process ---")
    rubric_data = get_rubric_data(rubric_path)

    if not os.path.isdir(input_folder):
        raise FileNotFoundError(f"Input folder not found: {input_folder}")
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder)

    batch_results = []
    criteria_order = []

    for filename in os.listdir(input_folder):
        if filename.lower().endswith(".pdf"):
            paper_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)
            print(f"\nGrading {paper_path}...")

            try:
                paper_text = extract_text_from_pdf(paper_path)
                evaluation_a, evaluation_b, final_evaluation = evaluate_paper(rubric_data, paper_text, xai_api_key)

                evaluation_text = f"--- Agent 1 Evaluation ---\n{evaluation_a}\n--- End of Agent 1 Evaluation ---\n\n"
                evaluation_text += f"--- Agent 2 Evaluation ---\n{evaluation_b}\n--- End of Agent 2 Evaluation ---\n\n"
                evaluation_text += f"--- Final Moderator Evaluation ---\n{final_evaluation}\n--- End of Final Moderator Evaluation ---\n"

                save_to_pdf(evaluation_text, output_path)
                print(f"  - Saved evaluation to {output_path}")

                criterion_scores, total_score = parse_score_summary(final_evaluation)
                if criterion_scores:
                    for criterion in criterion_scores.keys():
                        if criterion not in criteria_order:
                            criteria_order.append(criterion)
                    batch_results.append({
                        'filename': filename,
                        'scores': criterion_scores,
                        'total': total_score
                    })
                else:
                    print("  - Warning: Could not extract score summary for batch table.")

            except Exception as e:
                print(f"Error evaluating {paper_path}: {e}", file=sys.stderr)
    if batch_results and criteria_order:
        save_batch_summary(output_folder, criteria_order, batch_results)

    print("\n--- Grading Process Complete ---")
