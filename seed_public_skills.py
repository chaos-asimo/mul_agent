# -*- coding: utf-8 -*-
"""
公共技能种子脚本（幂等，可重复执行）。

用途：部署到新环境后，初始化一组默认公共技能，让所有用户开箱即用。
执行：在应用根目录运行
    python -B seed_public_skills.py
说明：
  - 会先初始化数据库（自动建 mu_skills 表）。
  - 按“技能名”去重：已存在的公共技能跳过，不重复创建。
  - 全部创建为公共技能（user_id=0, is_public=1），普通用户只读可用。
  - 仅写库，不触发网络/模型调用，可离线执行。
"""
import os
import sys

# 确保能 import 本项目模块（无论从哪个目录启动）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lobster_mu.db as db           # noqa: E402
import lobster_mu.skill_store as ss  # noqa: E402


# 默认公共技能定义：覆盖四种执行器（llm / script / search / api）
DEFAULT_PUBLIC_SKILLS = [
    # ---------------- LLM 类 ----------------
    {
        "name": "文本润色",
        "description": "对给定文本进行润色，使其更通顺、专业、自然，保持原意。",
        "executor": "llm",
        "prompt_template": "请对以下文本进行润色，使其表达更通顺、专业、自然，保持原意，直接输出润色后的文本，不要加解释：\n{text}",
        "parameters": [{"name": "text", "required": True, "description": "待润色的文本"}],
    },
    {
        "name": "翻译助手",
        "description": "把文本翻译成指定语言（默认英文）。",
        "executor": "llm",
        "prompt_template": "请把下面的文本翻译成{lang}，只输出译文，不要解释：\n{text}",
        "parameters": [
            {"name": "text", "required": True, "description": "待翻译文本"},
            {"name": "lang", "required": False, "description": "目标语言，默认 英文"},
        ],
    },
    {
        "name": "摘要总结",
        "description": "把长文本压缩成简洁的要点摘要。",
        "executor": "llm",
        "prompt_template": "请阅读以下文本，输出不超过 5 条的要点摘要，每条一行：\n{text}",
        "parameters": [{"name": "text", "required": True, "description": "待总结文本"}],
    },
    {
        "name": "代码解释",
        "description": "用通俗语言解释一段代码的作用与逻辑。",
        "executor": "llm",
        "prompt_template": "请用通俗的语言解释下面这段代码的作用、关键逻辑和注意事项：\n```\n{code}\n```",
        "parameters": [{"name": "code", "required": True, "description": "代码片段"}],
    },
    {
        "name": "邮件撰写",
        "description": "根据主题与语气，生成一封得体的邮件。",
        "executor": "llm",
        "prompt_template": "请帮我写一封{tone}语气的邮件，主题是「{topic}」，包含称呼、正文、结尾署名，语言自然得体。",
        "parameters": [
            {"name": "topic", "required": True, "description": "邮件主题/事由"},
            {"name": "tone", "required": False, "description": "语气，如 正式/友好/委婉，默认 正式"},
        ],
    },
    {
        "name": "标题生成",
        "description": "为一段内容生成多个吸引人的标题。",
        "executor": "llm",
        "prompt_template": "请为以下内容生成 5 个简洁有力、吸引人的标题，每个一行：\n{text}",
        "parameters": [{"name": "text", "required": True, "description": "正文内容"}],
    },
    {
        "name": "创意头脑风暴",
        "description": "围绕一个主题发散出多个创意点子。",
        "executor": "llm",
        "prompt_template": "请围绕「{topic}」这个主题，发散思考，给出 8 个有创意的点子或角度，每个一行。",
        "parameters": [{"name": "topic", "required": True, "description": "头脑风暴主题"}],
    },
    # ---------------- Script 类 ----------------
    {
        "name": "随机密码生成器",
        "description": "生成一个 16 位的强随机密码（字母+数字+符号）。",
        "executor": "script",
        "script": (
            "import random, string\n"
            "chars = string.ascii_letters + string.digits + '!@#$%^&*'\n"
            "rng = random.SystemRandom()\n"
            "pwd = ''.join(rng.choice(chars) for _ in range(16))\n"
            "print(pwd)\n"
        ),
        "parameters": [],
    },
    # ---------------- Search 类 ----------------
    {
        "name": "联网搜索",
        "description": "用关键词在网上搜索并返回结果摘要。",
        "executor": "search",
        "parameters": [
            {"name": "query", "required": True, "description": "搜索关键词"},
            {"name": "num_results", "required": False, "description": "返回条数，默认 5"},
        ],
    },
    # ---------------- API 类 ----------------
    {
        "name": "公网IP查询",
        "description": "查询当前服务器的公网 IP 地址（调用 ipify 公共 API）。",
        "executor": "api",
        "api_endpoint": "https://api.ipify.org?format=json",
        "parameters": [],
    },
]


def main():
    db.init_db()
    existing = {s["name"] for s in ss.list_public()}
    created, skipped, failed = [], [], []
    for skill in DEFAULT_PUBLIC_SKILLS:
        if skill["name"] in existing:
            skipped.append(skill["name"])
            continue
        res = ss.add(0, skill, is_public=True, is_admin=True)
        if res.get("success"):
            created.append(skill["name"])
        else:
            failed.append((skill["name"], res.get("error")))

    print("=" * 56)
    print("公共技能种子执行完成")
    print("=" * 56)
    print(f"  新建 : {len(created)}  -> {', '.join(created) if created else '(无)'}")
    print(f"  跳过 : {len(skipped)}  -> {', '.join(skipped) if skipped else '(无)'}")
    for name, err in failed:
        print(f"  失败 : {name} -> {err}")
    print("-" * 56)
    print(f"当前公共技能总数: {len(ss.list_public())}")
    for s in ss.list_public():
        print(f"  [{s['executor']}] {s['name']}  enabled={s['enabled']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
