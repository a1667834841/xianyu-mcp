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


def test_update_conversation_basic():
    """测试基本对话更新"""
    cache = ConversationCache(max_conversations=3)

    conv1 = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="消息1",
        last_message_time=1000.0,
        unread_count=1
    )

    cache.update_conversation(conv1)
    conversations = cache.get_conversations()
    assert len(conversations) == 1
    assert conversations[0].conversation_id == "conv1"


def test_update_conversation_capacity_limit():
    """测试对话容量限制（超出时删除最早活跃的对话）"""
    cache = ConversationCache(max_conversations=3)

    # 添加 3 个对话
    for i in range(3):
        conv = Conversation(
            conversation_id=f"conv{i}",
            user_id=f"user{i}",
            user_nick=f"用户{i}",
            last_message=f"消息{i}",
            last_message_time=1000.0 + i,  # 时间递增
            unread_count=0
        )
        cache.update_conversation(conv)

    # 验证有 3 个对话
    conversations = cache.get_conversations()
    assert len(conversations) == 3

    # 添加第 4 个对话（应该删除最早的 conv0）
    conv4 = Conversation(
        conversation_id="conv4",
        user_id="user4",
        user_nick="用户4",
        last_message="消息4",
        last_message_time=1004.0,
        unread_count=0
    )
    cache.update_conversation(conv4)

    conversations = cache.get_conversations()
    assert len(conversations) == 3
    # 验证 conv0 已被删除
    conv_ids = [c.conversation_id for c in conversations]
    assert "conv0" not in conv_ids
    assert "conv4" in conv_ids


def test_update_conversation_duplicate():
    """测试重复对话更新"""
    cache = ConversationCache()

    conv1 = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="旧消息",
        last_message_time=1000.0,
        unread_count=1
    )

    cache.update_conversation(conv1)

    # 更新同一对话
    conv1_updated = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="新消息",
        last_message_time=2000.0,
        unread_count=2
    )

    cache.update_conversation(conv1_updated)

    conversations = cache.get_conversations()
    assert len(conversations) == 1
    assert conversations[0].last_message == "新消息"
    assert conversations[0].last_message_time == 2000.0


def test_update_conversation_invalid():
    """测试无效对话不会添加到缓存"""
    cache = ConversationCache()
    
    # 测试空 conversation_id
    conv_invalid = Conversation(
        conversation_id="",
        user_id="user1",
        user_nick="用户1",
        last_message="消息",
        last_message_time=1000.0,
        unread_count=0
    )
    
    cache.update_conversation(conv_invalid)
    assert len(cache.get_conversations()) == 0


def test_add_message_basic():
    """测试基本消息添加"""
    cache = ConversationCache()
    
    # 先添加对话
    conv = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="",
        last_message_time=0.0,
        unread_count=0
    )
    cache.update_conversation(conv)
    
    # 添加消息
    msg1 = ChatMessage(
        message_id="msg1",
        conversation_id="conv1",
        sender_id="user1",
        receiver_id="user2",
        content=TextContent(type="text", text="你好"),
        timestamp=1000.0
    )
    
    cache.add_message("conv1", msg1)
    
    messages = cache.get_messages("conv1")
    assert len(messages) == 1
    assert messages[0].message_id == "msg1"


def test_add_message_capacity_limit():
    """测试消息容量限制（超出时删除最早的消息）"""
    cache = ConversationCache(max_messages_per_conv=3)
    
    # 添加对话
    conv = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="",
        last_message_time=0.0,
        unread_count=0
    )
    cache.update_conversation(conv)
    
    # 添加 3 条消息
    for i in range(3):
        msg = ChatMessage(
            message_id=f"msg{i}",
            conversation_id="conv1",
            sender_id="user1",
            receiver_id="user2",
            content=TextContent(type="text", text=f"消息{i}"),
            timestamp=1000.0 + i
        )
        cache.add_message("conv1", msg)
    
    # 验证有 3 条消息
    messages = cache.get_messages("conv1")
    assert len(messages) == 3
    
    # 添加第 4 条消息（应该删除最早的 msg0）
    msg4 = ChatMessage(
        message_id="msg4",
        conversation_id="conv1",
        sender_id="user1",
        receiver_id="user2",
        content=TextContent(type="text", text="消息4"),
        timestamp=1004.0
    )
    cache.add_message("conv1", msg4)
    
    messages = cache.get_messages("conv1")
    assert len(messages) == 3
    # 验证 msg0 已被删除
    msg_ids = [m.message_id for m in messages]
    assert "msg0" not in msg_ids
    assert "msg4" in msg_ids


def test_add_message_without_conversation():
    """测试在不存在对话时添加消息（消息仍然被存储）"""
    cache = ConversationCache()
    
    # 直接添加消息（无对应对话）
    msg = ChatMessage(
        message_id="msg1",
        conversation_id="conv_new",
        sender_id="user_new",
        receiver_id="user_me",
        content=TextContent(type="text", text="测试"),
        timestamp=1000.0
    )
    
    cache.add_message("conv_new", msg)
    
    # 验证消息已添加
    messages = cache.get_messages("conv_new")
    assert len(messages) == 1


def test_get_conversation_by_user():
    """测试按 user_id 查找对话"""
    cache = ConversationCache()
    
    conv1 = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="消息1",
        last_message_time=1000.0,
        unread_count=0
    )
    
    cache.update_conversation(conv1)
    
    # 查找存在的对话
    found_conv = cache.get_conversation_by_user("user1")
    assert found_conv is not None
    assert found_conv.conversation_id == "conv1"
    
    # 查找不存在的对话
    not_found = cache.get_conversation_by_user("user_unknown")
    assert not_found is None


def test_mark_read():
    """测试标记对话为已读"""
    cache = ConversationCache()
    
    conv1 = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="消息1",
        last_message_time=1000.0,
        unread_count=5
    )
    
    cache.update_conversation(conv1)
    
    # 标记为已读
    cache.mark_read("conv1")
    
    conversations = cache.get_conversations()
    assert conversations[0].unread_count == 0


def test_clear():
    """测试清空缓存"""
    cache = ConversationCache()
    
    # 添加对话和消息
    conv = Conversation(
        conversation_id="conv1",
        user_id="user1",
        user_nick="用户1",
        last_message="消息1",
        last_message_time=1000.0,
        unread_count=0
    )
    cache.update_conversation(conv)
    
    msg = ChatMessage(
        message_id="msg1",
        conversation_id="conv1",
        sender_id="user1",
        receiver_id="user2",
        content=TextContent(type="text", text="你好"),
        timestamp=1000.0
    )
    cache.add_message("conv1", msg)
    
    # 验证缓存有数据
    assert len(cache.get_conversations()) == 1
    assert len(cache.get_messages("conv1")) == 1
    
    # 清空缓存
    cache.clear()
    
    # 验证缓存已清空
    assert len(cache.get_conversations()) == 0
    assert len(cache.get_messages("conv1")) == 0
