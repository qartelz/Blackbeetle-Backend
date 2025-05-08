import pyotp
import hashlib
import base64

class OTPManager:
    @staticmethod
    def generate_secret_key(phone_number):
        """Generate a unique secret key based on the phone number."""
        hash_digest = hashlib.sha256(phone_number.encode()).digest()
        return base64.b32encode(hash_digest).decode()[:32]  # 32 characters for TOTP

    @staticmethod
    def generate_otp(secret_key):
        """Generate a TOTP based on the secret key."""
        totp = pyotp.TOTP(secret_key, interval=300)  # OTP valid for 5 minutes
        return totp.now()

    @staticmethod
    def verify_otp(secret_key, otp):
        """Verify the OTP based on the secret key."""
        totp = pyotp.TOTP(secret_key, interval=300)
        return totp.verify(otp)