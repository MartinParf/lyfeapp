from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

TOKEN_SALT = "core.email_verification"


def build_email_verification_token(user):
    payload = {
        "user_id": user.pk,
        "email": user.email,
    }
    return signing.dumps(payload, salt=TOKEN_SALT)


def load_email_verification_token(token):
    return signing.loads(
        token,
        salt=TOKEN_SALT,
        max_age=settings.EMAIL_VERIFICATION_TIMEOUT,
    )


def send_email_verification_email(request, user):
    if not user.email:
        raise ValueError("User does not have an email address.")

    token = build_email_verification_token(user)
    verification_url = request.build_absolute_uri(
        reverse("email-verification-confirm", kwargs={"token": token})
    )

    context = {
        "user": user,
        "verification_url": verification_url,
    }

    subject = render_to_string(
        "registration/email_verification_subject.txt",
        context,
    ).strip()

    body = render_to_string(
        "registration/email_verification_email.txt",
        context,
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )

    return verification_url