from fastapi import HTTPException
from .fixtures import QUESTIONS

def grade(answers):
    bank = {q['id']: q for q in QUESTIONS}
    selected = {}
    for answer in answers:
        if answer.question_id in selected:
            raise HTTPException(422, '提交中包含重复题目')
        question = bank.get(answer.question_id)
        if not question:
            raise HTTPException(422, '提交中包含不属于本试卷的题目')
        values = answer.selected_option_ids
        if len(values) != len(set(values)) or not set(values) <= {o['id'] for o in question['options']}:
            raise HTTPException(422, '选项非法或重复')
        selected[answer.question_id] = set(values)
    # 所有试卷题目均计入；提交内遗漏的题目视为未答。
    graded = [{'question_id':q['id'], 'knowledge_point_ids':q['knowledge_point_ids'],
               'correct':selected.get(q['id'], set()) == set(q['correct_option_ids'])} for q in QUESTIONS]
    score = sum(int(a['correct']) for a in graded)
    return score, len(QUESTIONS), graded
