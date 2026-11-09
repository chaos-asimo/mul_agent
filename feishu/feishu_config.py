"""飞书配置管理模块

负责加载、保存和管理飞书（Lark）接入相关配置。配置以 JSON 文件形式持久化存储，
敏感字段（app_secret、encrypt_key）在通过 get() 方法返回时会自动脱敏，
需要获取原始配置请使用 get_raw() 方法（仅供内部使用，例如调用飞书 API）。
"""
import os
import json
from typing import Optional, Dict, Any


class FeishuConfig:
    """飞书配置管理类。

    配置文件默认位于项目 data 目录下的 feishu_config.json。支持加载、保存、
    部分更新以及脱敏读取等操作。配置文件目录不存在时会自动创建。
    """

    # 敏感字段列表：在 get() 中会被替换为 '***'
    SENSITIVE_FIELDS = ('app_secret', 'encrypt_key')

    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器。

        Args:
            config_path: 配置文件路径。为 None 时使用默认路径
                （项目根目录下 data/feishu_config.json）。
        """
        if config_path is None:
            # 默认配置文件路径：<项目根>/data/feishu_config.json
            config_path = os.path.join(
                os.path.dirname(__file__), '..', 'data', 'feishu_config.json'
            )
        self.config_path = os.path.abspath(config_path)
        # 确保配置文件所在目录存在
        config_dir = os.path.dirname(self.config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        # 加载配置到内存
        self._config: Dict[str, Any] = self.load()

    def _default_config(self) -> Dict[str, Any]:
        """返回默认配置字典。

        Returns:
            包含所有字段默认值的配置字典。
        """
        return {
            'app_id': '',                # 飞书应用 App ID，格式 cli_xxx
            'app_secret': '',            # 飞书应用 App Secret
            'encrypt_key': '',           # 事件加密密钥（可选，webhook模式）
            'verification_token': '',    # 事件校验令牌（webhook模式）
            'bot_name': 'Lobster Bot',   # 机器人名称
            'domain': 'feishu',          # 域名：feishu（中国版）或 lark（国际版）
            'event_mode': 'long_connection',  # 事件接收模式：webhook 或 long_connection
            'dm_policy': 'open',         # 私聊策略：open/allowlist/blocklist
            'allow_list': [],            # 允许名单（open_id 列表）
            'block_list': [],            # 阻止名单（open_id 列表）
            'handle_groups': True,       # 是否处理群聊消息
            'handle_dms': True,          # 是否处理私聊消息
            'trigger_on_mention': True,  # 群聊是否仅在 @机器人 时触发
            'enabled': False,            # 是否启用飞书接入
        }

    def load(self) -> Dict[str, Any]:
        """从文件加载配置。

        若配置文件不存在，则使用默认配置并写入文件；若文件存在但解析失败，
        则回退到默认配置。加载后会与默认配置合并以补齐缺失字段。

        Returns:
            加载后的完整配置字典。
        """
        if not os.path.exists(self.config_path):
            # 配置文件不存在时创建默认配置
            default_config = self._default_config()
            self._write_file(default_config)
            return default_config
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            # 配置文件损坏或无法读取时回退到默认配置
            config = self._default_config()
        # 与默认配置合并，补齐可能缺失的字段
        merged = self._default_config()
        merged.update(config)
        return merged

    def _write_file(self, config: Dict[str, Any]) -> None:
        """将配置写入文件（内部方法）。

        Args:
            config: 要写入的配置字典。
        """
        config_dir = os.path.dirname(self.config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def save(self, config: Dict[str, Any]) -> bool:
        """保存配置到文件。

        保存前会与默认配置合并以校验字段完整性，缺失的字段会被自动补齐为默认值。

        Args:
            config: 要保存的配置字典。

        Returns:
            保存成功返回 True，失败返回 False。
        """
        try:
            # 以默认配置为底，合并传入的配置，保证字段完整性
            merged = self._default_config()
            merged.update(config)
            self._write_file(merged)
            self._config = merged
            return True
        except (OSError, TypeError, ValueError):
            return False

    def get(self) -> Dict[str, Any]:
        """获取当前配置（脱敏后）。

        敏感字段（app_secret、encrypt_key）若非空则替换为 '***'。
        适合用于对外展示、API 响应或日志记录。

        Returns:
            脱敏后的配置字典副本。
        """
        masked = dict(self._config)
        for field_name in self.SENSITIVE_FIELDS:
            value = masked.get(field_name)
            if value:
                masked[field_name] = '***'
        return masked

    def get_raw(self) -> Dict[str, Any]:
        """获取原始配置（不脱敏）。

        警告：返回的字典包含明文的敏感信息，仅供内部使用（如调用飞书 API、
        计算签名等），不应直接对外暴露或写入日志。

        Returns:
            原始配置字典副本。
        """
        return dict(self._config)

    def is_configured(self) -> bool:
        """检查是否已配置必要字段。

        必要字段为 app_id 和 app_secret，两者均不能为空字符串。

        Returns:
            已配置返回 True，否则返回 False。
        """
        app_id = self._config.get('app_id', '')
        app_secret = self._config.get('app_secret', '')
        if isinstance(app_id, str):
            app_id = app_id.strip()
        if isinstance(app_secret, str):
            app_secret = app_secret.strip()
        return bool(app_id and app_secret)

    def update(self, partial_config: Dict[str, Any]) -> Dict[str, Any]:
        """部分更新配置，自动合并到现有配置。

        仅更新 partial_config 中提供的字段，其他字段保持不变。
        更新后会自动保存到文件。

        Args:
            partial_config: 包含待更新字段的字典。

        Returns:
            更新后脱敏的配置字典。
        """
        merged = dict(self._config)
        merged.update(partial_config)
        self.save(merged)
        return self.get()
