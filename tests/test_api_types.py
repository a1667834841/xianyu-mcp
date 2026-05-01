import pytest
from src.api.types import TextContent, ImageContent, AudioContent, Message, Conversation

class TestTextContent:
    def test_creation(self):
        msg = TextContent(type="text", text="hello")
        assert msg.type == "text"
        assert msg.text == "hello"

    def test_default_values(self):
        msg = TextContent()
        assert msg.type == "text"
        assert msg.text == ""


class TestImageContent:
    def test_creation(self):
        img = ImageContent(type="image", image_url="http://example.com/img.jpg", width=100, height=200)
        assert img.type == "image"
        assert img.image_url == "http://example.com/img.jpg"
        assert img.width == 100
        assert img.height == 200


class TestConversation:
    def test_creation(self):
        conv = Conversation(
            conversation_id="conv_123",
            user_id="user_456",
            user_nick="test_user",
            last_message="hello",
            last_message_time=1700000000.0,
            unread_count=2,
            item_id="item_789"
        )
        assert conv.conversation_id == "conv_123"
        assert conv.unread_count == 2
        assert conv.item_id == "item_789"

    def test_optional_fields(self):
        conv = Conversation(
            conversation_id="conv_123",
            user_id="user_456",
            user_nick="test_user"
        )
        assert conv.last_message is None
        assert conv.item_id is None
