import asyncio
import logging
from typing import Dict, Any
from .cron_manager import CronTaskManager

logger = logging.getLogger(__name__)


class TaskExecutor:
    def __init__(self, task_manager: CronTaskManager):
        self.task_manager = task_manager

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task.get('task_type', '')
        content = task.get('content', '')
        timeout = task.get('timeout', 300)

        try:
            if task_type == 'ai':
                result = await asyncio.wait_for(
                    self._execute_ai_task(task),
                    timeout=timeout
                )
            elif task_type == 'command':
                result = await asyncio.wait_for(
                    self._execute_command_task(task),
                    timeout=min(timeout, 300)
                )
            else:
                result = {'success': False, 'output': '', 'error': f"Unknown task type: {task_type}"}
            
            return result
        except asyncio.TimeoutError:
            return {'success': False, 'output': '', 'error': f"Task timed out after {timeout} seconds"}
        except Exception as e:
            return {'success': False, 'output': '', 'error': str(e)}

    async def _execute_ai_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from llm.adapter_base import get_default_llm_adapter
            
            adapter = get_default_llm_adapter()
            if not adapter:
                return {'success': False, 'output': '', 'error': "No LLM adapter configured"}

            system_prompt = "你是龙虾Claw，一个强大的AI智能体助手。请完成以下定时任务："
            messages = adapter.create_prompt(system_prompt, task['content'], [])
            
            response = await adapter.chat(messages)
            return {'success': True, 'output': response.content, 'error': ''}
        except Exception as e:
            logger.error(f"AI task execution failed: {e}")
            return {'success': False, 'output': '', 'error': str(e)}

    async def _execute_command_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from web.routes.lobster_claw import is_command_safe, execute_shell_command
            
            if not is_command_safe(task['content']):
                return {'success': False, 'output': '', 'error': "Command not in whitelist"}
            
            result = await execute_shell_command(task['content'])
            if result.get('success'):
                output = result.get('stdout', '')
                if result.get('stderr'):
                    output += '\n' + result.get('stderr', '')
                return {'success': True, 'output': output, 'error': ''}
            else:
                return {'success': False, 'output': '', 'error': result.get('error', 'Command failed')}
        except Exception as e:
            logger.error(f"Command task execution failed: {e}")
            return {'success': False, 'output': '', 'error': str(e)}
