"""
测试 core 模块 - 搜索和发布功能
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.core import XianyuApp, _ItemCopierImpl, SearchItem


async def test_search_no_duplicates():
    """测试搜索商品去重功能 - 查询多条数据时不能有重复"""
    async with XianyuApp() as app:
        print(f"\n=== 测试搜索去重功能 ===")

        # 测试查询 90 条商品
        target_count = 90
        items = await app.search("机械键盘", rows=target_count)

        print(f"\n请求数量：{target_count} 条")
        print(f"实际返回：{len(items)} 条")

        # 检查重复
        item_ids = [item.item_id for item in items]
        unique_ids = set(item_ids)

        print(f"唯一 ID 数：{len(unique_ids)} 个")

        if len(item_ids) != len(unique_ids):
            # 找出重复的 ID
            seen = set()
            duplicates = []
            for item_id in item_ids:
                if item_id in seen and item_id not in duplicates:
                    duplicates.append(item_id)
                seen.add(item_id)

            print(f"\n发现重复商品 ID:")
            for dup_id in duplicates:
                count = item_ids.count(dup_id)
                print(f"  - {dup_id}: 出现 {count} 次")

        # 验证结果
        assert len(items) <= target_count, (
            f"返回数量 {len(items)} 超过请求数量 {target_count}"
        )
        assert len(item_ids) == len(unique_ids), (
            f"发现 {len(item_ids) - len(unique_ids)} 个重复商品"
        )

        # 打印部分结果
        print(f"\n前 5 个商品:")
        for i, item in enumerate(items[:5]):
            print(
                f"  {i + 1}. {item.title[:30]}... - ¥{item.price} (ID: {item.item_id})"
            )

        print(f"\n✓ 测试通过：返回 {len(items)} 条商品，无重复")
        return items


async def test_search_small_count():
    """测试查询少量商品（10 条）"""
    async with XianyuApp() as app:
        print(f"\n=== 测试小数量搜索 ===")

        items = await app.search("鼠标", rows=10)

        print(f"请求 10 条，返回 {len(items)} 条")

        item_ids = [item.item_id for item in items]
        unique_ids = set(item_ids)

        assert len(item_ids) == len(unique_ids), "发现重复商品"
        assert len(items) <= 10, "返回数量超过请求数量"

        print(f"✓ 测试通过：返回 {len(items)} 条商品，无重复")
        return items


async def test_search_with_filters():
    """测试带筛选条件的搜索"""
    async with XianyuApp() as app:
        print(f"\n=== 测试带筛选搜索 ===")

        items = await app.search(
            "键盘", rows=20, min_price=50, max_price=200, free_ship=True
        )

        print(f"请求 20 条（50-200 元，包邮），返回 {len(items)} 条")

        item_ids = [item.item_id for item in items]
        unique_ids = set(item_ids)

        # 主要验证去重
        assert len(item_ids) == len(unique_ids), "发现重复商品"
        assert len(items) <= 20, "返回数量超过请求数量"

        # 注：闲鱼网页筛选可能不完全准确，主要验证去重功能
        print(f"✓ 测试通过：返回 {len(items)} 条商品，无重复")
        return items


async def test_capture_item():
    """测试捕获商品详情"""
    item_url = "https://www.goofish.com/item?id=933097353434"

    async with XianyuApp() as app:
        print(f"\n=== 测试捕获商品详情 ===")
        print(f"商品链接：{item_url}")

        item = await app.get_detail(item_url)

        if item:
            print(f"\n捕获成功!")
            print(f"  商品 ID: {item.item_id}")
            print(f"  标题：{item.title[:50]}...")
            print(f"  分类：{item.category} (ID: {item.category_id})")
            print(f"  品牌：{item.brand}")
            print(f"  型号：{item.model}")
            print(f"  价格：¥{item.min_price} - ¥{item.max_price}")
            print(f"  图片：{len(item.image_urls)} 张")
            print(f"  包邮：{item.is_free_ship}")
            print(f"  所在地：{item.seller_city}")
            print(f"  描述长度：{len(item.description)}")
        else:
            print("\n捕获失败")

        assert item is not None, "获取商品详情失败"
        return item


async def test_publish_from_item():
    """测试完整的复制发布流程"""
    item_url = "https://www.goofish.com/item?id=1036280645275"

    async with XianyuApp() as app:
        print(f"\n=== 测试复制发布 ===")
        print(f"对标商品：{item_url}")

        result = await app.publish(item_url, new_price=95.0, condition="全新")

        import sys

        sys.stdout.flush()
        print(f"\n发布结果：success={result.get('success')}")
        if result.get("success"):
            print("表单填充完成，请检查浏览器窗口")
            if result.get("item_data"):
                item_data = result["item_data"]
                print(f"  标题：{item_data.get('title', '')[:50]}...")
                print(f"  价格：¥{item_data.get('min_price')}")
                print(f"  图片数量：{len(item_data.get('image_urls', []))} 张")
                print(f"  分类：{item_data.get('category')}")
        else:
            print(f"错误：{result.get('error')}")
        return result


if __name__ == "__main__":
    print("=== 运行搜索去重测试 ===")
    asyncio.run(test_search_no_duplicates())

    print("\n\n=== 运行小数量搜索测试 ===")
    asyncio.run(test_search_small_count())

    print("\n\n=== 运行带筛选搜索测试 ===")
    asyncio.run(test_search_with_filters())

    print("\n\n=== 运行商品详情测试 ===")
    item = asyncio.run(test_capture_item())

    if item:
        print("\n\n捕获成功，继续测试发布流程...")
        asyncio.run(test_publish_from_item())
    else:
        print("\n捕获失败，跳过发布测试")
