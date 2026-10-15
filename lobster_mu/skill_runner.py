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

MAX_ROUNDS = 30            # luobo-ppt 全流程（自检→分析→写deck→大纲→风格→版式→出图）需要十余轮命令
MAX_CMDS_PER_ROUND = 4
MAX_NUDGES = 2             # 模型未产成交付文件就试图总结时，最多催促继续的次数
CMD_TIMEOUT = 180          # 单条命令超时（秒）
TOTAL_DEADLINE = 9 * 60    # 整个技能执行总时限（秒）
OUT_TAIL = 3000            # 回传给模型的 stdout 最大字符
ERR_TAIL = 1500

# 产物归档白名单（与 script_service 对齐，另加技能常用中间产物）
_ARTIFACT_EXT = {'.pptx', '.docx', '.xlsx', '.xls', '.pdf', '.png', '.jpg',
                 '.jpeg', '.gif', '.csv', '.md', '.html', '.txt', '.zip'}
# 交付文件扩展名（用于判断模型是否可以收尾总结）；tuple 兼容 endswith 与 in 两种用法
_DELIVERABLE_EXT = ('.pptx', '.docx', '.xlsx', '.pdf')
_FORBIDDEN = re.compile(r'\$\(|\$\{|`|&&|\|\|')  # 仅拒绝命令替换/连接符；; 在 python -c 代码中合法，shell=False 下其余元字符只是普通 argv
_BASH_BLOCK = re.compile(r'```(?:bash|shell|sh|cmd|console)?\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)

# 产出关键文件（用于判断模型是否进入了真正的产出阶段，而非烧轮次在探索/查询上）
_KEY_OUTPUT_FILES = ('deck.json', 'style.json', 'plan.json', 'beautified.pptx', 'pipeline')
# 探索/查询类命令（命中则视为低价值轮次）
_EXPLORE_CMD_HINTS = ('layout_info', 'show_diff', 'print(', 'findstr', 'type $S/references', 'type $W/input_material')


def _phase_check(work_dir: str) -> str:
    """当前执行阶段：explore(仅探索/查询) | drafting(写了中间文件) | building(开始生成) | delivering(有交付物)"""
    files = set()
    for root, _d, names in os.walk(work_dir):
        for n in names:
            files.add(n.lower())
    if any(n.lower().endswith(_DELIVERABLE_EXT) for n in files):
        return 'delivering'
    if any('deck.json' in n or 'style.json' in n or 'plan.json' in n for n in files):
        return 'building'
    return 'explore'


def _is_explore_cmd(cmd: str) -> bool:
    """判断命令是否是低价值的探索/查询类"""
    c = (cmd or '').lower()
    return any(h in c for h in _EXPLORE_CMD_HINTS)


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
    """从模型回复的 ```bash 代码块中提取完整命令（处理 python -c 多行引号闭合）。
    逐行扫描：遇到以 python/py 开头的行，若后续引号/括号未闭合，则继续向后合并直到闭合。"""
    cmds = []
    for block in _BASH_BLOCK.findall(reply or ''):
        lines = [l.strip() for l in block.splitlines() if l.strip() and not l.strip().startswith('#')]
        i = 0
        while i < len(lines):
            line = lines[i]
            # 判断是否是完整的 python 命令（引号/括号/方括号都闭合）
            opens = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
            closed = True
            stack = []
            # 跳过引号内的内容
            in_q = None
            esc = False
            for ch in line:
                if esc:
                    esc = False; continue
                if ch == '\\':
                    esc = True; continue
                if in_q:
                    if ch == in_q: in_q = None
                    continue
                if ch in ('"', "'"):
                    in_q = ch; continue
                if ch in opens:
                    stack.append(opens[ch])
                elif stack and ch == stack[-1]:
                    stack.pop()
            if stack or in_q:
                closed = False
            if line.startswith(('python ', 'python3 ', 'py ')) and not closed and i + 1 < len(lines):
                # 合并下一行
                line += ' ' + lines[i + 1]
                i += 1
                # 重新检测闭合
                closed = True; stack = []; in_q = None; esc = False
                for ch in line:
                    if esc: esc = False; continue
                    if ch == '\\': esc = True; continue
                    if in_q:
                        if ch == in_q: in_q = None
                        continue
                    if ch in ('"', "'"): in_q = ch; continue
                    if ch in opens: stack.append(opens[ch])
                    elif stack and ch == stack[-1]: stack.pop()
                if stack or in_q:
                    closed = False
            cmds.append(line)
            i += 1
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


def _has_deliverable(work_dir: str) -> bool:
    """工作目录中是否已存在交付文件（.pptx/.docx/.xlsx/.pdf）"""
    for dirpath, _dirs, names in os.walk(work_dir):
        for name in names:
            if os.path.splitext(name)[1].lower() in _DELIVERABLE_EXT:
                return True
    return False


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


def _emit(progress, text: str) -> None:
    """推送执行进度给上层（回调异常静默忽略，不影响主流程）"""
    if progress:
        try:
            progress(text)
        except Exception:
            pass


def _short(s: str, n: int = 120) -> str:
    """压成单行短摘要"""
    s = ' '.join((s or '').split())
    return s[:n] + ('…' if len(s) > n else '')


def run_skillmd(user_id: int, skill: Dict[str, Any], params: Dict[str, Any],
                progress=None) -> Dict[str, Any]:
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

    # 工作目录放在私有 data/ 区（不经 web/static 直接暴露），且按用户隔离
    work_dir = os.path.join(BASE_DIR, 'data', 'mu_skill_work', str(user_id),
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
        + "\n\n【轮次预算约束】（本技能代理最多执行 30 轮命令，轮次非常宝贵，请节约使用）\n"
        + "- 禁止逐个查询 layout_info / schema / style_previews 等参考文档的完整内容——"
          "请先快速读 references/generate.md 了解规则框架，然后直接写 deck.json 和 style.json。"
          "遇到某个版式的字段细节不确定时，只查那一个版式一次，不要全查\n"
        + "- 建议路径：环境自检(1轮) → 读规则(1轮) → 写 deck.json + style.json(1-2轮) → outline_check(1轮) → plan_deck(1轮) → pipeline(1轮) → QA修复(1-3轮)\n"
        + "- 如果第 6 轮结束还没写出 deck.json，系统会强制催促你停止探索，进入产出\n"
        + "- 每个 python -c 命令必须是单行（用 json.dumps 把多行 JSON 压成一行），不要在 -c 字符串里写换行\n"
    )

    transcript = f"【任务】\n{task_input}\n\n请开始。第一步先输出环境自检命令。"
    deadline = time.time() + TOTAL_DEADLINE
    final_text = ''
    rounds_used = 0
    nudges = 0
    end_reason = 'rounds'
    explore_rounds = 0  # 连续的低价值（探索/查询）轮次
    forced_phase_warned = {'build': False, 'deliver': False}
    try:
        for rnd in range(1, MAX_ROUNDS + 1):
            rounds_used = rnd
            if time.time() > deadline:
                final_text += '\n\n(执行总时限到达，已中断)'
                end_reason = 'deadline'
                break
            reply = _call_llm(transcript, system=system)
            final_text = reply or ''
            cmds = _extract_commands(reply)
            if not cmds:
                # 模型想收尾：交付文件已生成才允许结束；否则催促继续（防止"假完成"）
                if _has_deliverable(work_dir) or nudges >= MAX_NUDGES:
                    end_reason = 'completed'
                    break
                nudges += 1
                _emit(progress, f"⚠️ 第{rnd}轮：模型未给出命令且尚无交付文件，系统催促继续（{nudges}/{MAX_NUDGES}）\n")
                transcript += (
                    f"\n\n【你的第 {rnd} 轮回复】\n{reply}\n\n【系统提示】\n"
                    "工作目录中还没有任何交付文件（.pptx/.docx/.xlsx/.pdf），任务尚未完成，"
                    "不能总结收尾。请继续输出 ```bash 命令完成剩余步骤（写出内容文件并运行生成/渲染脚本），"
                    "直到交付文件真实存在于 $W 中。"
                )
                continue
            plan = cmds[:MAX_CMDS_PER_ROUND]
            outputs = []
            for k, c in enumerate(plan, 1):
                outp = _run_command(c, scripts_dir, work_dir)
                outputs.append(outp)
                # 每条命令执行完即时推送进度：命令 + 退出码 + 输出摘要
                parts = outp.split('\n', 2)
                exit_line = parts[1] if len(parts) > 1 else ''
                snippet = _short(parts[2]) if len(parts) > 2 else ''
                _emit(progress, f"▶ 第{rnd}轮 · 命令 {k}/{len(plan)}：{_short(c, 100)}\n↳ {exit_line}  {snippet}\n")
            if len(cmds) > MAX_CMDS_PER_ROUND:
                outputs.append(f"(本轮仅执行前 {MAX_CMDS_PER_ROUND} 条，其余请在下一轮重新给出)")
            # 阶段检测 + 强制催促
            phase = _phase_check(work_dir)
            all_explore = all(_is_explore_cmd(c) for c in plan)
            if all_explore:
                explore_rounds += 1
            else:
                explore_rounds = 0
            # 催促 1：第 6 轮还在 explore 阶段
            if rnd >= 6 and phase == 'explore' and not forced_phase_warned['build']:
                forced_phase_warned['build'] = True
                _emit(progress, f"🚨 第{rnd}轮仍处于探索阶段（无 deck.json/style.json），系统强制催促进入产出\n")
                transcript += (
                    f"\n\n【系统强制提示 · 第 {rnd} 轮】\n"
                    "你已经花费了至少 6 轮在探索/查询参考文档上，但还没有写出任何产出文件。\n"
                    "立即停止查询！请直接写 deck.json（1 行 python 命令）和 style.json，\n"
                    "然后跑 outline_check → plan_deck → pipeline，尽快生成 .pptx 交付物。"
                )
                continue
            # 催促 2：第 12 轮还没进入 building 阶段
            if rnd >= 12 and phase != 'building' and not forced_phase_warned['deliver']:
                forced_phase_warned['deliver'] = True
                _emit(progress, f"🚨 第{rnd}轮仍未写出 deck.json，系统强制催促\n")
                transcript += (
                    f"\n\n【系统强制提示 · 第 {rnd} 轮】\n"
                    "已消耗超过 12 轮但 $W 中仍无 deck.json/style.json。"
                    "立即执行：1) python -c '写入 deck.json 单行 JSON'  2) python $S/outline_check.py $W"
                )
                continue
            remaining = MAX_ROUNDS - rnd
            transcript += (
                f"\n\n【你的第 {rnd} 轮回复】\n{reply}\n\n【命令执行输出】\n"
                + '\n\n'.join(outputs)
                + f'\n\n请根据输出继续下一步（剩余约 {remaining} 轮，'
                  f'当前阶段={phase}{"（连续探索轮次="+str(explore_rounds)+"）" if explore_rounds >= 3 else ""}）；'
                  '全部完成且交付文件已生成时，回复不含代码块的总结。'
            )
    except Exception as e:
        return {'success': False, 'error': f'技能代理执行异常: {e}'}

    generated = _collect_artifacts(user_id, work_dir)
    _emit(progress, f"📦 已归档 {len(generated)} 个产物文件\n")
    result = (final_text or '').strip()
    if generated:
        lines = ['', '【生成的文件】（下载链接必须原样引用，不得改动文件名）']
        for f in generated:
            lines.append(f"- {f['original_name']}: {f['download_url']}")
        result = (result + '\n' + '\n'.join(lines)).strip()
    # 非自然完成的结局必须显式标注，防止上层二次生成时编造"后台处理/稍后提供"等不存在的机制
    if end_reason == 'rounds':
        result += f"\n\n(已达最大执行轮次 {MAX_ROUNDS} 轮，任务被迫中断，未走完全部流程)"
    elif end_reason == 'deadline':
        result += "\n\n(已达执行总时限，任务被迫中断)"
    if not _has_deliverable(work_dir):
        result += "\n\n(注意：本次执行未生成任何交付文件 .pptx/.docx/.xlsx/.pdf，任务未完成)"
    result += f"\n\n(技能代理执行 {rounds_used} 轮)"
    return {'success': True, 'result': result, 'generated_files': generated}
