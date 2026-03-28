from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from pathlib import Path
from app.core.config import settings

async def send_email(to_email: str, subject: str, template_name: str, **kwargs):
    template_path = Path(__file__).parent.parent / "templates" / "emails" / f"{template_name}.html"
    with open(template_path, 'r') as f:
        html_content = f.read()
    for key, value in kwargs.items():
        html_content = html_content.replace(f"{{{{{key}}}}}", str(value))
    message = Mail(
        from_email=settings.SENDGRID_FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        print(f"📧 Sending email to {to_email}")
        sg = SendGridAPIClient(settings.SMTP_PASSWORD)
        response = sg.send(message)
        print(f"✅ Email sent! Status: {response.status_code}")
        return response.status_code
    except Exception as e:
        print(f"Email error: {str(e)}")
        raise

async def send_welcome_email(to_email: str, name: str, dashboard_url: str):
    await send_email(to_email, "Welcome to Revozi!", "welcome", name=name, dashboard_url=dashboard_url)

async def send_verification_email(to_email: str, name: str, verification_url: str):
    await send_email(to_email, "Verify your email - Revozi", "verify", name=name, verification_url=verification_url)

async def send_reset_password_email(to_email: str, name: str, reset_url: str):
    await send_email(to_email, "Reset your password - Revozi", "reset_password", name=name, reset_url=reset_url)

async def send_subscription_email(to_email: str, name: str, plan_name: str, amount: str, billing_period: str, dashboard_url: str):
    await send_email(to_email, "Your Revozi subscription is active!", "subscription", name=name, plan_name=plan_name, amount=amount, billing_period=billing_period, dashboard_url=dashboard_url)

async def send_payment_success_email(to_email: str, name: str, amount: str, plan_name: str, next_billing_date: str, dashboard_url: str):
    await send_email(to_email, "Payment received - Revozi", "payment_success", name=name, amount=amount, plan_name=plan_name, next_billing_date=next_billing_date, dashboard_url=dashboard_url)

async def send_payment_failed_email(to_email: str, name: str, amount: str, update_url: str):
    await send_email(to_email, "Payment failed - action required", "payment_failed", name=name, amount=amount, update_url=update_url)

async def send_refund_email(to_email: str, name: str, amount: str, refund_date: str):
    await send_email(to_email, "Your refund has been processed - Revozi", "refund", name=name, amount=amount, refund_date=refund_date)

async def send_subscription_expired_email(to_email: str, name: str, rejoin_url: str):
    await send_email(to_email, "Your Revozi subscription has expired", "subscription_expired", name=name, rejoin_url=rejoin_url)

async def send_subscription_reminder_email(to_email: str, name: str, days_left: str, rejoin_url: str):
    await send_email(to_email, f"Your Revozi subscription expires in {days_left} days", "subscription_reminder", name=name, days_left=days_left, rejoin_url=rejoin_url)
