COURSE = {'id': 'course-ds', 'name': '数据结构', 'description': '仅含栈、队列的自编最小样例，后续扩展为任务书规定数据规模。'}
KNOWLEDGE_POINTS = [{'id': 'kp-stack', 'name': '栈'}, {'id': 'kp-queue', 'name': '队列'}]
RESOURCES = [
    {'resource_id': 'res-stack', 'title': '栈示例材料', 'knowledge_point_ids': ['kp-stack']},
    {'resource_id': 'res-queue', 'title': '队列示例材料', 'knowledge_point_ids': ['kp-queue']},
]

def q(id, stem, kp, correct='A'):
    return {'id': id, 'stem': stem, 'kind': 'single', 'knowledge_point_ids': [kp],
            'options': [{'id':'A','text': {'q-stack-1':'后进先出','q-stack-2':'栈顶','q-stack-3':'3','q-queue-1':'先进先出','q-queue-2':'队尾','q-queue-3':'1'}[id]}, {'id':'B','text':'以上均不正确'}],
            'correct_option_ids': [correct]}

QUESTIONS = [
    q('q-stack-1','栈遵循哪一种访问原则？','kp-stack'),
    q('q-stack-2','入栈与出栈操作发生在哪一端？','kp-stack'),
    q('q-stack-3','依次将1、2、3入栈，第一次出栈得到哪个元素？','kp-stack'),
    q('q-queue-1','队列遵循哪一种访问原则？','kp-queue'),
    q('q-queue-2','普通队列的新元素从哪一端进入？','kp-queue'),
    q('q-queue-3','依次将1、2、3入队，第一次出队得到哪个元素？','kp-queue'),
]

def public_question(question):
    return {k:v for k,v in question.items() if k != 'correct_option_ids'}
