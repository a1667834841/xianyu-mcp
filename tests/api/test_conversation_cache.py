from src.api.conversation_cache import ConversationCache
from src.api.types import Conversation, ChatMessage, TextContent


def test_conversation_cache_init():
    cache = ConversationCache()
    assert cache.max_conversations == 20
    assert cache.max_messages_per_conv == 50

    cache_custom = ConversationCache(max_conversations=10, max_messages_per_conv=30)
    assert cache_custom.max_conversations == 10
    assert cache_custom.max_messages_per_conv == 30


def test_conversation_cache_empty():
    cache = ConversationCache()
    conversations = cache.get_conversations()
    assert len(conversations) == 0

    messages = cache.get_messages("test_conv_id")
    assert len(messages) == 0