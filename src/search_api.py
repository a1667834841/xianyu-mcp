from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from .core import SearchItem, SearchOutcome, SearchParams


class PageApiSearchError(RuntimeError):
    pass


@dataclass
class PageApiResult:
    keyword: str
    page: int
    items: List[SearchItem]


class PageApiSearchClient:
    engine_name = "page_api"

    def __init__(
        self,
        page,
        ensure_page_ready: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self.page = page
        self.ensure_page_ready = ensure_page_ready
        self._bridge_ready = False

    async def _ensure_bridge(self):
        if self._bridge_ready:
            return
        await self.page.evaluate(
            """
            () => {
              if (window.__XY_SEARCH_FETCH__) {
                return;
              }
              const getToken = () => {
                const match = document.cookie.match(/(?:^|; )_m_h5_tk=([^;]+)/);
                if (!match) {
                  throw new Error('missing _m_h5_tk');
                }
                return decodeURIComponent(match[1]).split('_')[0];
              };

              const md5 = (function() {
                function safeAdd(x, y) {
                  var lsw = (x & 0xffff) + (y & 0xffff);
                  var msw = (x >> 16) + (y >> 16) + (lsw >> 16);
                  return (msw << 16) | (lsw & 0xffff);
                }
                function bitRotateLeft(num, cnt) {
                  return (num << cnt) | (num >>> (32 - cnt));
                }
                function md5cmn(q, a, b, x, s, t) {
                  return safeAdd(bitRotateLeft(safeAdd(safeAdd(a, q), safeAdd(x, t)), s), b);
                }
                function md5ff(a, b, c, d, x, s, t) {
                  return md5cmn((b & c) | ((~b) & d), a, b, x, s, t);
                }
                function md5gg(a, b, c, d, x, s, t) {
                  return md5cmn((b & d) | (c & (~d)), a, b, x, s, t);
                }
                function md5hh(a, b, c, d, x, s, t) {
                  return md5cmn(b ^ c ^ d, a, b, x, s, t);
                }
                function md5ii(a, b, c, d, x, s, t) {
                  return md5cmn(c ^ (b | (~d)), a, b, x, s, t);
                }
                function binlMD5(x, len) {
                  x[len >> 5] |= 0x80 << (len % 32);
                  x[(((len + 64) >>> 9) << 4) + 14] = len;
                  var a = 1732584193, b = -271733879, c = -1732584194, d = 271733878;
                  for (var i = 0; i < x.length; i += 16) {
                    var olda = a, oldb = b, oldc = c, oldd = d;
                    a = md5ff(a, b, c, d, x[i], 7, -680876936);
                    d = md5ff(d, a, b, c, x[i + 1], 12, -389564586);
                    c = md5ff(c, d, a, b, x[i + 2], 17, 606105819);
                    b = md5ff(b, c, d, a, x[i + 3], 22, -1044525330);
                    a = md5ff(a, b, c, d, x[i + 4], 7, -176418897);
                    d = md5ff(d, a, b, c, x[i + 5], 12, 1200080426);
                    c = md5ff(c, d, a, b, x[i + 6], 17, -1473231341);
                    b = md5ff(b, c, d, a, x[i + 7], 22, -45705983);
                    a = md5ff(a, b, c, d, x[i + 8], 7, 1770035416);
                    d = md5ff(d, a, b, c, x[i + 9], 12, -1958414417);
                    c = md5ff(c, d, a, b, x[i + 10], 17, -42063);
                    b = md5ff(b, c, d, a, x[i + 11], 22, -1990404162);
                    a = md5ff(a, b, c, d, x[i + 12], 7, 1804603682);
                    d = md5ff(d, a, b, c, x[i + 13], 12, -40341101);
                    c = md5ff(c, d, a, b, x[i + 14], 17, -1502002290);
                    b = md5ff(b, c, d, a, x[i + 15], 22, 1236535329);
                    a = md5gg(a, b, c, d, x[i + 1], 5, -165796510);
                    d = md5gg(d, a, b, c, x[i + 6], 9, -1069501632);
                    c = md5gg(c, d, a, b, x[i + 11], 14, 643717713);
                    b = md5gg(b, c, d, a, x[i], 20, -373897302);
                    a = md5gg(a, b, c, d, x[i + 5], 5, -701558691);
                    d = md5gg(d, a, b, c, x[i + 10], 9, 38016083);
                    c = md5gg(c, d, a, b, x[i + 15], 14, -660478335);
                    b = md5gg(b, c, d, a, x[i + 4], 20, -405537848);
                    a = md5gg(a, b, c, d, x[i + 9], 5, 568446438);
                    d = md5gg(d, a, b, c, x[i + 14], 9, -1019803690);
                    c = md5gg(c, d, a, b, x[i + 3], 14, -187363961);
                    b = md5gg(b, c, d, a, x[i + 8], 20, 1163531501);
                    a = md5gg(a, b, c, d, x[i + 13], 5, -1444681467);
                    d = md5gg(d, a, b, c, x[i + 2], 9, -51403784);
                    c = md5gg(c, d, a, b, x[i + 7], 14, 1735328473);
                    b = md5gg(b, c, d, a, x[i + 12], 20, -1926607734);
                    a = md5hh(a, b, c, d, x[i + 5], 4, -378558);
                    d = md5hh(d, a, b, c, x[i + 8], 11, -2022574463);
                    c = md5hh(c, d, a, b, x[i + 11], 16, 1839030562);
                    b = md5hh(b, c, d, a, x[i + 14], 23, -35309556);
                    a = md5hh(a, b, c, d, x[i + 1], 4, -1530992060);
                    d = md5hh(d, a, b, c, x[i + 4], 11, 1272893353);
                    c = md5hh(c, d, a, b, x[i + 7], 16, -155497632);
                    b = md5hh(b, c, d, a, x[i + 10], 23, -1094730640);
                    a = md5hh(a, b, c, d, x[i + 13], 4, 681279174);
                    d = md5hh(d, a, b, c, x[i + 0], 11, -358537222);
                    c = md5hh(c, d, a, b, x[i + 3], 16, -722521979);
                    b = md5hh(b, c, d, a, x[i + 6], 23, 76029189);
                    a = md5hh(a, b, c, d, x[i + 9], 4, -640364487);
                    d = md5hh(d, a, b, c, x[i + 12], 11, -421815835);
                    c = md5hh(c, d, a, b, x[i + 15], 16, 530742520);
                    b = md5hh(b, c, d, a, x[i + 2], 23, -995338651);
                    a = md5ii(a, b, c, d, x[i], 6, -198630844);
                    d = md5ii(d, a, b, c, x[i + 7], 10, 1126891415);
                    c = md5ii(c, d, a, b, x[i + 14], 15, -1416354905);
                    b = md5ii(b, c, d, a, x[i + 5], 21, -57434055);
                    a = md5ii(a, b, c, d, x[i + 12], 6, 1700485571);
                    d = md5ii(d, a, b, c, x[i + 3], 10, -1894986606);
                    c = md5ii(c, d, a, b, x[i + 10], 15, -1051523);
                    b = md5ii(b, c, d, a, x[i + 1], 21, -2054922799);
                    a = md5ii(a, b, c, d, x[i + 8], 6, 1873313359);
                    d = md5ii(d, a, b, c, x[i + 15], 10, -30611744);
                    c = md5ii(c, d, a, b, x[i + 6], 15, -1560198380);
                    b = md5ii(b, c, d, a, x[i + 13], 21, 1309151649);
                    a = md5ii(a, b, c, d, x[i + 4], 6, -145523070);
                    d = md5ii(d, a, b, c, x[i + 11], 10, -1120210379);
                    c = md5ii(c, d, a, b, x[i + 2], 15, 718787259);
                    b = md5ii(b, c, d, a, x[i + 9], 21, -343485551);
                    a = safeAdd(a, olda);
                    b = safeAdd(b, oldb);
                    c = safeAdd(c, oldc);
                    d = safeAdd(d, oldd);
                  }
                  return [a, b, c, d];
                }
                function binl2rstr(input) {
                  var output = '';
                  for (var i = 0; i < input.length * 32; i += 8) {
                    output += String.fromCharCode((input[i >> 5] >>> (i % 32)) & 0xff);
                  }
                  return output;
                }
                function rstr2binl(input) {
                  var output = [];
                  output[(input.length >> 2) - 1] = undefined;
                  for (var i = 0; i < output.length; i++) {
                    output[i] = 0;
                  }
                  for (var i = 0; i < input.length * 8; i += 8) {
                    output[i >> 5] |= (input.charCodeAt(i / 8) & 0xff) << (i % 32);
                  }
                  return output;
                }
                function rstrMD5(s) {
                  return binl2rstr(binlMD5(rstr2binl(s), s.length * 8));
                }
                function rstr2hex(input) {
                  var hexTab = '0123456789abcdef';
                  var output = '';
                  for (var i = 0; i < input.length; i++) {
                    var x = input.charCodeAt(i);
                    output += hexTab.charAt((x >>> 4) & 0x0f) + hexTab.charAt(x & 0x0f);
                  }
                  return output;
                }
                return function(string) {
                  return rstr2hex(rstrMD5(string));
                };
              })();

              window.__XY_SEARCH_FETCH__ = async ({ keyword, page, min_price, max_price, free_ship, sort_field, sort_order }) => {
                const timestamp = String(Date.now());
                const appKey = '34839810';
                const data = {
                  pageNumber: page,
                  rowsPerPage: 30,
                  keyword,
                  sortValue: sort_order || '',
                  sortField: sort_field || '',
                  propValueStr: JSON.stringify({
                    searchFilter: 'publishDays:14;',
                    minPrice: min_price ?? '',
                    maxPrice: max_price ?? '',
                    freeShipping: free_ship ? '1' : '',
                  }),
                  searchReqFromPage: 'pcSearch',
                };
                const dataStr = JSON.stringify(data);
                const token = getToken();
                const sign = md5(`${token}&${timestamp}&${appKey}&${dataStr}`);
                const query = new URLSearchParams({
                  jsv: '2.7.2',
                  appKey,
                  t: timestamp,
                  sign,
                  api: 'mtop.taobao.idlemtopsearch.pc.search',
                  v: '1.0',
                  type: 'originaljson',
                  dataType: 'json',
                  timeout: '20000',
                  data: dataStr,
                });
                const response = await fetch(`https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/?${query.toString()}`, {
                  method: 'POST',
                  credentials: 'include',
                  headers: {
                    'content-type': 'application/x-www-form-urlencoded',
                  },
                });
                const payload = await response.json();
                console.log('PAGE_API_RAW ret=' + String(payload.ret) + ' hasData=' + (payload.data != null) + ' dataKeys=' + (payload.data ? Object.keys(payload.data).join(',') : '') + ' resultListLen=' + (payload.data?.resultList?.length ?? -1));
                const resultList = payload?.data?.resultList || [];
                return {
                  _raw: payload,
                  keyword,
                  page,
                  items: resultList.map((entry) => {
                    const main = entry?.data?.item?.main || {};
                    const exContent = main.exContent || {};
                    const clickArgs = main.clickParam?.args || {};
                    const itemId = clickArgs.item_id || exContent.itemId || '';

                    const extractText = (val) => {
                      if (typeof val === 'string') return val;
                      if (Array.isArray(val)) {
                        return val.map(v => typeof v === 'object' && v !== null ? (v.text || '') : (typeof v === 'string' ? v : '')).join('');
                      }
                      return String(val || '');
                    };

                    return {
                      item_id: itemId,
                      title: main.title || exContent.title || '',
                      price: extractText(exContent.price),
                      original_price: extractText(exContent.originalPrice),
                      want_cnt: Number(exContent.wantNum || 0),
                      seller_nick: exContent.userNick || '',
                      seller_city: exContent.city || '',
                      image_urls: exContent.picUrl ? [exContent.picUrl] : [],
                      detail_url: itemId ? `https://www.goofish.com/item?id=${itemId}` : '',
                      is_free_ship: Boolean(exContent.freeDelivery),
                      publish_time: null,
                      exposure_score: 0.0,
                    };
                  }).filter((item) => item.item_id),
                };
              };
            }
            """
        )
        self._bridge_ready = True

    async def fetch_page(self, params: SearchParams, page_number: int) -> PageApiResult:
        try:
            if self.ensure_page_ready is not None:
                await self.ensure_page_ready()
            await self._ensure_bridge()
            payload = {
                "keyword": params.keyword,
                "page": page_number,
                "min_price": params.min_price,
                "max_price": params.max_price,
                "free_ship": params.free_ship,
                "sort_field": params.sort_field,
                "sort_order": params.sort_order,
            }
            raw = await self.page.evaluate(
                """
                async ({ keyword, page, min_price, max_price, free_ship, sort_field, sort_order }) => {
                  return await window.__XY_SEARCH_FETCH__({
                    keyword,
                    page,
                    min_price,
                    max_price,
                    free_ship,
                    sort_field,
                    sort_order,
                  });
                }
                """,
                payload,
            )
            data_val = raw.get("data")
            data_info = (
                f"dict with keys {list(data_val.keys())}"
                if isinstance(data_val, dict)
                else str(data_val)[:100]
            )

        except PageApiSearchError:
            raise
        except Exception as exc:
            raise PageApiSearchError(str(exc)) from exc

        if not isinstance(raw, dict):
            raise PageApiSearchError("invalid page api response")
        actual_keyword = raw.get("keyword")
        if actual_keyword != params.keyword:
            raise PageApiSearchError(
                f"keyword mismatch: expected {params.keyword}, got {actual_keyword}"
            )
        items = [SearchItem(**item) for item in raw.get("items", [])]
        print(
            f"[PageApi] 第 {page_number} 页返回 keyword={actual_keyword!r} items={len(items)}",
            flush=True,
        )
        return PageApiResult(
            keyword=actual_keyword,
            page=int(raw.get("page", page_number)),
            items=items,
        )


class StableSearchRunner:
    """稳定搜索运行器 - 支持分页、去重、stale page 控制"""

    def __init__(self, client, max_stale_pages: int = 3):
        """
        Args:
            client: 搜索客户端（HttpApiSearchClient 或 PageApiSearchClient）
            max_stale_pages: 最大连续无新增页数
        """
        self.client = client
        self.max_stale_pages = max_stale_pages

    async def search(self, params: SearchParams) -> SearchOutcome:
        """执行搜索"""
        all_items = []
        seen_item_ids = set()
        stale_pages = 0
        page_number = 1

        engine_name = getattr(self.client, "engine_name", "page_api")

        while len(all_items) < params.rows:
            result = await self.client.fetch_page(params, page_number=page_number)
            items = result.items

            new_count = 0
            for item in items:
                if item.item_id not in seen_item_ids:
                    seen_item_ids.add(item.item_id)
                    all_items.append(item)
                    new_count += 1

            print(
                f"[{engine_name}] 第 {page_number} 页解析完成 "
                f"raw_items={len(items)} new_items={new_count} total_items={len(all_items)}",
                flush=True,
            )

            if len(all_items) >= params.rows:
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="target_reached",
                    stale_pages=stale_pages,
                    engine_used=engine_name,
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            stale_pages = stale_pages + 1 if new_count == 0 else 0
            if stale_pages >= self.max_stale_pages:
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="stale_limit",
                    stale_pages=stale_pages,
                    engine_used=engine_name,
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            page_number += 1

        return SearchOutcome(
            items=all_items[: params.rows],
            requested_rows=params.rows,
            returned_rows=len(all_items[: params.rows]),
            stop_reason="target_reached",
            stale_pages=stale_pages,
            engine_used=engine_name,
            fallback_reason=None,
            pages_fetched=page_number,
        )
