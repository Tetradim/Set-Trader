"""SMTP email service for Sentinel Pulse."""
import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("SentinelPulse")

APP_VERSION = "1.0.0-beta"

def _get_smtp_config() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "recipient": os.environ.get("SMTP_RECIPIENT", ""),
    }


def _smtp_configured() -> bool:
    cfg = _get_smtp_config()
    return bool(cfg["host"] and cfg["user"] and cfg["password"] and cfg["recipient"])


def send_email(subject: str, body_html: str, from_email: str = "") -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    cfg = _get_smtp_config()
    if not _smtp_configured():
        logger.warning("SMTP not configured — email not sent: %s", subject)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email or cfg["user"]
        msg["To"] = cfg["recipient"]
        msg["Reply-To"] = from_email or cfg["user"]
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(msg["From"], [cfg["recipient"]], msg.as_string())

        logger.info("Email sent: %s", subject)
        return True
    except Exception as e:
        logger.error("Failed to send email '%s': %s", subject, e)
        return False


def send_registration_email(reg: dict) -> bool:
    """Send beta registration details to the admin."""
    subject = f"[Sentinel Pulse] New Beta Registration: {reg.get('first_name', '')} {reg.get('last_name', '')}"
    body = f"""
    <html><body style="font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px;">
    <h2 style="color: #58a6ff;">New Beta Tester Registration</h2>
    <table style="border-collapse: collapse; width: 100%;">
      <tr><td style="padding: 6px; color: #8b949e;">Name</td><td style="padding: 6px;">{reg.get('first_name', '')} {reg.get('last_name', '')}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Email</td><td style="padding: 6px;">{reg.get('email', '')}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Phone</td><td style="padding: 6px;">{reg.get('phone', 'N/A')}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">SSN Last 4</td><td style="padding: 6px;">****{reg.get('ssn_last4', '')}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Address</td><td style="padding: 6px;">{reg.get('address_street', '')}, {reg.get('address_city', '')}, {reg.get('address_state', '')} {reg.get('address_zip', '')}, {reg.get('address_country', '')}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Jurisdiction</td><td style="padding: 6px;">{reg.get('jurisdiction', '')}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Agreement Version</td><td style="padding: 6px;">{reg.get('agreement_version', '')}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Registered At</td><td style="padding: 6px;">{reg.get('registered_at', '')}</td></tr>
    </table>
    <p style="color: #484f58; font-size: 11px; margin-top: 20px;">Sentinel Pulse v{APP_VERSION}</p>
    </body></html>
    """
    return send_email(subject, body, from_email=reg.get("email", ""))


def send_feedback_email(feedback: dict, user: dict) -> bool:
    """Send a feedback/bug report email."""
    ftype = feedback.get("type", "general").upper()
    subject = f"[Sentinel Pulse] {ftype}: {feedback.get('subject', 'No Subject')}"

    user_name = f"{user.get('first_name', 'Unknown')} {user.get('last_name', '')}".strip()
    user_email = user.get("email", "unregistered")

    body = f"""
    <html><body style="font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px;">
    <h2 style="color: #58a6ff;">{ftype} Report</h2>
    <table style="border-collapse: collapse; width: 100%; margin-bottom: 16px;">
      <tr><td style="padding: 6px; color: #8b949e;">From</td><td style="padding: 6px;">{user_name} ({user_email})</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Type</td><td style="padding: 6px;">{ftype}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">App Version</td><td style="padding: 6px;">{APP_VERSION}</td></tr>
      <tr><td style="padding: 6px; color: #8b949e;">Subject</td><td style="padding: 6px;">{feedback.get('subject', '')}</td></tr>
    </table>
    <h3 style="color: #58a6ff;">Description</h3>
    <div style="background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 12px; white-space: pre-wrap;">{feedback.get('description', '')}</div>
    """

    if feedback.get("error_log"):
        body += f"""
    <h3 style="color: #f85149; margin-top: 16px;">Error Log</h3>
    <div style="background: #1c0e0e; border: 1px solid #f8514930; border-radius: 6px; padding: 12px; white-space: pre-wrap; font-size: 11px;">{feedback.get('error_log', '')}</div>
    """

    body += f"""
    <p style="color: #484f58; font-size: 11px; margin-top: 20px;">Sentinel Pulse v{APP_VERSION} | User: {user_email}</p>
    </body></html>
    """
    return send_email(subject, body, from_email=user_email)
