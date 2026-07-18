import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Callable, Any
from .cron_manager import CronTaskManager

logger = logging.getLogger(__name__)


class CronParser:
    @staticmethod
    def parse(cron_expr: str) -> List[List[int]]:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError("Invalid cron expression. Expected 5 fields: minute hour day month weekday")

        return [
            CronParser._parse_field(parts[0], 0, 59),
            CronParser._parse_field(parts[1], 0, 23),
            CronParser._parse_field(parts[2], 1, 31),
            CronParser._parse_field(parts[3], 1, 12),
            CronParser._parse_field(parts[4], 0, 6),
        ]

    @staticmethod
    def _parse_field(field: str, min_val: int, max_val: int) -> List[int]:
        result = set()
        
        if field == '*':
            return list(range(min_val, max_val + 1))
        
        for part in field.split(','):
            part = part.strip()
            if part == '*':
                result.update(range(min_val, max_val + 1))
            elif '/' in part:
                base, step = part.split('/')
                if base == '*':
                    start = min_val
                else:
                    start = int(base)
                step = int(step)
                for val in range(start, max_val + 1, step):
                    if min_val <= val <= max_val:
                        result.add(val)
            elif '-' in part:
                start, end = part.split('-')
                start, end = int(start), int(end)
                for val in range(start, end + 1):
                    if min_val <= val <= max_val:
                        result.add(val)
            else:
                val = int(part)
                if min_val <= val <= max_val:
                    result.add(val)
        
        return sorted(list(result))

    @staticmethod
    def get_next_run(cron_expr: str, now: Optional[datetime] = None) -> datetime:
        if now is None:
            now = datetime.now()
        
        parsed = CronParser.parse(cron_expr)
        minutes, hours, days, months, weekdays = parsed
        
        next_time = now + timedelta(minutes=1)
        next_time = next_time.replace(second=0, microsecond=0)
        
        max_iterations = 10000
        for _ in range(max_iterations):
            if (next_time.month in months and
                next_time.day in days and
                next_time.hour in hours and
                next_time.minute in minutes and
                next_time.weekday() in weekdays):
                return next_time
            
            next_time += timedelta(minutes=1)
        
        raise ValueError("Could not find next run time within reasonable range")


class CronScheduler:
    def __init__(self, task_manager: CronTaskManager, task_executor: Callable):
        self.task_manager = task_manager
        self.task_executor = task_executor
        self.running = False
        self._task = None
        self._lock = asyncio.Lock()

    async def start(self):
        self.running = True
        await self._restore_tasks()
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Cron scheduler started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cron scheduler stopped")

    async def _restore_tasks(self):
        tasks = self.task_manager.list_tasks(enabled=True)
        for task in tasks:
            if task['schedule']:
                try:
                    next_run = CronParser.get_next_run(task['schedule'])
                    self.task_manager.update_task(task['id'], next_run_at=next_run.isoformat())
                except Exception as e:
                    logger.error(f"Failed to calculate next run for task {task['id']}: {e}")
            elif task['run_at']:
                if task['run_at'] <= datetime.now().isoformat():
                    asyncio.create_task(self._execute_task(task))

    async def _scheduler_loop(self):
        while self.running:
            try:
                await self._check_and_execute_tasks()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            
            now = datetime.now()
            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            sleep_seconds = (next_minute - now).total_seconds()
            await asyncio.sleep(max(0, sleep_seconds))

    async def _check_and_execute_tasks(self):
        async with self._lock:
            due_tasks = self.task_manager.get_due_tasks()
            for task in due_tasks:
                asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: dict):
        task_id = task['id']
        started_at = datetime.now().isoformat()
        run_id = None
        
        try:
            run_id = self.task_manager.add_run(
                task_id=task_id,
                status='running',
                started_at=started_at
            )
            
            result = await self.task_executor(task)
            
            finished_at = datetime.now().isoformat()
            duration = (datetime.fromisoformat(finished_at) - 
                        datetime.fromisoformat(started_at)).total_seconds()
            
            self.task_manager.update_run(
                run_id=run_id,
                status='completed',
                output=result.get('output', ''),
                finished_at=finished_at,
                duration=duration
            )
            
            if task['schedule']:
                next_run = CronParser.get_next_run(task['schedule'])
                self.task_manager.update_task(task_id, next_run_at=next_run.isoformat())
            elif task['run_at']:
                self.task_manager.update_task(task_id, enabled=False)
                
        except Exception as e:
            finished_at = datetime.now().isoformat()
            duration = (datetime.fromisoformat(finished_at) - 
                        datetime.fromisoformat(started_at)).total_seconds()
            
            if run_id:
                self.task_manager.update_run(
                    run_id=run_id,
                    status='failed',
                    error=str(e),
                    finished_at=finished_at,
                    duration=duration
                )
            
            if task['schedule']:
                try:
                    next_run = CronParser.get_next_run(task['schedule'])
                    self.task_manager.update_task(task_id, next_run_at=next_run.isoformat())
                except:
                    pass

    def run_now(self, task_id: int) -> bool:
        task = self.task_manager.get_task(task_id)
        if not task or not task['enabled']:
            return False
        asyncio.create_task(self._execute_task(task))
        return True
