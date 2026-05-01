import pytest
import hashlib
from src.api.http_client import HttpClient


class TestHttpClientSign:
    def test_generate_sign_basic(self):
        client = HttpClient(cookies={}, device_id="test_device")
        token = "test_token"
        timestamp = "1234567890"
        data_str = '{"keyword":"test"}'
        
        sign = client._generate_sign(token, timestamp, data_str)
        
        expected = hashlib.md5(
            f"{token}&{timestamp}&{client.APP_KEY}&{data_str}".encode()
        ).hexdigest()
        assert sign == expected

    def test_extract_token_from_cookie(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "_m_h5_tk=test_token_1234567890; other_cookie=value"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == "test_token"

    def test_extract_token_missing(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "other_cookie=value; session=abc"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == ""
