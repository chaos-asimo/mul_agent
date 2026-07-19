"""飞书事件接收路由模块

支持两种事件接收模式：
1. Webhook 模式：通过 HTTP POST 接收飞书事件回调（需要公网地址）
2. 长连接模式：使用飞书官方 SDK 的 WebSocket 长连接（无需公网地址，推荐）

参考：
- 飞书开放平台事件订阅文档
- 飞书官方 SDK (lark-oapi) 长连接文档
- 项目 feishu/feishu_config.py 提供配置
"""
import json
import base64
import hashlib
import asyncio
from typing import Callable, Dict, Any

from fastapi import APIRouter, Request, HTTPException
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.backends import default_backend

from feishu import FeishuConfig, FeishuClient, FeishuMessageHandler, FeishuLongConnectionClient
from utils.logger import logger


# 模块级实例
feishu_config = FeishuConfig()
router = APIRouter()

# 事件处理器注册表：event_type -> handler
_event_handlers: Dict[str, Callable] = {}


def register_event_handler(event_type: str, handler: Callable) -> None:
    """注册事件处理器。

    Args:
        event_type: 事件类型，如 'im.message.receive_v1'
        handler: 处理器函数，签名为 async def handler(event_data: dict) -> None。
            同步函数亦可，分发时会自动适配。
    """
    _event_handlers[event_type] = handler
    logger.info(f"已注册飞书事件处理器: {event_type} -> {getattr(handler, '__name__', handler)}")


def decrypt_event(encrypt_data: str, encrypt_key: str) -> Dict[str, Any]:
    """解密 AES-256-CBC 加密的事件数据。

    飞书事件加密格式：
        - 密文为 Base64 编码
        - Key = SHA256(encrypt_key) 前 32 字节
        - IV = 密文前 16 字节
        - 实际密文 = 密文第 16 字节之后
        - 使用 PKCS7 填充

    Args:
        encrypt_data: Base64 编码的加密数据
        encrypt_key: 飞书配置的 Encrypt Key

    Returns:
        解密后的 JSON 字典

    Raises:
        ValueError: 解密失败或 JSON 解析失败
    """
    try:
        encrypted_bytes = base64.b64decode(encrypt_data)
        key = hashlib.sha256(encrypt_key.encode('utf-8')).digest()[:32]
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        return json.loads(plaintext.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"事件解密失败: {e}") from e


def verify_token(event_data: Dict[str, Any]) -> bool:
    """校验事件中的 Verification Token。

    Args:
        event_data: 解密后的事件数据字典

    Returns:
        Token 匹配返回 True；配置中未设置 token 或不匹配返回 False
    """
    config = feishu_config.get_raw()
    expected_token = config.get('verification_token', '')
    if not expected_token:
        return False
    header = event_data.get('header') or {}
    token = header.get('token') or event_data.get('token')
    if not token:
        return False
    return token == expected_token


async def dispatch_event(event_data: Dict[str, Any]) -> None:
    """异步分发事件到注册的处理器。

    Args:
        event_data: 解密后的事件数据字典
    """
    header = event_data.get('header') or {}
    event_type = header.get('event_type') or event_data.get('type')
    if not event_type:
        logger.warning(f"飞书事件缺少 event_type 字段: {event_data}")
        return

    handler = _event_handlers.get(event_type)
    if handler is None:
        logger.info(f"飞书事件 {event_type} 未注册处理器，忽略")
        return

    try:
        if asyncio.iscoroutinefunction(handler):
            await handler(event_data)
        else:
            handler(event_data)
    except Exception as e:
        logger.error(f"处理飞书事件 {event_type} 失败: {e}", exc_info=True)


@router.post("/api/feishu/webhook")
async def feishu_webhook(request: Request):
    """飞书 Webhook 回调入口（webhook模式）。

    处理流程：
        1. 解析请求体 JSON
        2. 若包含 `encrypt` 字段，使用 Encrypt Key 解密
        3. 处理 URL 验证挑战（type=url），直接返回 challenge
        4. 校验 Verification Token，不匹配返回 403
        5. 异步分发事件，立即返回 200 避免飞书请求超时重试
    """
    try:
        body = await request.body()
        event_data = json.loads(body)
    except Exception as e:
        logger.error(f"飞书 Webhook 请求体解析失败: {e}")
        raise HTTPException(status_code=400, detail="请求体不是有效的 JSON")

    if 'encrypt' in event_data:
        config = feishu_config.get_raw()
        encrypt_key = config.get('encrypt_key', '')
        if not encrypt_key:
            logger.error("收到加密事件但未配置 encrypt_key")
            raise HTTPException(status_code=400, detail="未配置 encrypt_key，无法解密事件")
        try:
            event_data = decrypt_event(event_data['encrypt'], encrypt_key)
        except ValueError as e:
            logger.error(f"事件解密失败: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    if event_data.get('type') == 'url' or 'challenge' in event_data:
        challenge = event_data.get('challenge', '')
        logger.info(f"飞书 URL 验证挑战: {challenge}")
        return {"challenge": challenge}

    if not verify_token(event_data):
        logger.warning("飞书事件 Verification Token 校验失败")
        raise HTTPException(status_code=403, detail="Invalid verification token")

    asyncio.create_task(dispatch_event(event_data))
    return {"status": "ok"}


# ------------------------------------------------------------------
# 模块级实例化：消息事件处理器和长连接客户端
# ------------------------------------------------------------------
# 说明：即使飞书配置未完整，也实例化 client 与 handler，
# 便于其他模块查询处理器状态/日志；handle_event 内部会再次检查 enabled 字段。
if not feishu_config.is_configured():
    logger.warning("飞书配置未完整（app_id/app_secret 缺失），仍会实例化处理器，但实际消息处理会在 handle_event 内被跳过")

feishu_client = FeishuClient(feishu_config)
feishu_handler = FeishuMessageHandler(feishu_config, feishu_client)

# 注册 im.message.receive_v1 事件处理器
register_event_handler("im.message.receive_v1", feishu_handler.handle_event)

# 创建长连接客户端（默认使用长连接模式）
feishu_ws_client = FeishuLongConnectionClient(feishu_config)


async def start_feishu_ws_client():
    """启动飞书长连接客户端。

    根据配置的 event_mode 决定启动方式：
    - long_connection: 使用 lark-oapi SDK 的 WebSocket 长连接（推荐）
    - webhook: 仅注册 Webhook 路由，不启动长连接客户端
    """
    raw_cfg = feishu_config.get_raw()
    event_mode = raw_cfg.get('event_mode', 'long_connection')
    enabled = raw_cfg.get('enabled', False)

    if not enabled:
        logger.info("飞书接入未启用，跳过长连接客户端启动")
        return

    if event_mode == 'long_connection':
        logger.info(f"飞书事件模式: long_connection（使用官方SDK长连接）")
        # 设置事件回调，将长连接收到的事件转发给注册的处理器
        feishu_ws_client.set_event_handler(
            lambda evt: asyncio.create_task(dispatch_event(evt))
        )
        feishu_ws_client.start()
    else:
        logger.info(f"飞书事件模式: webhook（使用HTTP回调）")


def stop_feishu_ws_client():
    """停止飞书长连接客户端。"""
    feishu_ws_client.stop()


# 暴露给其他模块使用
__all__ = [
    "router", "feishu_config", "feishu_client", "feishu_handler", 
    "feishu_ws_client", "register_event_handler",
    "start_feishu_ws_client", "stop_feishu_ws_client"
]
