from django.test import TestCase

from apps.accounts import otp as otp_service
from apps.accounts.models import User


class OTPFlowTests(TestCase):
    def test_verify_creates_user_on_first_login(self):
        phone = "+9779800000000"
        request = otp_service.request_otp(phone)
        user = otp_service.verify_otp(phone, request.code)
        self.assertTrue(User.objects.filter(phone_number=phone).exists())
        self.assertTrue(user.is_phone_verified)

    def test_wrong_code_raises(self):
        phone = "+9779800000001"
        otp_service.request_otp(phone)
        with self.assertRaises(otp_service.OTPError):
            otp_service.verify_otp(phone, "000000")
