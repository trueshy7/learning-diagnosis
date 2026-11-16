"""邮箱验证码、用户注册及密码重置接口。"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from . import ok
from ..dependencies import DbSession
from ..models import User
from ..schemas import RegisterIn, ResetPasswordIn, SendRegisterCodeIn
from ..services.password_reset import EmailNotRegistered, reset_password
from ..services.registration import (
    AccountAlreadyExists,
    InvalidVerificationCode,
    VerificationAttemptsExceeded,
    register_user,
)
from ..services.mail import (
    MailConfigurationError,
    MailDeliveryError,
    send_registration_code_email,
    send_password_reset_code_email,
    validate_mail_configuration,
)
from ..services.verification import (
    CODE_COOLDOWN_SECONDS,
    CODE_TTL_SECONDS,
    VerificationCodeTooFrequent,
    VerificationConfigurationError,
    issue_registration_code,
    issue_email_code,
    RESET_PASSWORD_PURPOSE,
)

router = APIRouter(prefix='/user', tags=['用户账户'])


@router.post('/send-register-code')
def send_register_code(body: SendRegisterCodeIn, request: Request, db: DbSession):
    try:
        validate_mail_configuration()
        generated = issue_registration_code(db, body.email, deliver=send_registration_code_email)
    except VerificationCodeTooFrequent as exc:
        raise HTTPException(429, str(exc), headers={'Retry-After': str(exc.retry_after)}) from exc
    except (MailConfigurationError, VerificationConfigurationError) as exc:
        raise HTTPException(503, '验证码邮件服务尚未配置完成') from exc
    except MailDeliveryError as exc:
        raise HTTPException(502, '邮件发送失败，请稍后重试') from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, '验证码服务暂不可用，请稍后重试') from exc
    return ok(request, {
        'sent': True,
        'email': generated.email,
        'expires_in': CODE_TTL_SECONDS,
        'retry_after': CODE_COOLDOWN_SECONDS,
    })


@router.post('/register', status_code=201)
def register(body: RegisterIn, request: Request, db: DbSession):
    try:
        user = register_user(db, body)
    except InvalidVerificationCode as exc:
        raise HTTPException(400, str(exc)) from exc
    except VerificationAttemptsExceeded as exc:
        raise HTTPException(429, str(exc)) from exc
    except AccountAlreadyExists as exc:
        raise HTTPException(409, str(exc)) from exc
    except VerificationConfigurationError as exc:
        raise HTTPException(503, '验证码服务尚未配置完成') from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, '注册服务暂不可用，请稍后重试') from exc
    return ok(request, {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
    })


@router.post('/send-reset-password-code')
def send_reset_password_code(body: SendRegisterCodeIn, request: Request, db: DbSession):
    try:
        if db.scalar(select(User.id).where(User.email == body.email)) is None:
            db.rollback()
            raise HTTPException(404, '该邮箱尚未注册')
        validate_mail_configuration()
        generated = issue_email_code(db, body.email, RESET_PASSWORD_PURPOSE, deliver=send_password_reset_code_email)
    except VerificationCodeTooFrequent as exc:
        raise HTTPException(429, str(exc), headers={'Retry-After': str(exc.retry_after)}) from exc
    except (MailConfigurationError, VerificationConfigurationError) as exc:
        db.rollback()
        raise HTTPException(503, '验证码邮件服务尚未配置完成') from exc
    except MailDeliveryError as exc:
        raise HTTPException(502, '邮件发送失败，请稍后重试') from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, '验证码服务暂不可用，请稍后重试') from exc
    return ok(request, {
        'sent': True, 'email': generated.email,
        'expires_in': CODE_TTL_SECONDS, 'retry_after': CODE_COOLDOWN_SECONDS,
    })


@router.post('/resetPassword')
def reset_password_endpoint(body: ResetPasswordIn, request: Request, db: DbSession):
    try:
        reset_password(db, body)
    except InvalidVerificationCode as exc:
        raise HTTPException(400, str(exc)) from exc
    except VerificationAttemptsExceeded as exc:
        raise HTTPException(429, str(exc)) from exc
    except EmailNotRegistered as exc:
        raise HTTPException(404, str(exc)) from exc
    except VerificationConfigurationError as exc:
        raise HTTPException(503, '验证码服务尚未配置完成') from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, '重置密码服务暂不可用，请稍后重试') from exc
    return ok(request, {'password_reset': True})
