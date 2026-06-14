import asyncio
from collections.abc import Callable

import aiohttp
import blivedm
import blivedm.models.web as web_models

from .auth import AuthManager


class DanmakuClient:
    """
    弹幕客户端，用于获取B站直播弹幕
    """

    def __init__(self, room_id: int, sessdata: str = ''):
        self.room_id = room_id
        self.sessdata = sessdata
        self.session: aiohttp.ClientSession | None = None
        self.client: blivedm.BLiveClient | None = None
        self.handler: DanmakuHandler | None = None
        self.on_danmaku_received: Callable[[web_models.DanmakuMessage], None] | None = None
        self.on_gift_received: Callable[[web_models.GiftMessage], None] | None = None
        self.on_interact_received: Callable[[web_models.InteractWordV2Message], None] | None = None
        self.on_login_failed: Callable[[str], None] | None = None # callback(message)

    def set_danmaku_callback(self, callback: Callable[[web_models.DanmakuMessage], None]):
        """设置弹幕接收回调函数"""
        self.on_danmaku_received = callback

    def set_gift_callback(self, callback: Callable[[web_models.GiftMessage], None]):
        """设置礼物接收回调函数"""
        self.on_gift_received = callback

    def set_interact_callback(self, callback: Callable[[web_models.InteractWordV2Message], None]):
        """设置互动接收回调函数 (进房/关注)"""
        self.on_interact_received = callback

    def set_login_failed_callback(self, callback: Callable[[str], None]):
        """设置登录失效回调"""
        self.on_login_failed = callback

    async def start(self):
        """在事件循环中启动弹幕客户端"""
        # 在Executor中运行Cookie加载，避免阻塞主线程和可能的线程冲突
        loop = asyncio.get_running_loop()
        auth_manager = AuthManager()

        try:
            loaded_cookies, is_keyring = await loop.run_in_executor(None, auth_manager.load_auth_cookies)
            if is_keyring:
                if not await auth_manager.validate_session(loaded_cookies):
                    print("Keyring cookies expired")
                    if self.on_login_failed:
                        self.on_login_failed("本地保存的登录信息已失效，请重新登录")
                    # 失效了就清空，但不要回退到浏览器，因为用户意图是使用keyring
                    loaded_cookies = {}

        except Exception as e:
            print(f"Error loading cookies: {e}")
            loaded_cookies = {}

        if self.sessdata:
            loaded_cookies["SESSDATA"] = self.sessdata

        self.session = auth_manager.create_session_from_cookies(loaded_cookies)

        # 创建客户端和处理器
        self.client = blivedm.BLiveClient(self.room_id, session=self.session)
        self.handler = DanmakuHandler()
        self.handler.set_danmaku_client(self)
        self.client.set_handler(self.handler)

        loop = asyncio.get_event_loop()
        loop.call_soon(self.client.start)
        # 启动客户端
        # self.client.start()
        # await asyncio.sleep(0.1)  # 让出控制权以启动客户端

    async def send_danmaku(self, message: str) -> tuple[bool, str]:
        """发送弹幕"""
        if not self.session or not message:
            return False, "会话未初始化或消息为空"

        url = 'https://api.live.bilibili.com/msg/send'

        # 从cookie中获取csrf token (bili_jct)
        csrf_token = ''
        for cookie in self.session.cookie_jar:
            if cookie.key == 'bili_jct':
                csrf_token = cookie.value
                break

        if not csrf_token:
            # print("Error: No csrf_token found in cookies")
            return False, "未找到CSRF Token，请重新连接或检查Cookie"

        data = {
            'bubble': '0',
            'msg': message,
            'color': '16777215',
            'mode': '1',
            'fontsize': '25',
            'rnd': str(int(asyncio.get_event_loop().time())),
            'roomid': self.room_id,
            'csrf': csrf_token,
            'csrf_token': csrf_token,
        }

        try:
            async with self.session.post(url, data=data) as res:
                if res.status != 200:
                    print(f"Send danmaku HTTP error: {res.status}")
                    return False, f"HTTP错误: {res.status}"
                json_data = await res.json()
                if json_data['code'] == 0:
                    return True, "发送成功"
                else:
                    print(f"Send danmaku failed: {json_data['message']}")
                    return False, f"发送失败: {json_data['message']}"
        except Exception as e:
            print(f"Send danmaku exception: {e}")
            return False, f"发送异常: {str(e)}"

    async def stop(self, normal_timeout: float = 3.0, forced_timeout: float = 3.0):
        """停止弹幕客户端，并确认底层网络任务和会话都已关闭。"""
        client = self.client
        session = self.session
        join_task: asyncio.Task | None = None
        stop_error: BaseException | None = None

        if client:
            try:
                if getattr(client, "is_running", False):
                    client.stop()
                    join_task = asyncio.create_task(client.join())
                    try:
                        await asyncio.wait_for(asyncio.shield(join_task), timeout=normal_timeout)
                    except asyncio.TimeoutError:
                        if session and not session.closed:
                            await session.close()
                        try:
                            await asyncio.wait_for(asyncio.shield(join_task), timeout=forced_timeout)
                        except asyncio.TimeoutError as exc:
                            stop_error = DanmakuShutdownError(
                                f"弹幕连接未能在强制关闭后停止，room_id={self.room_id}"
                            )
                            stop_error.__cause__ = exc
                            join_task.cancel()
                            await asyncio.gather(join_task, return_exceptions=True)
                    except Exception as exc:
                        stop_error = exc
            finally:
                try:
                    await client.close()
                except Exception as exc:
                    if stop_error is None:
                        stop_error = exc

        if session and not session.closed:
            await session.close()
        if stop_error is None:
            self.client = None
            self.session = None
            self.handler = None

        if stop_error is not None:
            raise stop_error


class DanmakuShutdownError(RuntimeError):
    pass


class DanmakuHandler(blivedm.BaseHandler):
    """弹幕处理器"""

    def __init__(self):
        super().__init__()
        self.danmaku_client: DanmakuClient | None = None

    def set_danmaku_client(self, client: DanmakuClient):
        self.danmaku_client = client

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        """处理弹幕消息"""
        if self.danmaku_client and self.danmaku_client.on_danmaku_received:
            self.danmaku_client.on_danmaku_received(message)

    def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage):
        """处理礼物消息"""
        if self.danmaku_client and self.danmaku_client.on_gift_received:
            self.danmaku_client.on_gift_received(message)

    def _on_interact_word_v2(self, client: blivedm.BLiveClient, message: web_models.InteractWordV2Message):
        """处理进入房间/关注"""
        if self.danmaku_client and self.danmaku_client.on_interact_received:
            self.danmaku_client.on_interact_received(message)

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        """处理醒目留言"""
        # 可以在这里处理醒目留言
        pass
