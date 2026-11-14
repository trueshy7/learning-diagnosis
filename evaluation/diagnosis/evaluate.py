"""Twelve fixed, transparent synthetic scenarios; no claim about real learners."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2] / 'member-d-agents'
sys.path.insert(0, str(ROOT))
from diagnosis_service.models import DiagnoseRequest
from diagnosis_service.orchestrator import run_pipeline
from diagnosis_service.rag_client import MockRetriever


def make_answers(right, total, point='kp-stack'):
    return [{'question_id': f'{point}-{i}', 'knowledge_point_ids': [point], 'correct': i < right}
            for i in range(total)]

CASES = [
    ('zero', [], 'insufficient_evidence', None, 0),
    ('two_wrong', make_answers(0, 2), 'insufficient_evidence', 0.0, 0),
    ('two_right', make_answers(2, 2), 'insufficient_evidence', 1.0, 0),
    ('three_weak', make_answers(1, 3), 'weak', 1/3, 1),
    ('five_below_60', make_answers(2, 5), 'weak', 0.4, 1),
    ('five_at_60', make_answers(3, 5), 'needs_practice', 0.6, 1),
    ('ten_below_80', make_answers(7, 10), 'needs_practice', 0.7, 1),
    ('five_at_80', make_answers(4, 5), 'mastered', 0.8, 0),
    ('all_right', make_answers(3, 3), 'mastered', 1.0, 0),
    ('all_wrong', make_answers(0, 5), 'weak', 0.0, 1),
    ('duplicate_question', make_answers(1, 3) + make_answers(1, 3), 'weak', 1/3, 1),
    ('multiple_knowledge_points', [{'question_id': f'cross-{i}', 'knowledge_point_ids': ['kp-stack', 'kp-queue'], 'correct': i == 0} for i in range(3)], 'weak', 1/3, 1),
]

async def evaluate():
    rows = []
    for name, answers, status, accuracy, recommendation_count in CASES:
        payload = {'attempt_id': name, 'course_id': 'course-ds', 'graded_answers': answers,
                   'knowledge_points': [{'id': 'kp-stack', 'name': '栈'}, {'id': 'kp-queue', 'name': '队列'}],
                   'resource_catalog': [{'resource_id': 'res-stack', 'title': '栈资料', 'knowledge_point_ids': ['kp-stack']}],
                   'baseline': None}
        report = await run_pipeline(DiagnoseRequest.model_validate(payload), MockRetriever())
        point = report.knowledge_points[0]
        count = sum(r.knowledge_point_id == 'kp-stack' for r in report.recommendations)
        valid = (point.status == status and (accuracy is None and point.accuracy is None or
                 accuracy is not None and abs(point.accuracy - accuracy) < 1e-6)
                 and count == recommendation_count
                 and all(r.resource_id == 'res-stack' for r in report.recommendations)
                 and (name != 'multiple_knowledge_points' or report.knowledge_points[1].sample_count == 3))
        rows.append({'case': name, 'expected_status': status, 'actual_status': point.status,
                     'sample_count': point.sample_count, 'actual_accuracy': point.accuracy,
                     'recommendation_count': count, 'passed': valid})
    return rows

if __name__ == '__main__':
    result = asyncio.run(evaluate())
    print(json.dumps({'scenario_count': len(result), 'passed': sum(x['passed'] for x in result), 'cases': result}, ensure_ascii=False, indent=2))
    if not all(x['passed'] for x in result):
        raise SystemExit(1)
