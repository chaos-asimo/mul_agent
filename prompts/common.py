# -*- coding: utf-8 -*-
"""跨子系统共享的提示词常量（纯常量，禁止 import 业务模块，避免循环导入）。"""

# 龙虾Claw 通用身份
ASSISTANT_IDENTITY = "你是龙虾Claw，一个强大的AI智能体助手。"

# 定时任务（多用户 cron_runner 与旧版 cron/task_executor 共用）
CRON_TASK_SYSTEM_PROMPT = "你是龙虾Claw，一个强大的AI智能体助手。请完成以下定时任务："

# 脚本命名助手
SCRIPT_NAME_SYSTEM_PROMPT = "你是一个命名助手，请严格按照格式返回。"

# 模型连通性测试提示
MODEL_TEST_IMAGE_PROMPT = "A beautiful landscape with mountains and river, digital art style"
MODEL_TEST_TEXT_PROMPT = "Hi, please respond with 'OK' if you can read this."
