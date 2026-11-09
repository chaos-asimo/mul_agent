"""飞书长连接客户端模块

使用飞书官方 SDK (lark-oapi) 实现 WebSocket 长连接模式接收飞书事件。
相比 Webhook 模式，长连接模式无需公网地址，更适合本地开发和内网部署。

设计要点：
- 使用独立线程运行长连接客户端，避免阻塞主事件循环
- 通过回调机制将事件转发给已注册的处理器
- 支持自动重连和心跳检测
- 与现有 FeishuMessageHandler 无缝对接
"""
import threading
import time
import json
from typing import Optional, Callable, Dict, Any

import lark_oapi as lark
from lark_oapi.ws.client import Client as WsClient
from lark_oapi.event.dispatcher_handler import EventDispatcherHandlerBuilder
from lark_oapi.event.custom import CustomizedEvent

from utils.logger import logger
from .feishu_config import FeishuConfig


class FeishuLongConnectionClient:
    """飞书长连接客户端。

    使用 lark-oapi SDK 的 WebSocket 客户端实现长连接模式，
    在独立线程中运行，通过回调机制转发事件。

    Attributes:
        config: 飞书配置实例。
        _ws_client: lark-oapi 的 WebSocket 客户端。
        _thread: 运行长连接的线程。
        _running: 是否正在运行。
        _event_handler: 事件处理器回调。
    """

    def __init__(self, config: FeishuConfig):
        """初始化长连接客户端。

        Args:
            config: 已加载好的 :class:`FeishuConfig` 实例。
        """
        self.config = config
        self._ws_client: Optional[WsClient] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._event_handler: Optional[Callable[[dict], None]] = None

    def set_event_handler(self, handler: Callable[[dict], None]):
        """设置事件处理器回调。

        Args:
            handler: 事件处理函数，接收事件数据字典。
        """
        self._event_handler = handler

    def start(self):
        """启动长连接客户端。

        在独立线程中启动 WebSocket 长连接，连接成功后开始接收事件。
        如果配置不完整或已在运行，则跳过启动。
        """
        if self._running:
            logger.warning("飞书长连接客户端已在运行")
            return

        if not self.config.is_configured():
            logger.warning("飞书配置不完整，无法启动长连接客户端")
            return

        raw_cfg = self.config.get_raw()
        app_id = raw_cfg.get("app_id", "")
        app_secret = raw_cfg.get("app_secret", "")
        domain = raw_cfg.get("domain", "feishu")
        encrypt_key = raw_cfg.get("encrypt_key", "")
        verification_token = raw_cfg.get("verification_token", "")

        try:
            domain_url = "https://open.feishu.cn" if domain == "feishu" else "https://open.larksuite.com"

            builder = EventDispatcherHandlerBuilder(
                encrypt_key=encrypt_key or "",
                verification_token=verification_token or ""
            )

            builder.register_p2_customized_event(
                "im.message.receive_v1",
                lambda event: self._on_event(event)
            )

            event_handler = builder.build()

            self._ws_client = WsClient(
                app_id=app_id,
                app_secret=app_secret,
                domain=domain_url,
                event_handler=event_handler,
                auto_reconnect=True
            )

            self._running = True
            self._thread = threading.Thread(
                target=self._run_loop,
                name="feishu_ws_client",
                daemon=True
            )
            self._thread.start()

            logger.info("飞书长连接客户端启动成功")
        except Exception as e:
            self._running = False
            logger.error(f"飞书长连接客户端启动失败: {e}", exc_info=True)

    def stop(self):
        """停止长连接客户端。

        优雅关闭 WebSocket 连接并等待线程结束。
        """
        self._running = False
        if self._ws_client:
            try:
                self._ws_client._disconnect()
                logger.info("飞书长连接客户端已关闭")
            except Exception as e:
                logger.error(f"关闭飞书长连接客户端失败: {e}")

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_loop(self):
        """长连接运行循环（在独立线程中执行）。"""
        try:
            while self._running:
                try:
                    if self._ws_client:
                        logger.info("飞书长连接客户端开始监听事件...")
                        self._ws_client.start()
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"飞书长连接客户端异常: {e}")
                    if self._running:
                        logger.info("尝试重新连接飞书长连接...")
                        time.sleep(5)
        except Exception as e:
            logger.error(f"飞书长连接客户端运行循环异常: {e}")
        finally:
            self._running = False
            logger.info("飞书长连接客户端运行循环结束")

    def _on_event(self, event: CustomizedEvent):
        """处理收到的飞书事件。

        Args:
            event: lark-oapi 的 CustomizedEvent 对象。
        """
        try:
            header = event.header if hasattr(event, 'header') and event.header else None
            
            event_data = {
                "schema": "2.0",
                "header": {
                    "event_id": header.event_id if header else '',
                    "event_type": header.event_type if header else '',
                    "create_time": header.create_time if header else '',
                    "token": header.token if header else '',
                    "app_id": header.app_id if header else '',
                    "tenant_key": header.tenant_key if header else ''
                },
                "event": event.event if hasattr(event, 'event') and event.event else {}
            }

            if self._event_handler:
                self._event_handler(event_data)
        except Exception as e:
            logger.error(f"处理飞书事件失败: {e}", exc_info=True)