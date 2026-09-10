# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 定时任务调度器（仿写 cron/cron_scheduler.py + task_executor.py）

与旧调度器（web/routes/lobster_claw.py 的 cron_scheduler，cron.db）完全并行、互不干扰：
- 独立模块级单例 mu_scheduler，由 web_server startup/shutdown 挂载
- 任务数据存 lobster_mu.db 的 mu_cron_tasks/mu_cron_runs（带 user_id）
- ai 任务以该用户身份通过 lobster_mu.chat_service.get_default_llm_adapter 调 LLM
"""
import asyncio
import functools
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from cron.cron_scheduler import CronParser
from lobster_mu import cron_store, tools

logger = logging.getLogger(__name__)


class MuCronScheduler:
    """多用户定时任务调度器（单实例服务所有用户，运行记录按 user_id 写入）"""

    def __init__(self, store=None):
        self.store = store or cron_store
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        # 确保表已建（startup 可早于首次登录）
        from lobster_mu import db
        db.init_db()
        self.running = True
        await self._restore_tasks()
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("MuCron scheduler started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MuCron scheduler stopped")

    async def _restore_tasks(self):
        """启动时恢复：周期任务重算 next_run_at；过期的一次性任务立即补执行"""
        for task in self.store.list_enabled_tasks():
            if task.get("schedule"):
                try:
                    next_run = CronParser.get_next_run(task["schedule"])
                    self.store.set_next_run(task["user_id"], task["id"], next_run.isoformat())
                except Exception as e:
                    logger.error(f"Failed to calculate next run for mu task {task['id']}: {e}")
            elif task.get("run_at"):
                if task["run_at"] <= datetime.now().isoformat():
                    asyncio.create_task(self._execute_task(task))

    async def _scheduler_loop(self):
        while self.running:
            try:
                await self._check_and_execute_tasks()
            except Exception as e:
                logger.error(f"Mu scheduler loop error: {e}")

            now = datetime.now()
            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            sleep_seconds = (next_minute - now).total_seconds()
            await asyncio.sleep(max(0, sleep_seconds))

    async def _check_and_execute_tasks(self):
        async with self._lock:
            due_tasks = self.store.get_due_tasks()
            for task in due_tasks:
                asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: Dict[str, Any]):
        task_id = task["id"]
        user_id = task["user_id"]
        started_at = datetime.now().isoformat()
        run_id = None

        try:
            run_id = self.store.add_run(
                user_id=user_id, task_id=task_id, status="running", started_at=started_at
            )

            result = await self._run_by_type(task)

            finished_at = datetime.now().isoformat()
            duration = (datetime.fromisoformat(finished_at)
                        - datetime.fromisoformat(started_at)).total_seconds()

            success = bool(result.get("success", False))
            self.store.update_run(
                user_id=user_id,
                run_id=run_id,
                status="success" if success else "failed",
                output=result.get("output", ""),
                error=result.get("error", "") if not success else "",
                finished_at=finished_at,
                duration=duration,
            )

            if task.get("schedule"):
                try:
                    next_run = CronParser.get_next_run(task["schedule"])
                    self.store.set_next_run(user_id, task_id, next_run.isoformat())
                except Exception:
                    pass
            elif task.get("run_at"):
                # 一次性任务执行后禁用
                self.store.update_task(user_id, task_id, enabled=0)

        except Exception as e:
            logger.exception(f"Mu task {task_id} execution crashed")
            finished_at = datetime.now().isoformat()
            duration = (datetime.fromisoformat(finished_at)
                        - datetime.fromisoformat(started_at)).total_seconds()
            if run_id:
                self.store.update_run(
                    user_id=user_id, run_id=run_id, status="failed", error=str(e),
                    finished_at=finished_at, duration=duration,
                )
            if task.get("schedule"):
                try:
                    next_run = CronParser.get_next_run(task["schedule"])
                    self.store.set_next_run(user_id, task_id, next_run.isoformat())
                except Exception:
                    pass

    def run_now(self, user_id: int, task: Dict[str, Any]) -> bool:
        """立即触发一次（run-now 端点用）"""
        if not task or not task.get("enabled"):
            return False
        asyncio.create_task(self._execute_task(task))
        return True

    # ============ 任务执行（对应 TaskExecutor._execute_ai_task/_execute_command_task） ============

    async def _run_by_type(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task.get("task_type", "")
        timeout = task.get("timeout", 300)
        try:
            if task_type == "ai":
                result = await asyncio.wait_for(self._execute_ai_task(task), timeout=timeout)
            elif task_type == "command":
                result = await asyncio.wait_for(
                    self._execute_command_task(task), timeout=min(timeout, 300)
                )
            else:
                result = {"success": False, "output": "",
                          "error": f"Unknown task type: {task_type}"}
            return result
        except asyncio.TimeoutError:
            return {"success": False, "output": "",
                    "error": f"Task timed out after {timeout} seconds"}
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}

    async def _execute_ai_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 以任务归属用户的身份获取 LLM 适配器
            from lobster_mu.chat_service import get_default_llm_adapter

            adapter = get_default_llm_adapter()
            if not adapter:
                return {"success": False, "output": "", "error": "No LLM adapter configured"}

            system_prompt = "你是龙虾Claw，一个强大的AI智能体助手。请完成以下定时任务："
            messages = adapter.create_prompt(system_prompt, task["content"], [])

            # adapter.chat 是同步调用，在后台线程中执行避免阻塞事件循环
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, functools.partial(adapter.chat, messages)
            )
            output = response.content if hasattr(response, "content") else str(response)
            return {"success": True, "output": output, "error": ""}
        except Exception as e:
            logger.exception("Mu AI task execution failed")
            return {"success": False, "output": "", "error": str(e)}

    async def _execute_command_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            content = task["content"]
            if not tools.is_command_safe(content):
                return {"success": False, "output": "", "error": "Command not in whitelist"}

            timeout = min(task.get("timeout", 300), 300)
            # tools.execute_shell_command 是同步实现，放线程池执行避免阻塞事件循环
            result = await asyncio.get_event_loop().run_in_executor(
                None, functools.partial(tools.execute_shell_command, content, timeout)
            )
            if result.get("success"):
                output = result.get("stdout", "")
                if result.get("stderr"):
                    output += "\n" + result.get("stderr", "")
                return {"success": True, "output": output, "error": ""}
            return {"success": False, "output": "",
                    "error": result.get("error", "Command failed")}
        except Exception as e:
            logger.error(f"Mu command task execution failed: {e}")
            return {"success": False, "output": "", "error": str(e)}


# 模块级单例：web/routes/lobster_mu.py import 后由 web_server.py startup/shutdown 挂载
mu_scheduler = MuCronScheduler()
