"""
R2 Uploader - 上传二维码图片到 Cloudflare R2
"""

import os
import uuid
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None


class R2Uploader:
    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        public_domain: str,
    ):
        self.account_id = account_id
        self.bucket_name = bucket_name
        self.public_domain = public_domain.rstrip("/")

        if boto3 is None:
            raise ImportError(
                "boto3 is required for R2 upload. Install: pip install boto3"
            )

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def upload_image(
        self,
        image_data: bytes,
        content_type: str = "image/png",
        custom_filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        上传图片到 R2

        Args:
            image_data: 图片二进制数据
            content_type: MIME 类型
            custom_filename: 自定义文件名（不含扩展名）

        Returns:
            公网访问 URL，失败返回 None
        """
        if custom_filename is None:
            custom_filename = str(uuid.uuid4())

        filename = f"xianyu/{custom_filename}.png"
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=image_data,
                ContentType=content_type,
            )
            public_url = f"{self.public_domain}/{filename}"
            print(f"[R2] 上传成功: {public_url}")
            return public_url
        except ClientError as e:
            print(f"[R2] 上传失败: {e}")
            return None
        except Exception as e:
            print(f"[R2] 上传异常: {e}")
            return None


_global_uploader: Optional[R2Uploader] = None


def get_uploader() -> Optional[R2Uploader]:
    """获取全局 R2 上传器实例"""
    global _global_uploader

    if _global_uploader is not None:
        return _global_uploader

    account_id = os.environ.get("CF_ACCOUNT_ID")
    access_key_id = os.environ.get("CF_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("CF_SECRET_ACCESS_KEY")
    bucket_name = os.environ.get("CF_BUCKET_NAME")
    public_domain = os.environ.get("CF_PUBLIC_DOMAIN")

    if not all(
        [account_id, access_key_id, secret_access_key, bucket_name, public_domain]
    ):
        print("[R2] R2 配置不完整，跳过上传")
        return None

    try:
        _global_uploader = R2Uploader(
            account_id=account_id,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            bucket_name=bucket_name,
            public_domain=public_domain,
        )
        print("[R2] R2 上传器初始化成功")
        return _global_uploader
    except Exception as e:
        print(f"[R2] R2 上传器初始化失败: {e}")
        return None


def upload_qr_code(image_data: bytes, token: str) -> Optional[str]:
    """
    上传二维码图片到 R2

    Args:
        image_data: 二维码图片二进制数据
        token: 用于生成唯一文件名

    Returns:
        公网访问 URL，失败返回 None
    """
    uploader = get_uploader()
    if uploader is None:
        return None

    return uploader.upload_image(
        image_data=image_data,
        custom_filename=f"qr-{token[:16]}",
    )
