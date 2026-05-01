import hashlib
import json
import time
import logging
from typing import Dict, Any, Optional, List
import requests

from .types import Conversation, ChatMessage, TextContent, ImageContent

logger = logging.getLogger(__name__)


class HttpClient:
    """闲鱼 HTTP MTOP API 客户端"""
    
    BASE_URL = "https://h5.m.taobao.com"
    APP_KEY = "12574478"
    
    def __init__(self, cookies: Dict[str, str], device_id: str):
        self.cookies = cookies
        self.device_id = device_id
        self.session = requests.Session()
        self.session.cookies.update(cookies)
    
    def _generate_sign(self, token: str, timestamp: str, data_str: str) -> str:
        """生成 MTOP 签名"""
        sign_str = f"{token}&{timestamp}&{self.APP_KEY}&{data_str}"
        return hashlib.md5(sign_str.encode()).hexdigest()
    
    def _extract_token_from_cookie(self, cookie_str: str) -> str:
        """从 Cookie 中提取 Token"""
        if not cookie_str:
            return ""
        for item in cookie_str.split(";"):
            item = item.strip()
            if item.startswith("_m_h5_tk="):
                token_part = item.split("=", 1)[1]
                if "__" in token_part:
                    return token_part.split("__", 1)[0]
                if "_" in token_part:
                    last_underscore = token_part.rfind("_")
                    if last_underscore > 0:
                        return token_part[:last_underscore]
                return token_part
        return ""
    
    async def _send_request(
        self, 
        api: str, 
        data: Dict[str, Any], 
        v: str = "1.0"
    ) -> Dict[str, Any]:
        """发送 MTOP API 请求"""
        cookie_str = self.session.cookies.get_dict()
        cookie_str_full = "; ".join([f"{k}={v}" for k, v in cookie_str.items()])
        
        token = self._extract_token_from_cookie(cookie_str_full)
        timestamp = str(int(time.time() * 1000))
        
        data_str = json.dumps(data, separators=(',', ':'))
        sign = self._generate_sign(token, timestamp, data_str)
        
        params = {
            "jsv": "2.6.1",
            "appKey": self.APP_KEY,
            "t": timestamp,
            "sign": sign,
            "api": api,
            "v": v,
            "dataType": "json",
            "data": data_str,
        }
        
        url = f"{self.BASE_URL}/mtop/{api}/{v}/"
        
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"MTOP API 请求失败：{e}")
            raise
    
    async def search(self, keyword: str, rows: int = 30, **kwargs) -> List[Dict]:
        """搜索商品"""
        api = "mtop.taobao.idle.pc.search/1.0"
        
        data = {
            "keyword": keyword,
            "pageNumber": 1,
            "rowsPerPage": rows,
            "searchReqFromPage": "pcSearch",
        }
        
        if kwargs.get("min_price"):
            data["propValueStr"] = {"price": f"{kwargs['min_price']}-{kwargs.get('max_price', '')}"}
        
        if kwargs.get("sort_field"):
            data["sortField"] = kwargs["sort_field"]
            data["sortValue"] = kwargs.get("sort_order", "DESC")
        
        resp = await self._send_request(api, data)
        
        if resp.get("ret") and "FAIL_SYS_SESSION_EXPIRED" in resp["ret"][0]:
            raise Exception("SESSION_EXPIRED: Session 过期")
        
        result_list = resp.get("data", {}).get("resultList", [])
        items = []
        
        for item_data in result_list:
            try:
                ex_content = item_data["data"]["item"]["main"]["exContent"]
                click_param = item_data["data"]["item"]["main"].get("clickParam", {}).get("args", {})
                
                item_id = ex_content.get("itemId") or click_param.get("item_id")
                if not item_id:
                    continue
                
                price = click_param.get("price") or click_param.get("displayPrice")
                if not price and ex_content.get("price"):
                    price = ex_content["price"][0].get("text", "")
                
                items.append({
                    "item_id": item_id,
                    "title": ex_content.get("title", ""),
                    "price": price or "",
                    "detail_url": f"https://www.goofish.com/item?id={item_id}",
                })
            except (KeyError, IndexError):
                continue
        
        return items
    
    async def get_item_detail(self, item_id: str) -> Dict[str, Any]:
        """获取商品详情"""
        # TODO: 实现详情逻辑
        return {}
    
    async def create_conversation(self, seller_id: str, item_id: str = "") -> str:
        """创建对话"""
        # TODO: 实现创建对话逻辑 (Task 4)
        return ""
    
    async def list_conversations(self, limit: int = 20, offset: int = 0) -> List[Conversation]:
        """获取对话列表"""
        # TODO: 实现获取对话列表逻辑 (Task 4)
        return []
    
    async def get_message_history(
        self, 
        conversation_id: str, 
        limit: int = 50,
        before_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取消息历史"""
        # TODO: 实现获取消息历史逻辑 (Task 4)
        return {"messages": [], "has_more": False}
    
    async def refresh_token(self) -> Dict[str, Any]:
        """刷新 Token"""
        # TODO: 实现刷新逻辑
        return {"success": False}
    
    async def login(self, timeout: int = 300) -> Dict[str, Any]:
        """登录"""
        # TODO: 实现登录逻辑
        return {"success": False}
    
    async def check_session(self) -> Dict[str, Any]:
        """检查会话"""
        # TODO: 实现检查逻辑
        return {"valid": False}
    
    async def publish(self, item_url: str, **kwargs) -> Dict[str, Any]:
        """发布商品"""
        # TODO: 实现发布逻辑
        return {"success": False}
    
    def close(self):
        """关闭会话"""
        self.session.close()
