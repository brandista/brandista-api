#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Email Notification System for Brandista - SendGrid Version
Sends admin notifications on new user registrations
Fixed: Uses SendGrid API instead of SMTP (Railway compatible)
"""

import os
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================

# Admin email settings (from environment)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "tuukka@brandista.eu")
FROM_EMAIL = os.getenv("FROM_EMAIL", "tuukka@brandista.eu")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

# Import SendGrid if available
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("SendGrid not installed. Install with: pip install sendgrid")

# ============================================================================
# EMAIL FUNCTIONS
# ============================================================================

def send_email(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """
    Send email via SendGrid API (Railway compatible)
    
    Args:
        to_email: Recipient email
        subject: Email subject
        html_body: HTML email body
        text_body: Plain text fallback (optional)
    
    Returns:
        bool: True if sent successfully
    """
    if not SENDGRID_AVAILABLE:
        logger.warning("SendGrid not available, skipping email")
        return False
    
    if not SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not configured, skipping email")
        return False
    
    try:
        message = Mail(
            from_email=Email(FROM_EMAIL),
            to_emails=To(to_email),
            subject=subject,
            plain_text_content=Content("text/plain", text_body) if text_body else None,
            html_content=Content("text/html", html_body)
        )
        
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        
        logger.info(f"✅ Email sent successfully to {to_email} (status: {response.status_code})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send email to {to_email}: {e}")
        return False


def send_new_user_notification(
    user_email: str,
    user_name: Optional[str] = None,
    registration_method: str = "email"
) -> bool:
    """
    Send admin notification about new user registration
    
    Args:
        user_email: New user's email
        user_name: New user's name (optional)
        registration_method: How they registered (email/google/magic-link)
    
    Returns:
        bool: True if sent successfully
    """
    
    # Email subject
    subject = f"🎉 Uusi käyttäjä rekisteröitynyt - {user_email}"
    
    # HTML email body
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 10px 10px 0 0;
                text-align: center;
            }}
            .content {{
                background: #f8f9fa;
                padding: 30px;
                border-radius: 0 0 10px 10px;
            }}
            .info-box {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
                border-left: 4px solid #667eea;
            }}
            .info-row {{
                display: flex;
                padding: 10px 0;
                border-bottom: 1px solid #e9ecef;
            }}
            .info-row:last-child {{
                border-bottom: none;
            }}
            .label {{
                font-weight: 600;
                color: #667eea;
                width: 150px;
            }}
            .value {{
                color: #495057;
            }}
            .footer {{
                text-align: center;
                padding: 20px;
                color: #6c757d;
                font-size: 14px;
            }}
            .emoji {{
                font-size: 48px;
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="emoji">🎉</div>
            <h1 style="margin: 0;">Uusi käyttäjä!</h1>
        </div>
        
        <div class="content">
            <p>Hei Admin,</p>
            <p>Brandista-palveluun on juuri rekisteröitynyt uusi käyttäjä.</p>
            
            <div class="info-box">
                <div class="info-row">
                    <div class="label">📧 Sähköposti:</div>
                    <div class="value"><strong>{user_email}</strong></div>
                </div>
                
                {f'''<div class="info-row">
                    <div class="label">👤 Nimi:</div>
                    <div class="value">{user_name}</div>
                </div>''' if user_name else ''}
                
                <div class="info-row">
                    <div class="label">🔐 Rekisteröitymistapa:</div>
                    <div class="value">{registration_method.title()}</div>
                </div>
                
                <div class="info-row">
                    <div class="label">📅 Aika:</div>
                    <div class="value">{datetime.now().strftime('%d.%m.%Y klo %H:%M')}</div>
                </div>
            </div>
            
            <p>Voit tarkastella käyttäjätietoja hallintapaneelista.</p>
        </div>
        
        <div class="footer">
            <p>Brandista Competitive Intelligence API</p>
            <p style="font-size: 12px; color: #adb5bd;">
                Tämä on automaattinen ilmoitus. Älä vastaa tähän viestiin.
            </p>
        </div>
    </body>
    </html>
    """
    
    # Plain text fallback
    text_body = f"""
    Uusi käyttäjä rekisteröitynyt Brandistaan
    
    Sähköposti: {user_email}
    {f'Nimi: {user_name}' if user_name else ''}
    Rekisteröitymistapa: {registration_method}
    Aika: {datetime.now().strftime('%d.%m.%Y klo %H:%M')}
    
    -- 
    Brandista Competitive Intelligence API
    """
    
    return send_email(ADMIN_EMAIL, subject, html_body, text_body)


def send_welcome_email(user_email: str, user_name: Optional[str] = None) -> bool:
    """
    Send welcome email to new user (optional)
    
    Args:
        user_email: User's email
        user_name: User's name (optional)
    
    Returns:
        bool: True if sent successfully
    """
    
    greeting = f"Hei {user_name}" if user_name else "Hei"
    
    subject = "Tervetuloa Brandistaan! 🚀"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                border-radius: 10px 10px 0 0;
                text-align: center;
            }}
            .content {{
                background: white;
                padding: 40px;
                border-radius: 0 0 10px 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .button {{
                display: inline-block;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px 30px;
                text-decoration: none;
                border-radius: 8px;
                margin: 20px 0;
                font-weight: 600;
            }}
            .features {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .feature {{
                padding: 10px 0;
            }}
            .emoji {{
                font-size: 64px;
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="emoji">🚀</div>
            <h1 style="margin: 0;">Tervetuloa Brandistaan!</h1>
        </div>
        
        <div class="content">
            <p>{greeting},</p>
            
            <p>Kiitos että liityit Brandistaan - kilpailuanalyysityökaluun, joka auttaa ymmärtämään kilpailijasi paremmin.</p>
            
            <div class="features">
                <h3 style="margin-top: 0;">Mitä voit tehdä Brandistalla:</h3>
                <div class="feature">🔍 <strong>Kilpailijahaku</strong> - Löydä kilpailijasi automaattisesti</div>
                <div class="feature">📊 <strong>Verkkosivuanalyysi</strong> - Analysoi tekninen toteutus</div>
                <div class="feature">💡 <strong>Strategiset suositukset</strong> - AI-avusteiset kehitysehdotukset</div>
                <div class="feature">📈 <strong>Seuranta</strong> - Pidä silmällä kilpailijoiden muutoksia</div>
            </div>
            
            <p style="text-align: center;">
                <a href="https://brandista.eu" class="button">Aloita analyysi →</a>
            </p>
            
            <p>Jos tarvitset apua, vastaa tähän viestiin tai ota yhteyttä tukeen.</p>
            
            <p>Onnea analyyseihin!</p>
            
            <p style="color: #6c757d; margin-top: 30px;">
                — Brandista Team
            </p>
        </div>
    </body>
    </html>
    """
    
    text_body = f"""
    {greeting},
    
    Kiitos että liityit Brandistaan!
    
    Voit nyt:
    - Löytää kilpailijasi automaattisesti
    - Analysoida verkkosivujen teknistä toteutusta
    - Saada AI-avusteisia strategisia suosituksia
    - Seurata kilpailijoiden muutoksia
    
    Aloita analyysi: https://brandista.eu
    
    -- 
    Brandista Team
    """
    
    return send_email(user_email, subject, html_body, text_body)


# ============================================================================
# INTEGRATION EXAMPLE
# ============================================================================

async def on_user_registered(user_email: str, user_name: Optional[str] = None, method: str = "email"):
    """
    Call this function when a new user registers
    
    Args:
        user_email: User's email
        user_name: User's name (optional)
        method: Registration method
    """
    try:
        # Send admin notification
        send_new_user_notification(user_email, user_name, method)
        
        # Optionally send welcome email to user
        send_welcome_email(user_email, user_name)
        
        logger.info(f"Notifications sent for new user: {user_email}")
        
    except Exception as e:
        logger.error(f"Failed to send notifications: {e}")
