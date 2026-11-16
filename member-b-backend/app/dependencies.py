"""供 API 路由复用的数据库、登录用户和教师依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import current_user, student_user, teacher_user

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
TeacherUser = Annotated[User, Depends(teacher_user)]
StudentUser = Annotated[User, Depends(student_user)]
