with open(r"d:\DACS2\backend\app\api\auth_routes.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

replacement = """    try:
        send_otp(contact, item.channel, code)
    except OTPDeliveryError as exc:
        with get_db() as connection:
            connection.execute(
                "UPDATE auth_otps SET consumed_at = ? WHERE id = ?",
                (int(time.time()), otp_id),
            )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    is_simulated = (
        item.channel == "email"
        and not all((settings.SMTP_HOST, settings.SMTP_FROM_EMAIL))
    ) or (
        item.channel == "phone"
        and not all(
            (
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
                settings.TWILIO_FROM_NUMBER,
            )
        )
    )
    if is_simulated:
        return {
            "message": f"Chế độ thử nghiệm (không cần SMTP): Mã OTP của bạn là {code}",
            "dev_otp": code,
        }

    return {"message": "Mã xác minh đã được gửi."}
"""

new_lines = lines[:219] + [replacement + "\n"] + lines[231:]

with open(r"d:\DACS2\backend\app\api\auth_routes.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Updated auth_routes.py successfully by line replacement!")
