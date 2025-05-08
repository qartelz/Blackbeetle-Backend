from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
import pandas as pd
import io
from .models import Company

class CompanyCSVUploadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.upload_url = reverse('company-csv-upload')
        self.list_url = reverse('company-list')

    def create_csv_file(self, data):
        df = pd.DataFrame(data)
        csv_file = io.StringIO()
        df.to_csv(csv_file, index=False)
        csv_file.seek(0)
        return csv_file

    def test_valid_csv_upload(self):
        data = {
            'tokenId': [114064],
            'exchange': ['NFO'],
            'tradingSymbol': ['MUTHOOTFIN27FEB25C2200'],
            'scriptName': ['MUTHOOTFIN'],
            'expiryDate': ['27-FEB-2025'],
            'displayName': ['MUTHOOTFIN 27 FEB CE 2200']
        }
        
        csv_file = self.create_csv_file(data)
        response = self.client.post(self.upload_url, {'csv_file': csv_file}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('task_id', response.data)

    def test_invalid_file_type(self):
        response = self.client.post(self.upload_url, {'csv_file': 'not_a_csv_file.txt'}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_company_list(self):
        Company.objects.create(
            token_id=114064,
            exchange='NFO',
            trading_symbol='MUTHOOTFIN27FEB25C2200',
            script_name='MUTHOOTFIN',
            expiry_date='2025-02-27',
            display_name='MUTHOOTFIN 27 FEB CE 2200'
        )

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

