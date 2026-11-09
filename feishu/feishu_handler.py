"""飞书消息事件处理器模块

负责处理飞书 `im.message.receive_v1` 事件，包括：
- 解析事件数据中的发送者、消息内容、消息类型等
- 执行访问控制（私聊/群聊开关、白名单/黑名单策略）
- 群聊 @机器人 触发检测
- 文本/图片/富文本消息内容解析
- 复用 lobster_claw 的会话与 LLM 响应能力
- 通过飞书 API 回复用户
- 内存级日志记录与查询

设计原则：
- 所有错误在 handle_event 内兜底，不向外抛出
- 长消息和长响应自动截断存储，避免内存溢出
- 对 lobster_claw 的导入采用延迟导入，避免循环依赖
"""
import json
import time
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from utils.logger import logger
from .feishu_config import FeishuConfig
from .feishu_client import FeishuClient


class FeishuMessageHandler:
    """飞书消息事件处理器。

    处理 `im.message.receive_v1` 事件，整合飞书配置、飞书客户端与
    lobster_claw 的 LLM 响应能力，对外暴露统一的 ``handle_event`` 入口。

    Attributes:
        config: 飞书配置实例。
        client: 飞书 API 客户端实例。
        message_logs: 消息处理日志（内存存储）。
        MAX_LOGS: 日志最大条数，超出时移除最旧的。
    """

    def __init__(self, config: FeishuConfig, client: FeishuClient):
        """初始化消息事件处理器。

        Args:
            config: 已加载好的 :class:`FeishuConfig` 实例。
            client: 已初始化的 :class:`FeishuClient` 实例。
        """
        self.config = config
        self.client = client
        # 消息处理日志（内存存储）
        self.message_logs: List[Dict[str, Any]] = []
        self.MAX_LOGS = 1000

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    async def handle_event(self, event_data: dict) -> dict:
        """处理 `im.message.receive_v1` 事件的主入口。

        Args:
            event_data: 解密后的飞书事件数据字典。

        Returns:
            ``{"success": bool, "error": str}``。
        """
        start_time = time.time()
        # 默认字段，便于日志兜底
        sender_open_id = ""
        chat_id = ""
        chat_type = ""
        message_type = ""
        raw_content = ""
        text_content = ""
        message_id = ""
        mentions: list = []

        try:
            # 1. 解析事件数据
            event = event_data.get("event") or {}
            sender = event.get("sender") or {}
            sender_id = sender.get("sender_id") or {}
            sender_open_id = sender_id.get("open_id", "")

            message = event.get("message") or {}
            chat_id = message.get("chat_id", "")
            chat_type = message.get("chat_type", "")
            message_type = message.get("message_type", "")
            raw_content = message.get("content", "") or ""
            text_content = raw_content
            message_id = message.get("message_id", "")
            mentions = message.get("mentions", []) or []

            # 2. 检查 enabled 配置
            raw_cfg = self.config.get_raw()
            if not raw_cfg.get("enabled", False):
                logger.info("飞书接入未启用，忽略消息 chat_id=%s", chat_id)
                self._log_message(
                    sender_open_id, chat_id, message_type, text_content,
                    "", "ignored", time.time() - start_time,
                )
                return {"success": False, "error": "feishu integration disabled"}

            # 3. 检查 handle_dms / handle_groups 配置
            handle_groups = raw_cfg.get("handle_groups", True)
            handle_dms = raw_cfg.get("handle_dms", True)
            if chat_type == "group" and not handle_groups:
                logger.info("群聊消息处理已关闭，忽略 chat_id=%s", chat_id)
                self._log_message(
                    sender_open_id, chat_id, message_type, text_content,
                    "", "ignored", time.time() - start_time,
                )
                return {"success": False, "error": "group message handling disabled"}
            if chat_type == "p2p" and not handle_dms:
                logger.info("私聊消息处理已关闭，忽略 chat_id=%s", chat_id)
                self._log_message(
                    sender_open_id, chat_id, message_type, text_content,
                    "", "ignored", time.time() - start_time,
                )
                return {"success": False, "error": "dm message handling disabled"}

            # 4. 访问控制检查
            allowed, reason = self._check_access(sender_open_id, chat_type)
            if not allowed:
                logger.warning("访问被拒绝 open_id=%s chat_id=%s 原因=%s",
                               sender_open_id, chat_id, reason)
                self._log_message(
                    sender_open_id, chat_id, message_type, text_content,
                    f"[access denied] {reason}", "ignored", time.time() - start_time,
                )
                return {"success": False, "error": reason}

            # 5. 群聊 @机器人触发检测（在 _parse_message_content 内进一步处理）
            trigger_on_mention = raw_cfg.get("trigger_on_mention", True)
            if chat_type == "group" and trigger_on_mention:
                bot_mentioned = self._is_bot_mentioned(mentions)
                if not bot_mentioned:
                    logger.info("群聊消息未 @机器人，忽略 chat_id=%s", chat_id)
                    self._log_message(
                        sender_open_id, chat_id, message_type, text_content,
                        "", "ignored", time.time() - start_time,
                    )
                    return {"success": False, "error": "bot not mentioned in group"}

            # 6. 解析消息内容
            parsed_text, image_bytes = self._parse_message_content(
                message_type, raw_content, mentions,
            )
            text_content = parsed_text
            if not text_content and not image_bytes:
                logger.info("消息内容为空或不支持，忽略 chat_id=%s type=%s",
                            chat_id, message_type)
                self._log_message(
                    sender_open_id, chat_id, message_type, text_content,
                    "", "ignored", time.time() - start_time,
                )
                return {"success": False, "error": "empty or unsupported message"}

            # 7. 获取或创建会话
            session_id = self._get_or_create_session(chat_id, chat_type)

            # 8. 调用 LLM 生成响应
            response_text = await self._generate_response(session_id, text_content, image_bytes)

            # 9. 通过飞书 API 回复用户
            sent = self._send_reply(message_id, chat_id, chat_type, response_text)
            if not sent:
                logger.error("回复发送失败 message_id=%s chat_id=%s", message_id, chat_id)

            # 10. 记录成功日志
            duration = time.time() - start_time
            self._log_message(
                sender_open_id, chat_id, message_type, text_content,
                response_text, "success", duration,
            )
            return {"success": True, "error": ""}

        except Exception as e:
            # 11. 异常时记录错误日志
            logger.error("处理飞书消息事件失败: %s", e, exc_info=True)
            duration = time.time() - start_time
            self._log_message(
                sender_open_id, chat_id, message_type, text_content,
                f"[error] {e}", "error", duration,
            )
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # 访问控制
    # ------------------------------------------------------------------
    def _check_access(self, open_id: str, chat_type: str) -> Tuple[bool, str]:
        """执行访问控制检查。

        Args:
            open_id: 发送者的 open_id。
            chat_type: 会话类型，``p2p`` 表示私聊，``group`` 表示群聊。

        Returns:
            ``(是否允许, 原因)`` 元组。
        """
        raw_cfg = self.config.get_raw()
        handle_groups = raw_cfg.get("handle_groups", True)
        handle_dms = raw_cfg.get("handle_dms", True)
        dm_policy = raw_cfg.get("dm_policy", "open")
        allow_list = raw_cfg.get("allow_list", []) or []
        block_list = raw_cfg.get("block_list", []) or []

        # 群聊开关
        if chat_type == "group" and not handle_groups:
            return False, "group message handling disabled"
        # 私聊开关
        if chat_type == "p2p" and not handle_dms:
            return False, "dm message handling disabled"

        # 私聊策略（仅对私聊生效；群聊由 handle_groups 控制）
        if chat_type == "p2p":
            if dm_policy == "allowlist":
                if open_id not in allow_list:
                    return False, "open_id not in allow_list"
            elif dm_policy == "blocklist":
                if open_id in block_list:
                    return False, "open_id in block_list"
            elif dm_policy == "open":
                return True, "open policy"
            else:
                # 未知策略，保守拒绝
                return False, f"unknown dm_policy: {dm_policy}"

        return True, "allowed"

    def _is_bot_mentioned(self, mentions: list) -> bool:
        """判断 mentions 列表中是否包含机器人。

        飞书在 @机器人 时会在 mentions 中包含机器人自身的信息。
        只要 mentions 非空且包含至少一个有效的 mention 项即视为 @了机器人
        （飞书事件仅在被 @时才携带 mentions 字段，且通常只有机器人自身）。

        Args:
            mentions: 事件中的 mentions 列表。

        Returns:
            被 @机器人 返回 True，否则 False。
        """
        if not mentions:
            return False
        for mention in mentions:
            if not isinstance(mention, dict):
                continue
            # 飞书 mention 项至少包含 key 和 id 字段
            if mention.get("key") and mention.get("id"):
                return True
        return False

    # ------------------------------------------------------------------
    # 消息内容解析
    # ------------------------------------------------------------------
    def _parse_message_content(
        self, message_type: str, content: str, mentions: list,
    ) -> Tuple[str, Optional[bytes]]:
        """解析消息内容，返回文本与可选的图片二进制数据。

        Args:
            message_type: 飞书消息类型，如 ``text``/``image``/``post``/``file``。
            content: 飞书消息原始 content 字段（JSON 字符串）。
            mentions: 事件中的 mentions 列表，用于剥离 @文本。

        Returns:
            ``(text_content, image_bytes_optional)`` 元组。图片下载失败时
            image_bytes 为 None，text_content 包含错误提示。
        """
        if not content:
            return "", None

        # content 是 JSON 字符串，先尝试解析
        try:
            content_obj = json.loads(content)
        except (ValueError, TypeError):
            # 部分类型 content 不是 JSON，直接当文本处理
            content_obj = {"text": content}

        if message_type == "text":
            text = content_obj.get("text", "") if isinstance(content_obj, dict) else str(content_obj)
            text = self._strip_mentions(text, mentions)
            return text, None

        if message_type == "image":
            image_key = ""
            if isinstance(content_obj, dict):
                image_key = content_obj.get("image_key", "")
            if not image_key:
                return "[收到图片但未提供 image_key]", None
            # 调用飞书客户端下载图片
            # download_image 的 message_id 参数为保留参数（实际 API 仅依赖 image_key），
            # 由于本方法签名不包含 message_id，此处传空字符串。
            try:
                image_bytes = self.client.download_image("", image_key)
            except Exception as e:
                logger.error("下载飞书图片失败 image_key=%s: %s", image_key, e)
                return f"[下载图片失败 image_key={image_key}]", None
            if image_bytes is None:
                return f"[下载图片失败 image_key={image_key}]", None
            return f"[收到图片 image_key={image_key}]", image_bytes

        if message_type == "post":
            text = self._extract_post_text(content_obj)
            text = self._strip_mentions(text, mentions)
            return text, None

        # 其他类型暂不支持
        return f"[暂不支持的消息类型: {message_type}]", None

    def _strip_mentions(self, text: str, mentions: list) -> str:
        """从文本中剥离 @内容（mentions 中的 key）。

        飞书在文本消息中通过 ``@_user_1`` 等占位符表示 @，需要去除。

        Args:
            text: 原始文本。
            mentions: mentions 列表，从中提取 key 进行剥离。

        Returns:
            剥离 @占位符后的文本。
        """
        if not text or not mentions:
            return text
        result = text
        for mention in mentions:
            if isinstance(mention, dict):
                key = mention.get("key")
                if key:
                    result = result.replace(key, "")
        # 合并多余空白
        result = " ".join(result.split())
        return result.strip()

    def _extract_post_text(self, content_obj: Any) -> str:
        """从富文本 post 消息中提取纯文本。

        飞书 post 消息结构较为复杂，常见形式为：
        ``{"title": "...", "content": [[{"tag": "text", "text": "..."}, ...], ...]}``
        或使用 ``zh_cn``/``en_us`` 等语言 key 包裹。

        Args:
            content_obj: 已解析的 content 字典。

        Returns:
            提取的纯文本（多段以换行连接）。
        """
        if not isinstance(content_obj, dict):
            return ""

        # 取出实际内容（可能被语言 key 包裹）
        body = content_obj
        locale_keys = ("zh_cn", "en_us", "ja_jp", "ko_kr")
        for key in locale_keys:
            if key in body and isinstance(body[key], dict):
                body = body[key]
                break

        parts: List[str] = []
        title = body.get("title")
        if title:
            parts.append(str(title))

        content_lines = body.get("content") or body.get("lines")
        if isinstance(content_lines, list):
            for line in content_lines:
                if not isinstance(line, list):
                    continue
                line_text = ""
                for element in line:
                    if not isinstance(element, dict):
                        continue
                    tag = element.get("tag")
                    if tag == "text":
                        line_text += element.get("text", "")
                    elif tag in ("a", "at"):
                        # 链接或 @，取 text 字段
                        line_text += element.get("text", "") or element.get("name", "")
                if line_text:
                    parts.append(line_text)

        return "\n".join(parts).strip()

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------
    def _get_or_create_session(self, chat_id: str, chat_type: str) -> str:
        """获取或创建会话，复用 lobster_claw 的 chat_sessions。

        会话 ID 规则：
        - 私聊：``feishu_{chat_id}``
        - 群聊：``feishu_group_{chat_id}``

        Args:
            chat_id: 飞书会话 ID。
            chat_type: 会话类型。

        Returns:
            已存在或新创建的 session_id。
        """
        if chat_type == "group":
            session_id = f"feishu_group_{chat_id}"
        else:
            session_id = f"feishu_{chat_id}"

        # 延迟导入避免循环依赖
        from web.routes.lobster_claw import get_or_create_session
        return get_or_create_session(session_id)

    # ------------------------------------------------------------------
    # LLM 响应
    # ------------------------------------------------------------------
    async def _generate_response(
        self, session_id: str, text: str, image_bytes: Optional[bytes],
    ) -> str:
        """调用 LLM 生成响应文本。

        复用 lobster_claw 的 ``generate_chat_response``。MVP 阶段图片作为
        文本提示传入，不支持多模态调用。

        Args:
            session_id: 会话 ID。
            text: 用户输入文本。
            image_bytes: 可选的图片二进制数据（目前仅作为存在性提示）。

        Returns:
            LLM 生成的响应文本。失败时返回错误提示文本。
        """
        # 延迟导入避免循环依赖
        from web.routes.lobster_claw import generate_chat_response

        # 组装提示文本
        prompt = text or ""
        if image_bytes is not None:
            # MVP 阶段：图片以文本提示方式告知 LLM
            size_kb = len(image_bytes) / 1024.0
            prompt = f"{text}\n\n[附图: {size_kb:.1f} KB]".strip()

        if not prompt:
            return "[未提供可处理的内容]"

        try:
            result = await generate_chat_response(session_id, prompt)
        except Exception as e:
            logger.error("调用 generate_chat_response 失败: %s", e, exc_info=True)
            return f"[生成响应失败: {e}]"

        if isinstance(result, dict) and result.get("success"):
            content = result.get("content", "")
            if content:
                return content
            return "[LLM 返回空内容]"
        # 失败时返回错误提示
        err = result.get("error", "unknown error") if isinstance(result, dict) else "unknown error"
        return f"[生成响应失败: {err}]"

    # ------------------------------------------------------------------
    # 回复发送
    # ------------------------------------------------------------------
    def _send_reply(
        self, message_id: str, chat_id: str, chat_type: str, text: str,
    ) -> bool:
        """通过飞书 API 回复用户消息。

        优先使用 ``reply_message`` 回复原消息；失败时回退到
        ``send_text_message`` 直接发送到 chat_id。

        Args:
            message_id: 被回复的消息 ID。
            chat_id: 飞书会话 ID，回退发送时使用。
            chat_type: 会话类型（保留参数，便于未来按类型分流）。
            text: 要回复的文本。

        Returns:
            发送成功返回 True，否则 False。
        """
        if not text:
            return False

        content = json.dumps({"text": text}, ensure_ascii=False)
        try:
            result = self.client.reply_message(message_id, content, "text")
        except Exception as e:
            logger.error("reply_message 调用异常 message_id=%s: %s", message_id, e)
            result = {"success": False, "error": str(e)}

        if isinstance(result, dict) and result.get("success"):
            return True

        # 回退：直接通过 chat_id 发送
        logger.info("reply_message 失败，尝试通过 send_text_message 发送 chat_id=%s", chat_id)
        try:
            send_result = self.client.send_text_message(chat_id, "chat_id", text)
        except Exception as e:
            logger.error("send_text_message 调用异常 chat_id=%s: %s", chat_id, e)
            return False

        return bool(isinstance(send_result, dict) and send_result.get("success"))

    # ------------------------------------------------------------------
    # 日志记录
    # ------------------------------------------------------------------
    def _log_message(
        self,
        sender_open_id: str,
        chat_id: str,
        message_type: str,
        content: str,
        response: str,
        status: str,
        duration: float,
    ) -> None:
        """记录一条消息处理日志到内存。

        Args:
            sender_open_id: 发送者 open_id。
            chat_id: 会话 ID。
            message_type: 消息类型。
            content: 原始消息内容（会自动截断到 200 字符）。
            response: LLM 响应文本（会自动截断到 500 字符）。
            status: 处理状态，``success``/``error``/``ignored``。
            duration: 处理耗时（秒）。
        """
        log_entry = {
            "id": len(self.message_logs) + 1,
            "timestamp": datetime.now().isoformat(),
            "sender": sender_open_id,
            "chat_id": chat_id,
            "message_type": message_type,
            # 截断避免内存溢出
            "content": (content or "")[:2000],
            "response": (response or "")[:10000],
            "status": status,
            "duration": duration,
        }
        self.message_logs.append(log_entry)
        # 超过 MAX_LOGS 时移除最旧的
        if len(self.message_logs) > self.MAX_LOGS:
            self.message_logs = self.message_logs[-self.MAX_LOGS:]

    def get_message_logs(self, limit: int = 50, offset: int = 0) -> list:
        """获取消息处理日志（倒序，最新在前）。

        Args:
            limit: 返回的最大条数，默认 50。
            offset: 偏移量（从最新开始计算），默认 0。

        Returns:
            日志条目列表。
        """
        # 倒序，最新在前
        reversed_logs = list(reversed(self.message_logs))
        if offset < 0:
            offset = 0
        if limit < 0:
            limit = 0
        return reversed_logs[offset: offset + limit]

    def clear_message_logs(self) -> int:
        """清空消息日志。

        Returns:
            清空的日志条数。
        """
        count = len(self.message_logs)
        self.message_logs = []
        return count
