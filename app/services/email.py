from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from pathlib import Path
import os
from app.core.config import settings

async def send_email(to_email: str, subject: str, template_name: str, **kwargs):
    template_path = Path(__file__).parent.parent / "templates" / "emails" / f"{template_name}.html"
    with open(template_path, 'r') as f:
        html_content = f.read()
    
    # Replace variables in template
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
        print(f"📄 Template: {template_name}")
        print(f"🎨 HTML preview (first 200 chars): {html_content[:200]}")
        sg = SendGridAPIClient(settings.SMTP_PASSWORD)
        response = sg.send(message)
        print(f"✅ Email sent! Status: {response.status_code}")
        return response.status_code
    except Exception as e:
        print(f"Email error: {str(e)}")
        raise
