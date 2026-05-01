from dataclasses import dataclass, field
from typing import Union, Optional, List, Dict, Any


@dataclass
class TextContent:
    type: str = "text"
    text: str = ""


@dataclass
class ImageContent:
    type: str = "image"
    image_url: str = ""
    width: int = 0
    height: int = 0


@dataclass
class AudioContent:
    type: str = "audio"
    audio_url: str = ""
    duration_ms: int = 0


Message = Union[TextContent, ImageContent, AudioContent]


@dataclass
class ChatMessage:
    message_id: str
    conversation_id: str
    sender_id: str
    receiver_id: str
    content: Message
    timestamp: float = 0.0
    is_read: bool = False


@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    user_nick: str
    last_message: Optional[str] = None
    last_message_time: float = 0.0
    unread_count: int = 0
    item_id: Optional[str] = None
