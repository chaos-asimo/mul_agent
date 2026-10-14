# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - skillmd 技能的代理式执行器

背景：标准 Agent Skill（如 luobo-ppt）是多步骤工作流——模型需要反复运行
scripts/ 下的脚本（带命令行参数）、读写中间文件、根据输出迭代。单发
[SKILL_CALL] → 一次 LLM 调用 的机制无法驱动这类技能。

本模块实现有界代理循环：
1. materialize：把技能的 scripts/references 落盘（脚本互相 import 需要真实文件）
2. 多轮循环：LLM 输出 ```bash 代码块 → 系统逐条安全执行（仅 python 命令、
   无 shell 元字符、$S/$W 变量替换）→ 输出回传 → 直到模型不再给命令
3. 收集工作目录中的产物（白名单扩展名）→ 归档到用户产物目录 → 真实下载链接

安全约束：只允许以 python 开头的命令；拒绝 & | ; ` $ < > 等 shell 元字符；
subprocess shell=False；每条命令超时、总时限、最大轮数均有上限。
"""
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from lobster_mu.db import BASE_DIR
from lobster_mu.paths import files_dir, gen_filename

MAX_ROUNDS = 15
MAX_CMDS_PER_ROUND = 4
CMD_TIMEOUT = 180          # 单条命令超时（秒）
TOTAL_DEADLINE = 9 * 60    # 整个技能执行总时限（秒）
OUT_TAIL = 3000            # 回传给模型的 stdout 最大字符
ERR_TAIL = 1500

# 产物归档白名单（与 script_service 对齐，另加技能常用中间产物）
_ARTIFACT_EXT = {'.pptx', '.docx', '.xlsx', '.xls', '.pdf', '.png', '.jpg',
                 '.jpeg', '.gif', '.csv', '.md', '.html', '.txt', '.zip'}
_FORBIDDEN = re.compile(r'\$\(|\$\{|`|&&|\|\|')  # 仅拒绝命令替换/连接符；; 在 python -c 代码中合法，shell=False 下其余元字符只是普通 argv
_BASH_BLOCK = re.compile(r'```(?:bash|shell|sh|cmd|console)?\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)


def materialize(user_id: int, skill: Dict[str, Any]) -> str:
    """把技能的 scripts/references 落盘到 data/mu_skill_files/{uid}/{sid}/（幂等，内容变化才覆写）"""
    cfg = skill.get('config') or {}
    sid = skill.get('skill_id') or 'unknown'
    root = os.path.join(BASE_DIR, 'data', 'mu_skill_files', str(user_id), sid)
    for sub, mapping in (('scripts', cfg.get('scripts') or {}), ('references', cfg.get('references') or {})):
        d = os.path.join(root, sub)
        os.makedirs(d, exist_ok=True)
        for name, content in mapping.items():
            if not isinstance(content, str):
                continue
            p = os.path.join(d, os.path.basename(name))
            try:
                if os.path.exists(p):
                    with open(p, encoding='utf-8', errors='ignore') as f:
                        if f.read() == content:
                            continue
                with open(p, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
            except OSError:
                pass
    return root


def _extract_commands(reply: str) -> List[str]:
    """从模型回复的 ```bash 代码块中提取命令行（忽略注释与空行）"""
    cmds = []
    for block in _BASH_BLOCK.findall(reply or ''):
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                cmds.append(line)
    return cmds


def _run_command(cmd: str, scripts_dir: str, work_dir: str) -> str:
    """安全执行一条命令。仅允许 python 命令，shell=False，拒绝命令替换/连接符。"""
    raw = cmd.strip()
    if _FORBIDDEN.search(raw):
        return f"$ {raw}\n(已拒绝：含 shell 命令替换/连接符，请拆成多条纯 python 命令)"
    # $S/$W 后的反斜杠先归一为正斜杠，再用正斜杠路径替换（posix 解析不兼容 Windows 反斜杠转义）
    raw_n = raw.replace('$S\\', '$S/').replace('$W\\', '$W/')
    real = raw_n.replace('$S', scripts_dir.replace('\\', '/')).replace('$W', work_dir.replace('\\', '/'))
    try:
        args = shlex.split(real, posix=True)
    except ValueError as e:
        return f"$ {raw}\n(命令解析失败: {e})"
    args = [a for a in args if a]
    if not args or args[0] not in ('python', 'python3', 'py'):
        return f"$ {raw}\n(已拒绝：仅允许以 python 开头的命令)"
    args[0] = sys.executable
    # 自动安装的依赖在 packages/（不在 venv），子进程需显式注入 PYTHONPATH
    env = dict(os.environ)
    packages_dir = os.path.join(BASE_DIR, 'packages')
    env['PYTHONPATH'] = packages_dir + os.pathsep + env.get('PYTHONPATH', '')
    try:
        p = subprocess.run(args, cwd=work_dir, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=CMD_TIMEOUT, env=env)
        out = (p.stdout or '')[-OUT_TAIL:]
        if p.stderr:
            out += ('\n' if out else '') + '[stderr]\n' + p.stderr[-ERR_TAIL:]
        return f"$ {raw}\n(exit {p.returncode})\n{out.strip() or '(无输出)'}"
    except subprocess.TimeoutExpired:
        return f"$ {raw}\n(执行超时 {CMD_TIMEOUT}s，已终止)"
    except Exception as e:
        return f"$ {raw}\n(执行异常: {e})"


def _collect_artifacts(user_id: int, work_dir: str) -> List[Dict[str, Any]]:
    """收集工作目录中的产物文件，归档到用户产物目录，返回下载信息"""
    target_dir = files_dir(user_id)
    generated = []
    for dirpath, _dirs, names in os.walk(work_dir):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext not in _ARTIFACT_EXT or name == 'input_material.md':
                continue
            src = os.path.join(dirpath, name)
            try:
                new_name = gen_filename(name)
                dst = os.path.join(target_dir, new_name)
                shutil.copy2(src, dst)
                generated.append({
                    'name': new_name,
                    'original_name': os.path.relpath(src, work_dir),
                    'size': os.path.getsize(dst),
                    'download_url': f"/api/lobster-mu/script/files/download/{new_name}",
                })
            except OSError:
                pass
    return generated


def run_skillmd(user_id: int, skill: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """代理式执行 skillmd 技能：多轮 LLM + 受限命令执行。任何异常都捕获返回。"""
    from lobster_mu.skill_store import _call_llm

    cfg = skill.get('config') or {}
    body = (cfg.get('skillmd_body') or '').strip()
    if not body:
        return {'success': False, 'error': '技能内容为空'}

    params = dict(params or {})
    material_text = str(params.pop('_material', '') or '')[:24000]
    task_input = str(params.get('input') or '').strip()
    if not task_input:
        task_input = '\n'.join(f'{k}: {v}' for k, v in params.items() if not str(k).startswith('_')).strip()
    if not task_input:
        task_input = '按技能说明完成用户的请求。'

    try:
        root = materialize(user_id, skill)
    except Exception as e:
        return {'success': False, 'error': f'技能脚本落盘失败: {e}'}
    scripts_dir = os.path.join(root, 'scripts')

    work_dir = os.path.join(files_dir(user_id), 'skill_work',
                            f"{(skill.get('skill_id') or 'skill')[:8]}_{int(time.time())}")
    os.makedirs(work_dir, exist_ok=True)
    if material_text:
        try:
            with open(os.path.join(work_dir, 'input_material.md'), 'w', encoding='utf-8') as f:
                f.write(material_text)
        except OSError:
            material_text = ''

    system = (
        body
        + "\n\n【运行环境约定（本系统适配层，优先于正文中的环境假设）】\n"
        + f"- 运行环境为 Windows；本 skill 的 scripts 目录 $S = {scripts_dir}\n"
        + f"- 本次工作目录 $W = {work_dir}（已创建，可直接读写）\n"
        + "- 你不能直接执行命令：把要执行的命令放进 ```bash 代码块（每行一条），系统会逐条执行并把 stdout/stderr 回传给你\n"
        + "- 只允许以 python 开头的命令（用 python 而不是 python3）；禁止使用管道、重定向、命令连接符\n"
        + "- 命令中可使用 $S 与 $W 变量，系统会替换为上述真实路径\n"
        + ("- 用户提供的素材已保存为 $W/input_material.md，需要分析素材时用 --file 指向它\n" if material_text else "")
        + "- 交付文件（如 .pptx）必须生成在 $W 目录内（含子目录），系统会自动归档并提供下载\n"
        + "- 全部完成后，回复一段不含任何代码块的总结，说明产物位置与关键选择；中途不要用总结代替执行\n"
    )

    transcript = f"【任务】\n{task_input}\n\n请开始。第一步先输出环境自检命令。"
    deadline = time.time() + TOTAL_DEADLINE
    final_text = ''
    rounds_used = 0
    try:
        for rnd in range(1, MAX_ROUNDS + 1):
            rounds_used = rnd
            if time.time() > deadline:
                final_text += '\n\n(执行总时限到达，已中断)'
                break
            reply = _call_llm(transcript, system=system)
            final_text = reply or ''
            cmds = _extract_commands(reply)
            if not cmds:
                break
            outputs = [_run_command(c, scripts_dir, work_dir) for c in cmds[:MAX_CMDS_PER_ROUND]]
            if len(cmds) > MAX_CMDS_PER_ROUND:
                outputs.append(f"(本轮仅执行前 {MAX_CMDS_PER_ROUND} 条，其余请在下一轮重新给出)")
            transcript += (
                f"\n\n【你的第 {rnd} 轮回复】\n{reply}\n\n【命令执行输出】\n"
                + '\n\n'.join(outputs)
                + '\n\n请根据输出继续下一步；全部完成时回复不含代码块的总结。'
            )
    except Exception as e:
        return {'success': False, 'error': f'技能代理执行异常: {e}'}

    generated = _collect_artifacts(user_id, work_dir)
    result = (final_text or '').strip()
    if generated:
        lines = ['', '【生成的文件】（下载链接必须原样引用，不得改动文件名）']
        for f in generated:
            lines.append(f"- {f['original_name']}: {f['download_url']}")
        result = (result + '\n' + '\n'.join(lines)).strip()
    result += f"\n\n(技能代理执行 {rounds_used} 轮)"
    return {'success': True, 'result': result, 'generated_files': generated}
