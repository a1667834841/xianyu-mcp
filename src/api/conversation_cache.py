"""对话缓存管理 - 基于 WebSocket 实时消息积累构建对话列表"""

from typing import Dict, List, Optional
from .types import Conversation, ChatMessage


class ConversationCache:
    """对话缓存管理类

    功能：
    - 缓存对话列表（最多 20 个）
    - 缓存每个对话的消息历史（每个对话最多 50 条）
    - 自动管理容量限制，超出时删除最旧数据
    """

    def __init__(self, max_conversations: int = 20, max_messages_per_conv: int = 50):
        self._conversations: Dict[str, Conversation] = {}
        self._messages: Dict[str, List[ChatMessage]] = {}
        self.max_conversations = max_conversations
        self.max_messages_per_conv = max_messages_per_conv

    def update_conversation(self, conv: Conversation) -> None:
        """更新或添加对话"""
        raise NotImplementedError

    def add_message(self, conv_id: str, msg: ChatMessage) -> None:
        """添加消息到对话"""
        raise NotImplementedError

    def get_conversations(self, limit: int = 20) -> List[Conversation]:
        """获取对话列表（按最后消息时间降序排序）"""
        return []

    def get_messages(self, conv_id: str, limit: int = 50) -> List[ChatMessage]:
        """获取对话的消息列表（按时间降序排序）"""
        return []

    def get_conversation_by_user(self, user_id: str) -> Optional[Conversation]:
        """按 user_id 查找对话"""
        return None

    def mark_read(self, conv_id: str) -> None:
        """标记对话为已读"""
        pass

    def clear(self) -> None:
        """清空缓存"""
        pass