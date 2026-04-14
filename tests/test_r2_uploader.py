from src.utils.r2_uploader import R2Uploader, upload_qr_code


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


def test_upload_image_bytes_uses_key_prefix_and_custom_filename():
    uploader = R2Uploader.__new__(R2Uploader)
    uploader.bucket_name = "test-bucket"
    uploader.public_domain = "https://cdn.example.com"
    uploader.s3_client = FakeS3Client()

    public_url = uploader.upload_image_bytes(
        b"image-bytes",
        content_type="image/webp",
        key_prefix="xianyu/debug",
        custom_filename="debug-image",
    )

    assert public_url == "https://cdn.example.com/xianyu/debug/debug-image.png"
    assert uploader.s3_client.calls == [
        {
            "Bucket": "test-bucket",
            "Key": "xianyu/debug/debug-image.png",
            "Body": b"image-bytes",
            "ContentType": "image/webp",
        }
    ]


def test_upload_qr_code_delegates_to_upload_image_bytes(monkeypatch):
    calls = []

    class FakeUploader:
        def upload_image_bytes(self, image_data, **kwargs):
            calls.append((image_data, kwargs))
            return "https://cdn.example.com/xianyu/qr/qr-1234567890abcdef.png"

    monkeypatch.setattr("src.utils.r2_uploader.get_uploader", lambda: FakeUploader())

    public_url = upload_qr_code(b"qr-bytes", "1234567890abcdefghijklmn")

    assert public_url == "https://cdn.example.com/xianyu/qr/qr-1234567890abcdef.png"
    assert calls == [
        (
            b"qr-bytes",
            {
                "content_type": "image/png",
                "key_prefix": "xianyu/qr",
                "custom_filename": "qr-1234567890abcdef",
            },
        )
    ]
