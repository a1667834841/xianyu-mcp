from typing import Dict, List, Optional
from .types import Conversation, ChatMessage


class ConversationCache:
    
    def __init__(self, max_conversations: int = 20, max_messages_per_conv: int = 50):
        self._conversations: Dict[str, Conversation] = {}
        self._messages: Dict[str, List[ChatMessage]] = {}
        self.max_conversations = max_conversations
        self.max_messages_per_conv = max_messages_per_conv
    
    def update_conversation(self, conv: Conversation) -> None:
        raise NotImplementedError
    
    def add_message(self, conv_id: str, msg: ChatMessage) -> None:
        raise NotImplementedError
    
    def get_conversations(self, limit: int = 20) -> List[Conversation]:
        return []
    
    def get_messages(self, conv_id: str, limit: int = 50) -> List[ChatMessage]:
        return []
    
    def get_conversation_by_user(self, user_id: str) -> Optional[Conversation]:
        return None
    
    def mark_read(self, conv_id: str) -> None:
        pass
    
    def clear(self) -> None:
        pass