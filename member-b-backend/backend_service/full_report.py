"""将 D 的真实规则诊断结果转换成 full-v1 持久报告。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .full_common import iso, question_dto, resource_dto
from .models import FullAttempt, FullReport, Question, QuestionState, Resource, ResourceMeta

RULE_VERSION = 'rule-template-v1'
DATA_VERSION = 'business-snapshot-v1'


def build_report(db: Session, attempt: FullAttempt, diagnosis: dict, report_id: str, timestamp: int) -> dict:
    graded = attempt.payload['graded_answers']
    wrong_by_point: dict[str, list[str]] = {}
    for answer in graded:
        if not answer['correct']:
            for point_id in answer['knowledge_point_ids']:
                wrong_by_point.setdefault(point_id, []).append(answer['question_id'])
    evidence = []
    for item in diagnosis.get('evidence', []):
        resource = db.get(Resource, item['resource_id'])
        meta = db.get(ResourceMeta, item['resource_id']) if resource else None
        version = f'v{meta.version}' if meta else (resource.index_version or 'v1') if resource else 'v1'
        evidence.append({'evidence_id': item['evidence_id'], 'resource_id': item['resource_id'],
                         'document_id': item['document_id'], 'chunk_id': item['chunk_id'],
                         'document_title': item.get('title') or item['document_id'],
                         'knowledge_point_ids': item['knowledge_point_ids'], 'text': item['text'],
                         'location': {'page_start': None, 'page_end': None,
                                      'section': str(item.get('location') or '') or None},
                         'source_label': item.get('source') or '课程资料',
                         'resource_version': version,
                         'availability': 'available' if resource and resource.status != 'deleted' else 'removed'})
    evidence_ids = {item['evidence_id'] for item in evidence}
    points = []
    for item in diagnosis['knowledge_points']:
        point_id = item['knowledge_point_id']
        count = item['sample_count']
        correct = item['correct_count']
        status = {'needs_practice': 'consolidating'}.get(item['status'], item['status'])
        points.append({'knowledge_point_id': point_id, 'name': item['name'],
                       'correct_count': correct, 'question_count': count,
                       'correct_rate': correct / count if count else None,
                       'mastery_score': correct / count if count >= 3 else None,
                       'mastery_status': status,
                       'coverage_reason': 'not_tested' if count == 0 else
                                          'too_few_questions' if count < 3 else None,
                       'wrong_question_ids': list(dict.fromkeys(wrong_by_point.get(point_id, []))),
                       'explanation': f'本次覆盖 {count} 道题，答对 {correct} 道。',
                       'evidence_ids': [ev['evidence_id'] for ev in evidence
                                        if point_id in ev['knowledge_point_ids']]})
    recommendations = []
    for priority, item in enumerate(diagnosis.get('recommendations', []), 1):
        resource = db.get(Resource, item['resource_id'])
        meta = db.get(ResourceMeta, item['resource_id']) if resource else None
        if resource is None or resource.status == 'deleted' or (meta and not meta.active):
            continue
        candidates = list(db.scalars(select(Question).where(Question.course_id == attempt.course_id)))
        practice = []
        for question in candidates:
            state = db.get(QuestionState, question.id)
            if (state is None or state.active) and item['knowledge_point_id'] in question.knowledge_point_ids:
                dto = question_dto(db, question)
                practice.append({'question_id': question.id, 'title': question.stem,
                                 'type': dto['type']})
        recommendations.append({'recommendation_id': f'{report_id}-rec-{priority}',
                                'knowledge_point_id': item['knowledge_point_id'],
                                'priority': priority, 'reason': item['reason'],
                                'next_step': f'复习 {resource.title} 后完成相关练习。',
                                'estimated_minutes': None,
                                'evidence_ids': [ev['evidence_id'] for ev in evidence
                                                 if item['knowledge_point_id'] in ev['knowledge_point_ids']],
                                'resources': [{key: resource_dto(db, resource)[key] for key in (
                                    'resource_id', 'course_id', 'title', 'kind', 'knowledge_point_ids',
                                    'difficulty', 'active', 'availability', 'source_label')}],
                                'practice_questions': practice[:10]})
    comparison = _comparison(db, attempt, points)
    fallback = diagnosis.get('fallback_status')
    trace = []
    for item in diagnosis.get('trace', []):
        step = item.get('agent')
        if step in ('diagnosis', 'retrieval', 'recommendation'):
            status = item.get('status')
            trace.append({'step': step, 'status': status if status in ('completed', 'skipped', 'failed') else 'completed',
                          'summary': status or step, 'duration_ms': None})
    report = {'report_id': report_id, 'attempt_id': attempt.id, 'user_id': attempt.user_id,
              'course_id': attempt.course_id, 'generated_at': iso(timestamp),
              'report_version': 'v1', 'rule_version': RULE_VERSION, 'data_version': DATA_VERSION,
              'source_mode': 'backend', 'explanation_mode': 'rule_template',
              'cached_from': None, 'is_degraded': bool(fallback),
              'degraded_reasons': [fallback] if fallback else [],
              'retrieval_status': 'available' if evidence else
                                  'failed' if fallback else 'empty',
              'score': attempt.payload['result']['score'],
              'summary': diagnosis.get('explanation') or '已完成规则诊断。',
              'knowledge_points': points, 'evidences': evidence,
              'recommendations': recommendations, 'comparison': comparison,
              'agent_steps': trace,
              'actions': {'can_retest': bool(points),
                          'can_practice': any(rec['practice_questions'] for rec in recommendations)}}
    return report


def _comparison(db: Session, attempt: FullAttempt, current_points: list[dict]) -> dict | None:
    baseline_id = attempt.payload.get('baseline_attempt_id')
    if not baseline_id:
        return None
    baseline = db.get(FullAttempt, baseline_id)
    baseline_report = db.scalar(select(FullReport).where(FullReport.attempt_id == baseline_id))
    before = {item['knowledge_point_id']: item for item in baseline_report.payload['knowledge_points']} if baseline_report else {}
    rows = []
    for point in current_points:
        prior = before.get(point['knowledge_point_id'])
        ready = bool(prior and prior['question_count'] >= 3 and point['question_count'] >= 3)
        before_rate = prior['correct_rate'] if prior else None
        after_rate = point['correct_rate']
        rows.append({'knowledge_point_id': point['knowledge_point_id'], 'name': point['name'],
                     'comparable': ready, 'reason': None if ready else '至少一次测验的有效题少于 3 道',
                     'baseline_correct_rate': before_rate, 'current_correct_rate': after_rate,
                     'baseline_question_count': prior['question_count'] if prior else 0,
                     'current_question_count': point['question_count'],
                     'delta_percentage_points': round((after_rate - before_rate) * 100, 2) if ready else None,
                     'difficulty_note': '仅比较同一知识点的观测正确率。'})
    before_questions = {item['question_id'] for item in baseline.payload['questions']} if baseline else set()
    after_questions = {item['question_id'] for item in attempt.payload['questions']}
    overall = bool(baseline and before_questions == after_questions and
                   baseline.payload.get('result') and attempt.payload.get('result'))
    before_pct = baseline.payload['result']['score']['percentage'] if baseline and baseline.payload.get('result') else None
    after_pct = attempt.payload['result']['score']['percentage']
    return {'baseline_attempt_id': baseline_id, 'current_attempt_id': attempt.id,
            'baseline_rule_version': RULE_VERSION, 'current_rule_version': RULE_VERSION,
            'overall_comparable': overall,
            'overall_reason': None if overall else '试卷题目不同或基线无有效成绩',
            'overall_delta_percentage_points': round(after_pct - before_pct, 2) if overall else None,
            'knowledge_points': rows}
