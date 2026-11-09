"""课程目录的数据库访问与演示数据初始化。"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Course, KnowledgePoint, Question, QuestionState, Resource
from .fixtures import COURSE, KNOWLEDGE_POINTS, QUESTIONS, RESOURCES


def seed_demo(db: Session) -> None:
    """只补齐缺失的演示记录，不覆盖教师编辑过的内容。"""
    if db.get(Course, COURSE['id']) is None:
        db.add(Course(**COURSE))
    for point in KNOWLEDGE_POINTS:
        if db.get(KnowledgePoint, point['id']) is None:
            db.add(KnowledgePoint(**point, course_id=COURSE['id']))
    for question in QUESTIONS:
        if db.get(Question, question['id']) is None:
            db.add(Question(**question, course_id=COURSE['id']))
    for item in RESOURCES:
        if db.get(Resource, item['resource_id']) is None:
            db.add(Resource(resource_id=item['resource_id'], document_id='doc-'+item['resource_id'].removeprefix('res-'),
                            course_id=COURSE['id'], title=item['title'], source='原创课程样例',
                            knowledge_point_ids=item['knowledge_point_ids'], status='seeded',
                            index_version=None, chunk_count=0, updated_at=0))
    db.commit()


def course_dict(course: Course) -> dict:
    return {'id': course.id, 'name': course.name, 'description': course.description}


def point_dict(point: KnowledgePoint) -> dict:
    return {'id': point.id, 'name': point.name}


def question_dict(question: Question, *, include_answer: bool = False, active: bool | None = None) -> dict:
    data = {'id': question.id, 'stem': question.stem, 'kind': question.kind,
            'knowledge_point_ids': question.knowledge_point_ids, 'options': question.options}
    if include_answer:
        data['correct_option_ids'] = question.correct_option_ids
    if active is not None:
        data['active'] = active
    return data


def course_questions(db: Session, course_id: str, *, include_inactive: bool = False) -> list[Question]:
    rows = list(db.scalars(select(Question).where(Question.course_id == course_id).order_by(Question.id)))
    if include_inactive:
        return rows
    disabled = set(db.scalars(select(QuestionState.question_id).where(QuestionState.active.is_(False))))
    return [row for row in rows if row.id not in disabled]


def question_active(db: Session, question_id: str) -> bool:
    state = db.get(QuestionState, question_id)
    return state is None or state.active


def course_points(db: Session, course_id: str) -> list[KnowledgePoint]:
    return list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id).order_by(KnowledgePoint.id)))


def resource_dict(row: Resource) -> dict:
    return {'resource_id': row.resource_id, 'document_id': row.document_id,
            'course_id': row.course_id, 'title': row.title, 'source': row.source,
            'knowledge_point_ids': row.knowledge_point_ids, 'status': row.status,
            'index_version': row.index_version, 'chunk_count': row.chunk_count,
            'updated_at': row.updated_at}
