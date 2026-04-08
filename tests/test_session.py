"""
测试 session 模块 - 登录、Token 刷新、Cookie 检查
"""
import asyncio
from src.session import SessionManager, login, refresh_token, check_cookie_valid


async def test_refresh_token():
    """测试刷新 token"""
    async with SessionManager() as session:
        print("\n=== 测试刷新 Token ===")
        result = await session.refresh_token()

        if result:
            print(f"刷新成功!")
            print(f"  Token: {result['token'][:20]}...")
            print(f"  Full Cookie: {result['full_cookie'][:50]}...")
        else:
            print("刷新失败")

        return result


async def test_check_session():
    """测试检查会话"""
    async with SessionManager() as session:
        print("\n=== 测试检查会话 ===")
        is_valid = await session.check_cookie_valid()

        if is_valid:
            print("Cookie 有效")
        else:
            print("Cookie 无效，需要重新登录")

        return is_valid


async def test_login():
    """测试登录功能"""
    async with SessionManager() as session:
        print("\n=== 测试登录 ===")

        # 先检查是否有缓存 Cookie
        cached_token = session.load_cached_cookie()
        if cached_token:
            print(f"找到缓存 Cookie: {cached_token[:20]}...")

            # 检查是否已登录
            if await session.check_login_status():
                print("已登录，使用现有会话")
                return True

        # 需要扫码登录
        print("需要扫码登录...")
        result = await session.login(timeout=120)

        if result.get('success'):
            if result.get('token'):
                print(f"登录成功！Token: {result.get('token', '')[:20]}...")
            elif result.get('qr_code'):
                print("已获取二维码，等待扫码...")
                print(f"  QR URL: {result['qr_code']['url'][:50]}...")
            return True


async def main():
    """主函数"""
    async with SessionManager() as session:
        # 先测试刷新 token
        print("\n=== 测试刷新 Token ===")
        result = await session.refresh_token()

        if result:
            print(f"刷新成功!")
            print(f"  Token: {result['token'][:20]}...")
            print(f"  Full Cookie: {result['full_cookie'][:50]}...")

            # 刷新后立即检查会话
            print("\n=== 测试检查会话 ===")
            is_valid = await session.check_cookie_valid()

            if is_valid:
                print("Cookie 有效")
            else:
                print("Cookie 无效，需要重新登录")
        else:
            print("\nToken 刷新失败")


if __name__ == "__main__":
    asyncio.run(main())
