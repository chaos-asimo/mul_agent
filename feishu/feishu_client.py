"""飞书 API 客户端模块

封装飞书开放平台常用 API 调用，包括 tenant_access_token 获取与缓存、
消息发送与回复、图片下载与上传等。所有公共方法均不抛出异常，
失败时通过返回值（含 success/error 字段或 None）传递错误信息。

使用 httpx 同步客户端，适合在后台任务或非异步路径中调用。
"""
import json
import os
import time
from typing import Optional, Dict, Any, Tuple

import httpx

from utils.logger import logger
from .feishu_config import FeishuConfig


class FeishuClient:
    """飞书开放平台 API 客户端。

    通过传入的 :class:`FeishuConfig` 读取应用凭证，自动适配中国版 / 国际版
    域名，并对 tenant_access_token 进行内存级缓存。

    所有对外方法在失败时不会抛出异常，而是返回结构化的错误信息：
    - 消息类方法返回 ``{"success": bool, "data": ..., "error": str}``
    - 下载类方法返回 ``Optional[bytes]``
    - 上传类方法返回 ``Optional[str]``
    """

    # 中国版 / 国际版基础 URL
    BASE_URL_FEISHU = "https://open.feishu.cn/open-apis"
    BASE_URL_LARK = "https://open.larksuite.com/open-apis"

    # token 过期提前量（秒）：避免边界过期
    TOKEN_EXPIRE_BUFFER = 300

    # 网络错误最大重试次数
    MAX_RETRY = 3

    # token 过期相关错误码
    TOKEN_EXPIRED_CODE = 99991663

    def __init__(self, config: FeishuConfig):
        """初始化飞书 API 客户端。

        Args:
            config: 已加载好的 :class:`FeishuConfig` 实例。
        """
        self.config = config
        # token 缓存：(token, expire_at_timestamp) 元组
        self._token_cache: Optional[Tuple[str, float]] = None
        # 同步 HTTP 客户端，复用连接
        self._http_client = httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------
    # 基础工具方法
    # ------------------------------------------------------------------
    def _get_base_url(self) -> str:
        """根据配置返回飞书 API 基础 URL。

        Returns:
            中国版返回 ``https://open.feishu.cn/open-apis``，
            国际版返回 ``https://open.larksuite.com/open-apis``。
        """
        domain = self.config.get_raw().get("domain", "feishu")
        if domain == "lark":
            return self.BASE_URL_LARK
        return self.BASE_URL_FEISHU

    def _is_token_api(self, path: str) -> bool:
        """判断指定 path 是否为获取 token 的 API。

        Args:
            path: 请求路径（相对路径）。

        Returns:
            是获取 token 的 API 返回 True。
        """
        return path.endswith("/auth/v3/tenant_access_token/internal")

    # ------------------------------------------------------------------
    # token 获取与缓存
    # ------------------------------------------------------------------
    def get_tenant_access_token(self) -> Optional[str]:
        """获取 tenant_access_token，带内存缓存。

        缓存有效期按飞书返回的 expire（秒）计算，并提前 5 分钟视为过期，
        以避免在临界点请求失败。失败时记录日志并返回 None。

        Returns:
            成功返回 token 字符串，失败返回 None。
        """
        # 命中缓存直接返回
        if self._token_cache is not None:
            token, expire_at = self._token_cache
            if time.time() < expire_at:
                return token
            # 缓存过期，清理
            self._token_cache = None

        if not self.config.is_configured():
            logger.error("Feishu config not complete, cannot fetch tenant_access_token")
            return None

        raw = self.config.get_raw()
        app_id = raw.get("app_id", "")
        app_secret = raw.get("app_secret", "")
        url = f"{self._get_base_url()}/auth/v3/tenant_access_token/internal"
        payload = {"app_id": app_id, "app_secret": app_secret}

        try:
            response = self._http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Request tenant_access_token failed: {e}")
            return None
        except (ValueError, KeyError) as e:
            logger.error(f"Parse tenant_access_token response failed: {e}")
            return None

        token = data.get("tenant_access_token")
        expire = data.get("expire")
        if not token or not isinstance(expire, int):
            logger.error(f"Invalid tenant_access_token response: {data}")
            return None

        # 提前 5 分钟视为过期
        expire_at = time.time() + max(0, expire - self.TOKEN_EXPIRE_BUFFER)
        self._token_cache = (token, expire_at)
        logger.debug("Fetched new tenant_access_token, expire_in=%ss", expire)
        return token

    def _invalidate_token_cache(self) -> None:
        """清除 token 缓存，下次获取将重新请求。"""
        self._token_cache = None

    # ------------------------------------------------------------------
    # 统一请求方法
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, Any]] = None,
        retry_on_auth: bool = True,
    ) -> httpx.Response:
        """内部统一请求方法。

        自动处理 Authorization 头注入、token 过期重试、网络错误指数退避重试。

        Args:
            method: HTTP 方法（GET/POST 等）。
            path: 相对路径，例如 ``/im/v1/messages``。
            json_body: JSON 请求体。
            params: URL 查询参数。
            headers: 额外请求头。
            files: multipart/form-data 文件字段。
            retry_on_auth: 遇到 token 过期是否自动刷新重试一次。

        Returns:
            :class:`httpx.Response` 对象。即使多次重试仍失败也会返回最后一次
            的 Response 对象；仅在网络异常无法获得响应时抛出最后一个异常。
        """
        url = f"{self._get_base_url()}{path}"
        # 复制调用方传入的 headers，避免污染
        merged_headers: Dict[str, str] = {}
        if headers:
            merged_headers.update(headers)

        is_token_api = self._is_token_api(path)
        # 获取 token 的 API 无需 Authorization 头
        if not is_token_api:
            token = self.get_tenant_access_token()
            if token:
                merged_headers["Authorization"] = f"Bearer {token}"

        last_exception: Optional[Exception] = None
        for attempt in range(self.MAX_RETRY):
            try:
                response = self._http_client.request(
                    method=method,
                    url=url,
                    json=json_body,
                    params=params,
                    headers=merged_headers,
                    files=files,
                )
            except httpx.HTTPError as e:
                last_exception = e
                logger.warning(
                    "HTTP request failed (attempt=%d/%d) method=%s path=%s: %s",
                    attempt + 1, self.MAX_RETRY, method, path, e,
                )
                if attempt < self.MAX_RETRY - 1:
                    # 指数退避：1s, 2s, 4s
                    time.sleep(2 ** attempt)
                    continue
                # 已达最大重试次数
                raise

            # token 过期处理：401 或业务码 99991663
            if retry_on_auth and not is_token_api and self._is_token_expired(response):
                logger.info("Token expired, refreshing and retrying once")
                self._invalidate_token_cache()
                new_token = self.get_tenant_access_token()
                if new_token:
                    merged_headers["Authorization"] = f"Bearer {new_token}"
                    # 仅重试一次
                    try:
                        response = self._http_client.request(
                            method=method,
                            url=url,
                            json=json_body,
                            params=params,
                            headers=merged_headers,
                            files=files,
                        )
                    except httpx.HTTPError as e:
                        last_exception = e
                        logger.error(
                            "Retry after token refresh failed method=%s path=%s: %s",
                            method, path, e,
                        )
                        raise
                return response

            return response

        # 理论上不可达，兜底
        if last_exception:
            raise last_exception
        raise httpx.HTTPError("Unknown request failure")

    def _is_token_expired(self, response: httpx.Response) -> bool:
        """判断响应是否表示 token 过期。

        Args:
            response: :class:`httpx.Response` 对象。

        Returns:
            token 过期返回 True。
        """
        if response.status_code == 401:
            return True
        # 飞书业务层 token 过期错误码
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            return False
        code = data.get("code")
        return code == self.TOKEN_EXPIRED_CODE

    # ------------------------------------------------------------------
    # 消息发送
    # ------------------------------------------------------------------
    def send_text_message(
        self, receive_id: str, receive_id_type: str, text: str
    ) -> Dict[str, Any]:
        """发送文本消息。

        Args:
            receive_id: 接收者 ID（open_id / user_id / union_id / email / chat_id）。
            receive_id_type: 接收者 ID 类型。
            text: 文本内容。

        Returns:
            ``{"success": bool, "data": ..., "error": str}``。
        """
        content = json.dumps({"text": text}, ensure_ascii=False)
        return self._send_message(receive_id, receive_id_type, "text", content)

    def send_image_message(
        self, receive_id: str, receive_id_type: str, image_key: str
    ) -> Dict[str, Any]:
        """发送图片消息。

        Args:
            receive_id: 接收者 ID。
            receive_id_type: 接收者 ID 类型。
            image_key: 已上传到飞书的 image_key。

        Returns:
            ``{"success": bool, "data": ..., "error": str}``。
        """
        content = json.dumps({"image_key": image_key}, ensure_ascii=False)
        return self._send_message(receive_id, receive_id_type, "image", content)

    def _send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: str,
    ) -> Dict[str, Any]:
        """发送消息的统一实现。"""
        path = "/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }
        try:
            response = self._request("POST", path, json_body=payload, params=params)
        except httpx.HTTPError as e:
            logger.error("send_message network error: %s", e)
            return {"success": False, "data": None, "error": f"network error: {e}"}

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            return {
                "success": False,
                "data": None,
                "error": f"invalid response (status={response.status_code})",
            }

        # 飞书成功响应 code == 0
        if response.status_code == 200 and data.get("code") == 0:
            return {"success": True, "data": data, "error": ""}
        msg = data.get("msg") or data.get("message") or "unknown error"
        logger.error(
            "send_message failed status=%s code=%s msg=%s",
            response.status_code, data.get("code"), msg,
        )
        return {"success": False, "data": data, "error": str(msg)}

    def reply_message(
        self, message_id: str, content: str, msg_type: str = "text"
    ) -> Dict[str, Any]:
        """回复指定消息。

        Args:
            message_id: 被回复的消息 ID。
            content: 消息内容（已 JSON 序列化字符串）。
            msg_type: 消息类型，默认 ``text``。

        Returns:
            ``{"success": bool, "data": ..., "error": str}``。
        """
        path = f"/im/v1/messages/{message_id}/reply"
        payload = {"msg_type": msg_type, "content": content}
        try:
            response = self._request("POST", path, json_body=payload)
        except httpx.HTTPError as e:
            logger.error("reply_message network error: %s", e)
            return {"success": False, "data": None, "error": f"network error: {e}"}

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            return {
                "success": False,
                "data": None,
                "error": f"invalid response (status={response.status_code})",
            }

        if response.status_code == 200 and data.get("code") == 0:
            return {"success": True, "data": data, "error": ""}
        msg = data.get("msg") or data.get("message") or "unknown error"
        logger.error(
            "reply_message failed status=%s code=%s msg=%s",
            response.status_code, data.get("code"), msg,
        )
        return {"success": False, "data": data, "error": str(msg)}

    # ------------------------------------------------------------------
    # 图片处理
    # ------------------------------------------------------------------
    def download_image(self, message_id: str, image_key: str) -> Optional[bytes]:
        """下载飞书图片。

        Args:
            message_id: 触发下载的消息 ID（保留参数，飞书 download API 当前
                仅依赖 image_key，但保留以便未来扩展鉴权场景）。
            image_key: 图片资源 key。

        Returns:
            成功返回图片二进制数据，失败返回 None。
        """
        path = f"/im/v1/images/{image_key}"
        try:
            response = self._request("GET", path)
        except httpx.HTTPError as e:
            logger.error("download_image network error: %s", e)
            return None

        if response.status_code == 200:
            # 飞书图片下载接口成功时直接返回二进制流
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                # 极少数情况下错误也返回 200，需进一步判断
                try:
                    data = response.json()
                    if data.get("code") != 0:
                        logger.error(
                            "download_image biz failed code=%s msg=%s",
                            data.get("code"), data.get("msg"),
                        )
                        return None
                except (ValueError, json.JSONDecodeError):
                    pass
            return response.content

        logger.error(
            "download_image failed status=%s image_key=%s",
            response.status_code, image_key,
        )
        return None

    def upload_image(self, image_path: str, image_type: str = "message") -> Optional[str]:
        """上传图片到飞书，返回 image_key。

        Args:
            image_path: 本地图片文件路径。
            image_type: 图片类型，默认 ``message``（用于消息发送）。

        Returns:
            成功返回 image_key 字符串，失败返回 None。
        """
        try:
            with open(image_path, "rb") as f:
                file_bytes = f.read()
        except OSError as e:
            logger.error("read image file failed path=%s: %s", image_path, e)
            return None

        filename = os.path.basename(image_path) or "image"

        path = "/im/v1/images"
        params = {"image_type": image_type}
        files = {
            "image_type": (None, image_type),
            "image": (filename, file_bytes),
        }
        try:
            response = self._request("POST", path, params=params, files=files)
        except httpx.HTTPError as e:
            logger.error("upload_image network error: %s", e)
            return None

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            logger.error(
                "upload_image invalid response status=%s", response.status_code
            )
            return None

        if response.status_code == 200 and data.get("code") == 0:
            image_key = data.get("data", {}).get("image_key")
            if image_key:
                return image_key
            logger.error("upload_image missing image_key in response: %s", data)
            return None

        logger.error(
            "upload_image failed status=%s code=%s msg=%s",
            response.status_code, data.get("code"), data.get("msg"),
        )
        return None

    # ------------------------------------------------------------------
    # 资源清理
    # ------------------------------------------------------------------
    def close(self) -> None:
        """关闭内部 HTTP 客户端，释放连接资源。"""
        try:
            self._http_client.close()
        except Exception:
            pass

    def __del__(self):
        # 兜底释放 httpx 客户端
        try:
            self.close()
        except Exception:
            pass
