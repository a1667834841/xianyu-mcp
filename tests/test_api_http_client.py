import pytest
import hashlib
import json
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.http_client import HttpClient, save_local_auth, load_local_auth_data


class TestHttpClientSign:
    def test_load_local_auth_data_uses_env_root_user_tokens_dir(self, tmp_path, monkeypatch):
        user_root = tmp_path / "users" / "default" / "tokens"
        user_root.mkdir(parents=True)
        (user_root / "auth.json").write_text(
            json.dumps({"cookies": {"unb": "4188939592", "cookie2": "abc"}}),
            encoding="utf-8",
        )
        monkeypatch.delenv("XIANYU_DATA_DIR", raising=False)
        monkeypatch.setenv("XIANYU_DATA_ROOT", str(tmp_path / "users"))
        monkeypatch.setenv("XIANYU_USER_ID", "default")

        data = load_local_auth_data()

        assert data["cookies"] == {"unb": "4188939592", "cookie2": "abc"}

    def test_load_local_auth_data_falls_back_to_legacy_token_file(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "users" / "default" / "tokens"
        data_dir.mkdir(parents=True)
        (data_dir / "token.json").write_text(
            json.dumps(
                {
                    "full_cookie": "unb=4188939592; _m_h5_tk=test_token_123; cookie2=abc",
                    "updated_at": "2026-05-05T00:00:00",
                    "expires_at": "2026-05-06T00:00:00",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.delenv("XIANYU_DATA_DIR", raising=False)
        monkeypatch.setenv("XIANYU_DATA_ROOT", str(tmp_path / "users"))
        monkeypatch.setenv("XIANYU_USER_ID", "default")

        data = load_local_auth_data()

        assert data["cookies"]["unb"] == "4188939592"
        assert data["cookies"]["_m_h5_tk"] == "test_token_123"
        assert data["cookies"]["cookie2"] == "abc"
        assert data["updated_at"] == "2026-05-05 00:00:00"
        assert data["expires_at"] == "2026-05-06 00:00:00"

    def test_init_loads_device_id_from_auth_file(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        (data_dir / "auth.json").write_text(
            json.dumps({"cookies": {"unb": "123"}, "device_id": "web_saved"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        client = HttpClient(cookies=None, device_id="")

        assert client.cookies == {"unb": "123"}
        assert client.device_id == "web_saved"

    def test_init_uses_unb_based_device_id_when_auth_file_has_no_device_id(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        (data_dir / "auth.json").write_text(
            json.dumps({"cookies": {"unb": "4188939592"}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        client = HttpClient(cookies=None, device_id="")

        assert client.cookies == {"unb": "4188939592"}
        assert client.device_id == "web_4188939592"

    def test_httpclient_reads_from_custom_data_dir(self, tmp_path, monkeypatch):
        custom_dir = tmp_path / "custom-tokens"
        custom_dir.mkdir()
        (custom_dir / "auth.json").write_text(
            json.dumps({"cookies": {"unb": "custom-user", "cookie2": "xyz"}, "device_id": "web_custom"}),
            encoding="utf-8",
        )
        monkeypatch.delenv("XIANYU_DATA_DIR", raising=False)
        monkeypatch.delenv("XIANYU_DATA_ROOT", raising=False)

        client = HttpClient(cookies=None, device_id="", data_dir=custom_dir)

        assert client.cookies == {"unb": "custom-user", "cookie2": "xyz"}
        assert client.device_id == "web_custom"

    def test_httpclient_saves_to_custom_data_dir(self, tmp_path, monkeypatch):
        custom_dir = tmp_path / "custom-tokens"
        custom_dir.mkdir()
        monkeypatch.delenv("XIANYU_DATA_DIR", raising=False)
        monkeypatch.delenv("XIANYU_DATA_ROOT", raising=False)

        client = HttpClient(cookies={"unb": "save-user"}, device_id="", data_dir=custom_dir)
        client._save_cookies_to_file()

        saved = json.loads((custom_dir / "auth.json").read_text(encoding="utf-8"))
        assert saved["cookies"]["unb"] == "save-user"

    def test_save_local_auth_preserves_existing_device_id(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        (data_dir / "auth.json").write_text(
            json.dumps({"cookies": {"old": "cookie"}, "device_id": "web_saved"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        save_local_auth({"new": "cookie"})

        saved = json.loads((data_dir / "auth.json").read_text(encoding="utf-8"))
        assert saved["cookies"] == {"new": "cookie"}
        assert saved["device_id"] == "web_saved"

    def test_save_cookies_to_file_persists_current_cookies(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "tokens"
        data_dir.mkdir()
        monkeypatch.setenv("XIANYU_DATA_DIR", str(data_dir))

        client = HttpClient(cookies={"cookie2": "abc", "unb": "123"}, device_id="")

        client._save_cookies_to_file()

        saved = json.loads((data_dir / "auth.json").read_text(encoding="utf-8"))
        assert saved["cookies"] == {"cookie2": "abc", "unb": "123"}

    def test_generate_sign_basic(self):
        client = HttpClient(cookies={}, device_id="test_device")
        token = "test_token"
        timestamp = "1234567890"
        data_str = '{"keyword":"test"}'
        
        sign = client._generate_sign(token, timestamp, data_str)
        
        expected = hashlib.md5(
            f"{token}&{timestamp}&{client.APP_KEY}&{data_str}".encode()
        ).hexdigest()
        assert sign == expected

    def test_extract_token_from_cookie(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "_m_h5_tk=test_token_1234567890; other_cookie=value"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == "test_token"

    def test_extract_token_missing(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "other_cookie=value; session=abc"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == ""

    def test_get_authenticated_user_identity_returns_unb(self):
        client = HttpClient(cookies={"unb": 4188939592, "nick": "测试用户"}, device_id="test_device")

        identity = client.get_authenticated_user_identity()

        assert identity == {"user_id": "4188939592", "username": "4188939592"}

    def test_get_authenticated_user_identity_falls_back_to_unb_when_nick_missing(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")

        identity = client.get_authenticated_user_identity()

        assert identity == {"user_id": "4188939592", "username": "4188939592"}

    def test_get_authenticated_user_identity_falls_back_to_unb_when_nick_empty(self):
        client = HttpClient(cookies={"unb": "4188939592", "nick": ""}, device_id="test_device")

        identity = client.get_authenticated_user_identity()

        assert identity == {"user_id": "4188939592", "username": "4188939592"}

    def test_get_authenticated_user_identity_raises_when_unb_missing(self):
        client = HttpClient(cookies={"nick": "测试用户"}, device_id="test_device")

        with pytest.raises(ValueError, match="authenticated user id"):
            client.get_authenticated_user_identity()

    def test_get_authenticated_user_identity_raises_when_unb_empty(self):
        client = HttpClient(cookies={"unb": "", "nick": "测试用户"}, device_id="test_device")

        with pytest.raises(ValueError, match="authenticated user id"):
            client.get_authenticated_user_identity()

    def test_get_authenticated_user_identity_raises_when_unb_blank(self):
        client = HttpClient(cookies={"unb": "   ", "nick": "测试用户"}, device_id="test_device")

        with pytest.raises(ValueError, match="authenticated user id"):
            client.get_authenticated_user_identity()

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_returns_nick_from_api(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {"ret": ["SUCCESS::调用成功"], "data": {"nick": "真实昵称"}}

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == "真实昵称"

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_returns_empty_when_api_fails(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("network error")
            nickname = await client.fetch_user_nickname()

        assert nickname == ""

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_returns_display_name_from_module_base(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "module": {"base": {"displayName": "小明同学"}},
            },
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == "小明同学"

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_returns_nickname_field(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"nickname": "小红"},
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == "小红"

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_returns_login_nick(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"loginNick": "tb12345"},
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == "tb12345"

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_prefers_display_name_over_nick(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "module": {"base": {"displayName": "显示名"}},
                "nick": "用户名",
            },
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == "显示名"

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_falls_back_to_nick_when_display_name_missing(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"nick": "后备昵称"},
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == "后备昵称"

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_returns_empty_when_all_fields_missing(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"otherField": "irrelevant"},
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == ""

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_strips_whitespace(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"nick": "  昵称有空格  "},
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == "昵称有空格"

    @pytest.mark.asyncio
    async def test_fetch_user_nickname_returns_empty_for_whitespace_only(self):
        client = HttpClient(cookies={"unb": "4188939592"}, device_id="test_device")
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"nick": "   "},
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            nickname = await client.fetch_user_nickname()

        assert nickname == ""


class TestHttpClientSearch:
    @pytest.mark.asyncio
    async def test_search_success(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "123",
                                        "title": "测试商品",
                                        "price": [{"text": "¥100"}],
                                    },
                                    "clickParam": {"args": {"item_id": "123"}},
                                }
                            }
                        }
                    }
                ]
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.search(keyword="iPhone", rows=30)
            
            assert len(result) == 1
            assert result[0]["item_id"] == "123"
            assert result[0]["title"] == "测试商品"

    @pytest.mark.asyncio
    async def test_search_returns_enhanced_metadata_fields(self):
        client = HttpClient(cookies={}, device_id="test_device")

        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "123",
                                        "title": "测试商品",
                                        "price": [{"text": "5"}, {"text": ".40"}],
                                        "userNickName": "卖家A",
                                        "area": "江苏",
                                        "fishTags": {
                                            "r3": {
                                                "tagList": [
                                                    {"data": {"content": "1053人想要"}}
                                                ]
                                            }
                                        },
                                    },
                                    "clickParam": {
                                        "args": {
                                            "item_id": "123",
                                            "publishTime": 1739258714000,
                                        }
                                    },
                                }
                            }
                        }
                    }
                ]
            },
        }

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response

            result = await client.search(keyword="iPhone", rows=30)

        assert len(result) == 1
        assert result[0]["price"] == "5.40"
        assert result[0]["want_cnt"] == 1053
        assert result[0]["publish_time"] == "2025-02-11 15:25:14"
        assert result[0]["seller_nick"] == "卖家A"
        assert result[0]["seller_city"] == "江苏"
        assert result[0]["collect_time"]
        assert result[0]["detail_url"] == "https://www.goofish.com/item?id=123"

    @pytest.mark.asyncio
    async def test_search_session_expired(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["FAIL_SYS_SESSION_EXPIRED::Session 过期"],
            "data": None,
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            with pytest.raises(Exception) as exc_info:
                await client.search(keyword="test", rows=30)
            
            assert "SESSION_EXPIRED" in str(exc_info.value)


class TestHttpClientConversation:
    @pytest.mark.asyncio
    async def test_create_conversation(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"conversationId": "conv_123"},
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.create_conversation(seller_id="user_456", item_id="item_789")
            
            assert result == "conv_123"

    @pytest.mark.asyncio
    async def test_list_conversations(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "conversationList": [
                    {
                        "conversationId": "conv_123",
                        "userId": "user_456",
                        "userNick": "test_user",
                        "lastMessage": "hello",
                        "lastMessageTime": 1700000000000,
                        "unreadCount": 2,
                    }
                ]
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.list_conversations(limit=20, offset=0)
            
            assert len(result) == 1
            assert result[0].conversation_id == "conv_123"
            assert result[0].user_nick == "test_user"


class TestHttpClientPublish:
    @pytest.mark.asyncio
    async def test_publish_keeps_price_values_in_yuan_for_publish_payload(self):
        client = HttpClient(cookies={}, device_id="test_device")

        with (
            patch.object(client, "upload_media", new_callable=AsyncMock) as mock_upload,
            patch.object(client, "get_public_channel", new_callable=AsyncMock) as mock_channel,
            patch.object(client, "get_default_location", new_callable=AsyncMock) as mock_location,
            patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send,
        ):
            mock_upload.return_value = {
                "object": {"pix": "100x200", "url": "https://img.example/test.jpg"}
            }
            mock_channel.return_value = {
                "data": {
                    "categoryPredictResult": {
                        "catId": "1",
                        "catName": "手机",
                        "channelCatId": "2",
                        "tbCatId": "3",
                    }
                }
            }
            mock_location.return_value = {
                "data": {
                    "commonAddresses": [
                        {
                            "area": "鼓楼区",
                            "city": "南京",
                            "divisionId": "320106",
                            "longitude": "118.78",
                            "latitude": "31.92",
                            "poiId": "poi-1",
                            "poi": "测试地址",
                            "prov": "江苏",
                        }
                    ]
                }
            }
            mock_send.return_value = {
                "ret": ["SUCCESS::调用成功"],
                "data": {"itemId": "item-001"},
            }

            await client.publish(
                images_paths=["/tmp/test.jpg"],
                title="测试商品",
                price={"current_price": 88.0, "original_price": 128.0},
                shipping="一口价",
                post_price=12.0,
            )

        _, payload = mock_send.await_args.args
        assert payload["itemPriceDTO"]["priceInCent"] == "88"
        assert payload["itemPriceDTO"]["origPriceInCent"] == "128"
        assert payload["itemPostFeeDTO"]["postPriceInCent"] == "12"

    @pytest.mark.asyncio
    async def test_publish_preserves_decimal_yuan_prices_for_sourcing_flow(self):
        client = HttpClient(cookies={}, device_id="test_device")

        with (
            patch.object(client, "upload_media", new_callable=AsyncMock) as mock_upload,
            patch.object(client, "get_public_channel", new_callable=AsyncMock) as mock_channel,
            patch.object(client, "get_default_location", new_callable=AsyncMock) as mock_location,
            patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send,
        ):
            mock_upload.return_value = {
                "object": {"pix": "100x200", "url": "https://img.example/test.jpg"}
            }
            mock_channel.return_value = {
                "data": {
                    "categoryPredictResult": {
                        "catId": "1",
                        "catName": "手机",
                        "channelCatId": "2",
                        "tbCatId": "3",
                    }
                }
            }
            mock_location.return_value = {
                "data": {
                    "commonAddresses": [
                        {
                            "area": "鼓楼区",
                            "city": "南京",
                            "divisionId": "320106",
                            "longitude": "118.78",
                            "latitude": "31.92",
                            "poiId": "poi-1",
                            "poi": "测试地址",
                            "prov": "江苏",
                        }
                    ]
                }
            }
            mock_send.return_value = {
                "ret": ["SUCCESS::调用成功"],
                "data": {"itemId": "item-002"},
            }

            await client.publish(
                images_paths=["/tmp/test.jpg"],
                title="测试商品",
                price={"current_price": 5.4},
            )

        _, payload = mock_send.await_args.args
        assert payload["itemPriceDTO"]["priceInCent"] == "5.4"

    @pytest.mark.asyncio
    async def test_get_message_history(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "messageList": [
                    {
                        "messageId": "msg_123",
                        "senderId": "user_456",
                        "receiverId": "user_789",
                        "content": {"type": "text", "text": "hello"},
                        "timestamp": 1700000000000,
                    }
                ],
                "hasMore": False,
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.get_message_history(conversation_id="conv_123", limit=50)
            
            assert len(result["messages"]) == 1
            assert result["has_more"] == False


class TestHttpClientAccessToken:
    @pytest.mark.asyncio
    async def test_get_access_token_returns_empty_when_api_has_no_token(self):
        client = HttpClient(cookies={"unb": "4188939592", "_m_h5_tk": "token_123"}, device_id="web_4188939592")

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"ret": ["FAIL_SYS_USER_VALIDATE"], "data": {}}

            token = await client.get_access_token()

        assert token == ""

    @pytest.mark.asyncio
    async def test_handle_captcha_serializes_concurrent_recovery(self):
        client = HttpClient(cookies={"unb": "4188939592", "_m_h5_tk": "token_123"}, device_id="web_4188939592")

        calls = 0

        async def fake_handle(url, max_retries=3):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return True

        with patch("src.api.captcha_handler.CaptchaHandler.handle", new=AsyncMock(side_effect=fake_handle)):

            await asyncio.gather(
                client._handle_captcha("https://example.com/captcha"),
                client._handle_captcha("https://example.com/captcha"),
            )

        assert calls == 1
