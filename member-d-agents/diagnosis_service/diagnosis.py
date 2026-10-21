"""纯规则函数：每题对其关联的每个知识点等权计数一次。"""

from .models import Comparison, DiagnoseRequest, KnowledgePointStat, classify


def diagnose(request: DiagnoseRequest) -> list[KnowledgePointStat]:
    # 相同 question_id 只计一次；矛盾重复已在请求验证阶段拒绝。
    answers = {answer.question_id: answer for answer in request.graded_answers}.values()
    counts = {point.id: [0, 0] for point in request.knowledge_points}
    for answer in answers:
        for point_id in answer.knowledge_point_ids:
            counts[point_id][1] += 1
            counts[point_id][0] += int(answer.correct)
    result = []
    for point in request.knowledge_points:
        correct, samples = counts[point.id]
        result.append(KnowledgePointStat(
            knowledge_point_id=point.id,
            name=point.name,
            correct_count=correct,
            sample_count=samples,
            accuracy=round(correct / samples, 6) if samples else None,
            status=classify(samples, correct),
        ))
    return result


def compare(request: DiagnoseRequest, current: list[KnowledgePointStat]) -> list[Comparison]:
    if request.baseline is None:
        return []
    before = {item.knowledge_point_id: item for item in request.baseline.knowledge_points}
    result = []
    for after in current:
        earlier = before.get(after.knowledge_point_id)
        if earlier is None or earlier.sample_count < 3 or after.sample_count < 3:
            continue
        if earlier.accuracy is None or after.accuracy is None:
            continue
        result.append(Comparison(
            knowledge_point_id=after.knowledge_point_id,
            before_accuracy=earlier.accuracy,
            after_accuracy=after.accuracy,
            delta=round(after.accuracy - earlier.accuracy, 6),
        ))
    return result

