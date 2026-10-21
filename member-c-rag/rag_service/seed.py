from .index import LocalIndex
from .schemas import IngestRequest


# 本项目原创的两份极小教学示例，不代表已经建设完整课程知识库。
SEED_DOCUMENTS = [
    {"resource_id": "res-stack", "document_id": "doc-stack", "course_id": "course-ds",
     "title": "栈：后进先出的线性结构", "knowledge_point_ids": ["kp-stack"],
     "source": "原创课程样例/栈基础.txt",
     "text": "栈是一种后进先出（LIFO）的线性数据结构。插入和删除通常发生在栈顶。\n\n"
             "入栈 push 将元素放到栈顶，出栈 pop 移除并返回栈顶元素。读取栈顶 peek 不删除元素。"
             "例如按顺序将 A、B、C 入栈，连续出栈得到 C、B、A。空栈不能出栈，应返回明确的错误或空状态。\n\n"
             "顺序栈可以使用数组保存元素，链栈使用链表保存元素。基本入栈和出栈操作通常为 O(1)。"
             "栈适合括号匹配、函数调用管理和撤销操作。括号匹配时遇到左括号入栈，遇到右括号检查并弹出对应左括号。"},
    {"resource_id": "res-queue", "document_id": "doc-queue", "course_id": "course-ds",
     "title": "队列：先进先出的线性结构", "knowledge_point_ids": ["kp-queue"],
     "source": "原创课程样例/队列基础.txt",
     "text": "队列是一种先进先出（FIFO）的线性数据结构。通常在队尾入队，在队头出队。\n\n"
             "入队 enqueue 把元素放在队尾，出队 dequeue 移除并返回队头元素。"
             "例如依次将 A、B、C 入队，连续出队得到 A、B、C。空队列出队时，应返回明确的错误或空状态。\n\n"
             "循环队列用数组和头尾指针复用存储空间。若保留一个空位，队空条件为 front == rear，"
             "队满条件为 (rear + 1) % capacity == front。若使用计数器，判空和判满条件应与该实现保持一致。"
             "队列适合广度优先搜索、任务调度和消息缓冲；广度优先搜索依靠队列按层次访问节点。"},
]


def seed(index: LocalIndex) -> list[dict]:
    return [index.ingest(IngestRequest(**document)) for document in SEED_DOCUMENTS]
