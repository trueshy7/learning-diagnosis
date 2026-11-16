"""纯函数评分和知识点统计，不调用模型或静态样例题库。"""

from decimal import Decimal


def classify(sample_count, correct_count):
    if sample_count < 3:
        return 'insufficient_evidence'
    accuracy = correct_count / sample_count
    return 'weak' if accuracy < 0.6 else 'needs_practice' if accuracy < 0.8 else 'mastered'


def grade_paper(paper, answers, knowledge_points):
    """paper 每项含 question_id、score、snapshot；缺失答案计零，多选不计部分分。"""
    statistics = {point['id']: {
        'knowledge_point_id': point['id'], 'name': point['name'],
        'sample_count': 0, 'correct_count': 0, 'evidence_question_ids': [],
    } for point in knowledge_points}
    grades, total = [], Decimal('0')
    for item in paper:
        snapshot = item['snapshot']
        selected = answers.get(item['question_id'], [])
        expected = {option['id'] for option in snapshot['options'] if option['is_correct']}
        correct = bool(expected) and len(selected) == len(set(selected)) and set(selected) == expected
        score = Decimal(str(item['score'])) if correct else Decimal('0')
        total += score
        grades.append({'question_id': item['question_id'], 'correct': correct, 'score': score})
        for point in snapshot['knowledge_points']:
            stat = statistics.setdefault(point['id'], {
                'knowledge_point_id': point['id'], 'name': point['name'],
                'sample_count': 0, 'correct_count': 0, 'evidence_question_ids': [],
            })
            stat['sample_count'] += 1
            stat['correct_count'] += int(correct)
            stat['evidence_question_ids'].append(item['question_id'])
    for stat in statistics.values():
        n, correct = stat['sample_count'], stat['correct_count']
        stat['accuracy'] = round(correct / n, 6) if n else None
        stat['status'] = classify(n, correct)
    return total, grades, list(statistics.values())


def compare_statistics(before, after):
    baseline = {stat['knowledge_point_id']: stat for stat in before}
    result = []
    for current in after:
        earlier = baseline.get(current['knowledge_point_id'])
        if earlier and earlier['sample_count'] >= 3 and current['sample_count'] >= 3:
            result.append({
                'knowledge_point_id': current['knowledge_point_id'],
                'before_accuracy': earlier['accuracy'], 'after_accuracy': current['accuracy'],
                'delta': round(current['accuracy'] - earlier['accuracy'], 6),
            })
    return result
