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
        """更新或添加对话
        
        自动管理对话数量上限：
        - 如果超出 max_conversations，删除最早活跃的对话
        """
        # Validate input
        if not conv or not conv.conversation_id:
            return
        
        # 更新或添加对话
        self._conversations[conv.conversation_id] = conv
        
        # 检查容量限制
        if len(self._conversations) > self.max_conversations:
            # 找到最早活跃的对话（last_message_time 最小的）
            oldest_conv_id = min(
                self._conversations.keys(),
                key=lambda k: self._conversations[k].last_message_time
            )
            # 删除最早的对话及其消息
            del self._conversations[oldest_conv_id]
            if oldest_conv_id in self._messages:
                del self._messages[oldest_conv_id]

    def add_message(self, conv_id: str, msg: ChatMessage) -> None:
        """添加消息到对话
        
        自动管理消息数量上限：
        - 如果超出 max_messages_per_conv，删除最早的消息
        """
        # 确保 conversation_id 匹配
        if msg.conversation_id != conv_id:
            msg.conversation_id = conv_id
        
        # 如果对话不存在，初始化消息列表
        if conv_id not in self._messages:
            self._messages[conv_id] = []
        
        # 添加消息
        self._messages[conv_id].append(msg)
        
        # 检查容量限制
        if len(self._messages[conv_id]) > self.max_messages_per_conv:
            # 找到最早的消息（timestamp 最小的）
            messages = self._messages[conv_id]
            oldest_idx = min(range(len(messages)), key=lambda i: messages[i].timestamp)
            # 删除最早的消息
            self._messages[conv_id].pop(oldest_idx)

    def get_conversations(self, limit: int = 20) -> List[Conversation]:
        """获取对话列表（按最后消息时间降序排序）"""
        conversations = list(self._conversations.values())
        # 按最后消息时间降序排序（最新的在前）
        conversations.sort(key=lambda c: c.last_message_time, reverse=True)
        return conversations[:limit]

    def get_messages(self, conv_id: str, limit: int = 50) -> List[ChatMessage]:
        """获取对话的消息列表（按时间降序排序）"""
        if conv_id not in self._messages:
            return []
        
        messages = self._messages[conv_id]
        # Use sorted() to avoid mutating the internal list
        return sorted(messages, key=lambda m: m.timestamp, reverse=True)[:limit]

    def get_conversation_by_user(self, user_id: str) -> Optional[Conversation]:
        """按 user_id 查找对话"""
        for conv in self._conversations.values():
            if conv.user_id == user_id:
                return conv
        return None

    def mark_read(self, conv_id: str) -> None:
        """标记对话为已读（清空 unread_count）"""
        if conv_id in self._conversations:
            self._conversations[conv_id].unread_count = 0

    def clear(self) -> None:
        """清空缓存"""
        self._conversations.clear()
        self._messages.clear()
