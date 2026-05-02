"""消息编码/解码模块"""
import base64
import json
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel


class TextContent(BaseModel):
    type: str = "text"
    text: str


class ImageContent(BaseModel):
    type: str = "image"
    image_url: str
    width: int = 0
    height: int = 0


class MessageSegment(BaseModel):
    """消息段"""
    content: TextContent | ImageContent


def encode_text(text: str) -> Tuple[Dict[str, Any], int]:
    """编码文本消息"""
    return {
        "contentType": 1,
        "text": {"text": text},
    }, 1


def encode_image(image_url: str, width: int = 100, height: int = 100) -> Tuple[Dict[str, Any], int]:
    """编码图片消息"""
    return {
        "contentType": 2,
        "image": {
            "pics": [
                {
                    "type": 0,
                    "url": image_url,
                    "width": width,
                    "height": height,
                }
            ]
        },
    }, 2


def encode_message(content: str, image_url: str = "") -> Tuple[Dict[str, Any], int]:
    """编码消息（文本或图片）"""
    if image_url:
        return encode_image(image_url)
    return encode_text(content)


def encode_custom_message(content: str, image_url: str = "") -> str:
    """编码为 custom 格式（base64）"""
    payload, custom_type = encode_message(content, image_url)
    # 改为包装为数组，匹配 decode_message 的期望
    return base64.b64encode(json.dumps([payload]).encode("utf-8")).decode("utf-8")


def decode_message(data: Dict[str, Any]) -> List[MessageSegment]:
    """解码消息"""
    content_type = data.get("contentType", 0)
    segments = []
    
    if content_type == 1:  # 文本
        text = data.get("text", {}).get("text", "")
        if text:
            segments.append(MessageSegment(content=TextContent(text=text)))
    
    elif content_type == 2:  # 图片
        pics = data.get("image", {}).get("pics", [])
        for pic in pics:
            segments.append(MessageSegment(
                content=ImageContent(
                    image_url=pic.get("url", ""),
                    width=pic.get("width", 0),
                    height=pic.get("height", 0),
                )
            ))
    
    elif content_type == 101:  # 自定义/富文本
        custom_data = data.get("custom", {}).get("data", "")
        if custom_data:
            try:
                decoded = base64.b64decode(custom_data).decode("utf-8")
                for item in json.loads(decoded):
                    if item.get("type") == "text":
                        segments.append(MessageSegment(content=TextContent(text=item.get("text", ""))))
                    elif item.get("type") == "image":
                        segments.append(MessageSegment(content=ImageContent(
                            image_url=item.get("image_url", ""),
                            width=item.get("width", 0),
                            height=item.get("height", 0),
                        )))
            except Exception:
                pass
    
    return segments