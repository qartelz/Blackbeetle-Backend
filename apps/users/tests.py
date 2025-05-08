from django.test import TestCase, RequestFactory
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

class LoginViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            phone_number="1234567890",
            password="testpassword"
        )

    def test_successful_login(self):
        response = self.client.post('/api/login/', {
            'phone_number': '1234567890',
            'password': 'testpassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_invalid_credentials(self):
        response = self.client.post('/api/login/', {
            'phone_number': '1234567890',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn('error', response.data)

    def test_rate_limiting(self):
        for _ in range(6):
            response = self.client.post('/api/login/', {
                'phone_number': '1234567890',
                'password': 'wrongpassword'
            })
        self.assertEqual(response.status_code, 429)