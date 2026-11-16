"""固定三个逻辑代理的顺序编排，无模型调用或自主规划。"""

from .diagnosis import compare, diagnose
from .models import DiagnoseRequest, KnowledgePointStat, Recommendation, Report, TraceStep
from .rag_client import Retriever, RetrievalResult


def recommend(request: DiagnoseRequest, targets: list[KnowledgePointStat], retrieval: RetrievalResult) -> list[Recommendation]:
    result = []
    for target in targets:
        # 优先采用检索命中的目录资源；没有命中时仍只能选择 B 提供的合法目录项。
        candidates = [resource for resource in request.resource_catalog if target.knowledge_point_id in resource.knowledge_point_ids]
        matching_ids = {e.resource_id for e in retrieval.evidence if target.knowledge_point_id in e.knowledge_point_ids}
        candidates.sort(key=lambda resource: (resource.resource_id not in matching_ids, resource.resource_id))
        if not candidates:
            continue
        resource = candidates[0]
        reason = f"规则建议：{target.name}共 {target.sample_count} 题，答对 {target.correct_count} 题，建议复习该知识点并补充练习。"
        if resource.resource_id in matching_ids:
            reason += "检索返回了该目录资源的相关片段；请结合原材料核对。"
        else:
            reason += "本建议仅依据作答统计与资源目录，尚无匹配检索证据。"
        result.append(Recommendation(
            knowledge_point_id=target.knowledge_point_id,
            resource_id=resource.resource_id,
            title=resource.title,
            reason=reason,
        ))
    return result


async def run_pipeline(request: DiagnoseRequest, retriever: Retriever) -> Report:
    statistics = diagnose(request)
    # 薄弱点优先，其次待巩固点；同级按输入知识点顺序，输出确定。
    targets = sorted(
        [point for point in statistics if point.status in {"weak", "needs_practice"}],
        key=lambda point: (point.status != "weak", point.accuracy),
    )
    trace = [TraceStep(agent="diagnosis", status="completed")]
    if targets:
        retrieval = await retriever.retrieve(request, targets)
    else:
        retrieval = RetrievalResult(status="skipped_no_eligible_knowledge_points")
    trace.append(TraceStep(agent="retrieval", status=retrieval.status))
    recommendations = recommend(request, targets, retrieval)
    trace.append(TraceStep(agent="recommendation", status="completed"))
    explanation = "本报告由固定的诊断→检索→推荐三阶段规则流程生成，mode=rule_template_demo，未接入真实大语言模型。"
    explanation += "知识点有效题少于 3 道时标记为证据不足，不生成该知识点的推荐或提升判断。"
    if retrieval.status == "mock_fixture":
        explanation += "检索使用明确标注的内置演示证据，尚未调用成员 C 的知识库。"
    if retrieval.fallback_status:
        explanation += f"检索未成功（{retrieval.fallback_status}），证据为空；目录建议仍可展示，但不视为检索成功。"
    explanation += "复测仅展示双方样本均不少于 3 题的同知识点准确率差值，该差值不能证明推荐造成学习提升。"
    return Report(
        attempt_id=request.attempt_id,
        knowledge_points=statistics,
        evidence=retrieval.evidence,
        recommendations=recommendations,
        explanation=explanation,
        comparison=compare(request, statistics),
        trace=trace,
        fallback_status=retrieval.fallback_status,
    )

