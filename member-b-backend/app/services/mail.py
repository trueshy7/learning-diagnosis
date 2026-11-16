"""通过加密 SMTP 发送注册、重置密码验证码，不记录邮件正文或凭据。"""

from email.message import EmailMessage
import smtplib
import ssl

from .. import config
from ..email_utils import normalize_email
from .verification import CODE_TTL_SECONDS, GeneratedVerificationCode


class MailConfigurationError(RuntimeError):
    pass


class MailDeliveryError(RuntimeError):
    pass


def validate_mail_configuration() -> None:
    if not all((config.SMTP_HOST, config.SMTP_USERNAME, config.SMTP_PASSWORD, config.SMTP_FROM)):
        raise MailConfigurationError('请配置 SMTP_HOST、SMTP_USERNAME、SMTP_PASSWORD 和 SMTP_FROM')
    if config.SMTP_SECURITY not in ('ssl', 'starttls'):
        raise MailConfigurationError('SMTP_SECURITY 只能是 ssl 或 starttls')
    if not 1 <= config.SMTP_PORT <= 65535 or config.SMTP_TIMEOUT <= 0:
        raise MailConfigurationError('SMTP 端口或超时配置不正确')
    try:
        normalize_email(config.SMTP_FROM)
    except ValueError as exc:
        raise MailConfigurationError('SMTP_FROM 必须是有效邮箱地址') from exc


def send_registration_code_email(generated: GeneratedVerificationCode) -> None:
    _send_code_email(generated, '注册')


def send_password_reset_code_email(generated: GeneratedVerificationCode) -> None:
    _send_code_email(generated, '重置密码')


def _send_code_email(generated: GeneratedVerificationCode, action: str) -> None:
    validate_mail_configuration()
    recipient = normalize_email(generated.email)
    message = EmailMessage()
    message['Subject'] = f'学习诊断系统{action}验证码'
    message['From'] = normalize_email(config.SMTP_FROM)
    message['To'] = recipient
    message.set_content(
        f'你的{action}验证码是：{generated.code}\n\n'
        f'验证码 {CODE_TTL_SECONDS // 60} 分钟内有效，请勿向他人透露。\n'
        '如果不是你本人操作，请忽略这封邮件。\n'
    )
    context = ssl.create_default_context()
    try:
        if config.SMTP_SECURITY == 'ssl':
            connection = smtplib.SMTP_SSL(
                config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT, context=context,
            )
        else:
            connection = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT)
        with connection as smtp:
            if config.SMTP_SECURITY == 'starttls':
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailDeliveryError('验证码邮件发送失败') from exc
