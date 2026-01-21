import calendar
import datetime as dt
import os
import requests

def end_of_month(year:int, month) -> dt.date:
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, last_day)


def send_verification_email(to_email: str, code: str) -> bool:
    """Send verification code via Brevo API."""
    api_key = os.getenv("EMAIL_API_KEY")
    if not api_key:
        return False

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "content-type": "application/json"},
            json={
                "sender": {"name": "TrackStack", "email": "verify@trackstack.uk"},
                "to": [{"email": to_email}],
                "subject": "Your TrackStack verification code",
                "htmlContent": f'<p>Your verification code is: <strong>{code}</strong></p><p>Expires in 15 minutes.</p>',
            },
        )
        return response.status_code == 201
    except:
        return False