"""
====================================================================
Email Notification Module for Battery Tester v2.0
INESC-TEC CRAS - Centre for Robotics and Autonomous Systems
====================================================================

This module sends professional, high-priority email notifications when
battery tests complete. Includes INESC-TEC branding and test details.

Author: João Pedro Caldas Ferreira
Last Updated: December 16, 2025
====================================================================
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
import os
from typing import Optional


# ====================================================================
# CONFIGURATION - UPDATE THESE VALUES BEFORE FIRST USE
# ====================================================================
class EmailConfig:
    """Email configuration settings"""

    # SMTP Server Settings
    SMTP_SERVER = "smtp.gmail.com"          # Your email provider's SMTP server
    SMTP_PORT = 587                          # Port (587 for TLS)

    # Email Credentials (REQUIRED)
    SENDER_EMAIL = "joao.mail.bot@gmail.com"     # Your email address
    SENDER_PASSWORD = "zyrp cqky htjz fdco"        # Your app password (NOT regular password!)

    # Recipients
    RECIPIENT_EMAIL = "joao2001ferreira@gmail.com"  # Who receives the notifications

    # Banner Image (absolute path based on script location)
    BANNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inesctec_banner.png")

    # Enable/Disable Notifications
    ENABLE_NOTIFICATIONS = True  # Set to False to disable email sending


# ====================================================================
# MAIN EMAIL FUNCTION
# ====================================================================
def send_completion_email(
    test_name: str,
    duration: float,
    filename: str,
    voltage: Optional[float] = None,
    current: Optional[float] = None,
    temperature: Optional[float] = None,
    outcome: str = "completed",
    stop_reason: Optional[str] = None
) -> bool:
    """
    Send a high-priority test completion notification email.

    This function is called automatically when a battery test completes.
    It sends a professionally formatted email with test details and 
    final measurements.

    Args:
        test_name (str): Name of the test (e.g., "Discharge", "Pulsed Charge")
        duration (float): Test duration in seconds
        filename (str): Name of the saved data file (with or without .csv)
        voltage (float, optional): Final voltage reading in volts
        current (float, optional): Final current reading in amperes
        temperature (float, optional): Final temperature reading in Celsius

    Returns:
        bool: True if email sent successfully, False otherwise

    Example:
        send_completion_email(
            test_name="Discharge",
            duration=125.5,
            filename="battery_test_20251216.csv",
            voltage=2.85,
            current=0.45,
            temperature=24.3
        )
    """

    # Check if notifications are enabled
    if not EmailConfig.ENABLE_NOTIFICATIONS:
        print("[Email] Notifications disabled in configuration")
        return False

    try:
        # ============================================================
        # Format Test Data
        # ============================================================

        # Format duration for better readability
        if duration >= 3600:
            duration_str = f"{duration/3600:.2f} hours ({duration:.1f}s)"
        elif duration >= 60:
            duration_str = f"{duration/60:.2f} minutes ({duration:.1f}s)"
        else:
            duration_str = f"{duration:.2f} seconds"

        outcome_label = (outcome or "completed").replace("_", " ").title()
        stop_reason = stop_reason or outcome_label

        # Ensure filename has .csv extension
        if filename != "None" and not filename.endswith('.csv'):
            filename = f"{filename}.csv"

        # Get current date and time
        test_date = datetime.now().strftime("%B %d, %Y")
        test_time = datetime.now().strftime("%H:%M:%S")

        # ============================================================
        # Build Additional Measurements Section (if provided)
        # ============================================================
        additional_data = ""
        if any([voltage is not None, current is not None, temperature is not None]):
            additional_data = """
                            <tr>
                                <td colspan="2" style="padding: 16px 0 8px 0;">
                                    <div style="border-top: 2px solid #3b82f6; padding-top: 16px;">
                                        <strong style="color: #1e40af; font-size: 14px;">Final Measurements</strong>
                                    </div>
                                </td>
                            </tr>"""

            if voltage is not None:
                additional_data += f"""
                            <tr>
                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                    Voltage
                                </td>
                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                    {voltage:.3f} V
                                </td>
                            </tr>"""

            if current is not None:
                additional_data += f"""
                            <tr>
                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                    Current
                                </td>
                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                    {current:.3f} A
                                </td>
                            </tr>"""

            if temperature is not None:
                additional_data += f"""
                            <tr>
                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0;">
                                    Temperature
                                </td>
                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0;">
                                    {temperature:.2f} °C
                                </td>
                            </tr>"""

        # ============================================================
        # Create Email Message
        # ============================================================
        msg = MIMEMultipart('related')
        msg['Subject'] = f'Battery Test {outcome_label} - {test_name}'
        msg['From'] = EmailConfig.SENDER_EMAIL
        msg['To'] = EmailConfig.RECIPIENT_EMAIL

        # Set HIGH PRIORITY headers
        msg['X-Priority'] = '1'                    # 1=Highest priority
        msg['X-MSMail-Priority'] = 'High'          # For Microsoft Outlook
        msg['Importance'] = 'High'                 # Standard importance header

        # ============================================================
        # HTML Email Content
        # ============================================================
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f0f4f8; font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f0f4f8;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <!-- Main container (600px width for universal compatibility) -->
                <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); overflow: hidden;">
                    
                    <tr>
                        <td style="padding: 0; line-height: 0;">
                            <div style="background-image: url('cid:banner_image'); background-size: 100% auto; background-position: top center; background-repeat: no-repeat; height: 180px; border-radius: 8px 8px 0 0; display: flex; align-items: flex-end;">
                                <h1 style="margin: 0; padding: 110px 0px 0px 20px; color: #ffffff; font-size: 25px; font-weight: 700; letter-spacing: -0.5px; text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);">
                                    Test {outcome_label}
                                </h1>
                            </div>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="padding: 40px 40px 30px 40px;">

                            <!-- Test Details Card -->
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 28px 0; border: 2px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
                                <tr>
                                    <td style="background-color: #008cbe; padding: 16px 24px;">
                                        <h2 style="margin: 0; color: #ffffff; font-size: 18px; font-weight: 600;">
                                            <span style="font-size: 24px; margin-right: 10px;">⚡</span>
                                            Test Information
                                        </h2>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f9fafb; padding: 24px;">
                                        <table width="100%" cellpadding="8" cellspacing="0" border="0">
                                            <tr>
                                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    Test Type
                                                </td>
                                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    {test_name}
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    Duration
                                                </td>
                                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    {duration_str}
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    Outcome
                                                </td>
                                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    {outcome_label}
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    Stop Reason
                                                </td>
                                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    {stop_reason}
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    Data File
                                                </td>
                                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    <code style="background-color: #e0e7ff; color: #1e40af; padding: 4px 8px; border-radius: 4px; font-size: 13px;">{filename}</code>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    Completion Date
                                                </td>
                                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    {test_date}
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="width: 40%; color: #6b7280; font-size: 14px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    Completion Time
                                                </td>
                                                <td style="color: #1f2937; font-size: 14px; font-weight: 500; padding: 10px 0; border-bottom: 1px solid #e5e7eb;">
                                                    {test_time} WET
                                                </td>
                                            </tr>
                                            {additional_data}
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #008cbe; padding: 24px 40px;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="text-align: center;">
                                        <p style="margin: 0; color: #bfdbfe; font-size: 12px; line-height: 1.5;">
                                            Automated notification from Battery Tester v2.0<br>
                                            Developed for CRAS @ INESC Technology and Science
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>

                <!-- Legal Footer -->
                <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; margin-top: 20px;">
                    <tr>
                        <td style="text-align: center; padding: 0 20px;">
                            <p style="margin: 0; color: #9ca3af; font-size: 11px; line-height: 1.5;">
                                Please do not reply to this automated email.
                            </p>
                        </td>
                    </tr>
                </table>

            </td>
        </tr>
    </table>
</body>
</html>
"""

        # ============================================================
        # Attach HTML Content
        # ============================================================
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)

        # ============================================================
        # Attach INESC-TEC Banner Image
        # ============================================================
        if os.path.exists(EmailConfig.BANNER_PATH):
            with open(EmailConfig.BANNER_PATH, 'rb') as img_file:
                img_data = img_file.read()
                image = MIMEImage(img_data)
                image.add_header('Content-ID', '<banner_image>')
                image.add_header('Content-Disposition', 'inline', filename='inesctec_banner.png')
                msg.attach(image)
        else:
            print(f"[Email] Warning: Banner image not found at {EmailConfig.BANNER_PATH}")

        # ============================================================
        # Send Email via SMTP
        # ============================================================
        server = smtplib.SMTP(EmailConfig.SMTP_SERVER, EmailConfig.SMTP_PORT)
        server.starttls()
        server.login(EmailConfig.SENDER_EMAIL, EmailConfig.SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        print(f"[Email] ✓ High-priority notification sent to {EmailConfig.RECIPIENT_EMAIL}")
        print(f"[Email]   Test: {test_name} | Duration: {duration_str} | File: {filename}")
        return True

    except Exception as e:
        print(f"[Email] ✗ Failed to send notification: {str(e)}")
        return False


# ====================================================================
# WARNING EMAIL FUNCTION
# ====================================================================

def send_warning_email(
    test_name: str,
    temperature: float,
    filename: str,
    voltage: Optional[float] = None,
    current: Optional[float] = None
) -> bool:
    """Send a high-temperature warning email."""
    if not EmailConfig.ENABLE_NOTIFICATIONS:
        print("[Email] Notifications disabled in configuration")
        return False

    try:
        # Ensure filename has .csv extension
        if not filename.endswith('.csv'):
            filename = f"{filename}.csv"

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Battery Temperature Warning - {temperature:.2f} °C"
        msg['From'] = EmailConfig.SENDER_EMAIL
        msg['To'] = EmailConfig.RECIPIENT_EMAIL
        msg['X-Priority'] = '1'
        msg['X-MSMail-Priority'] = 'High'
        msg['Importance'] = 'High'

        voltage_text = f"{voltage:.3f} V" if voltage is not None else "N/A"
        current_text = f"{current:.3f} A" if current is not None else "N/A"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; background-color: #f8fafc; padding: 24px;">
    <div style="max-width: 560px; background: #ffffff; border: 1px solid #e5e7eb; padding: 20px;">
        <h2 style="color: #b91c1c; margin-top: 0;">Temperature Warning</h2>
        <p style="color: #111827;">The battery temperature reached <strong>{temperature:.2f} °C</strong>.</p>
        <p style="color: #111827;">Charging/discharging has been disabled. Measurements continue.</p>
        <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 16px 0;" />
        <p style="color: #374151; margin: 0;">
            Test: <strong>{test_name}</strong><br />
            File: <strong>{filename}</strong><br />
            Voltage: <strong>{voltage_text}</strong><br />
            Current: <strong>{current_text}</strong>
        </p>
    </div>
</body>
</html>
"""

        msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP(EmailConfig.SMTP_SERVER, EmailConfig.SMTP_PORT) as server:
            server.starttls()
            server.login(EmailConfig.SENDER_EMAIL, EmailConfig.SENDER_PASSWORD)
            server.send_message(msg)

        print("[Email] Warning email sent")
        return True

    except Exception as exc:
        print(f"[Email] Failed to send warning email: {exc}")
        return False


# ====================================================================
# TEST FUNCTION (for standalone testing)
# ====================================================================
if __name__ == "__main__":
    print("="*70)
    print("Battery Tester Email Notification - Test Mode")
    print("="*70)
    print()

    # Example test email
    success = send_completion_email(
        test_name="Discharge",
        duration=125.5,
        filename="battery_test_20251216.csv",
        voltage=2.85,
        current=0.45,
        temperature=24.3
    )

    if success:
        print()
        print("✓ Test email sent successfully!")
        print(f"  Check inbox: {EmailConfig.RECIPIENT_EMAIL}")
    else:
        print()
        print("✗ Test email failed. Check configuration.")

    # Example warning email
    success = send_warning_email(
        test_name="Discharge",
        temperature=75.3,
        filename="battery_test_20251216.csv",
        voltage=2.85,
        current=0.45
    )

    if success:
        print()
        print("✓ Warning email sent successfully!")
        print(f"  Check inbox: {EmailConfig.RECIPIENT_EMAIL}")
    else:
        print()
        print("✗ Warning email failed. Check configuration.")
