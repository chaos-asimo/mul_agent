"""Skill执行器"""
import asyncio
import json
import re
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from .skill_config import SkillConfig, SkillType
from .skill_manager import SkillManager


@dataclass
class SkillResult:
    """Skill执行结果"""
    success: bool
    output: str = ""
    error: str = ""
    metadata: Dict[str, Any] = None
    execution_time: float = 0.0
    tokens_used: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata or {},
            "execution_time": self.execution_time,
            "tokens_used": self.tokens_used
        }


class SkillLogger:
    """Skill执行日志记录器"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, "skill_execution.log")
        os.makedirs(log_dir, exist_ok=True)
    
    def _write(self, level: str, skill_name: str, message: str, extra: dict = None):
        """写入日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "skill_name": skill_name,
            "message": message
        }
        if extra:
            log_entry["extra"] = extra
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[SkillLogger] Failed to write log: {e}", flush=True)
        
        # 同时打印到控制台
        try:
            print(f"[{timestamp}] [{level}] [{skill_name}] {message}", flush=True)
            if extra:
                print(f"    Extra: {json.dumps(extra, ensure_ascii=False, indent=2)}", flush=True)
        except Exception as e:
            print(f"[SkillLogger] Failed to print log: {e}", flush=True)
    
    def info(self, skill_name: str, message: str, extra: dict = None):
        self._write("INFO", skill_name, message, extra)
    
    def error(self, skill_name: str, message: str, extra: dict = None):
        self._write("ERROR", skill_name, message, extra)
    
    def debug(self, skill_name: str, message: str, extra: dict = None):
        self._write("DEBUG", skill_name, message, extra)
    
    def log_execution(self, skill_id: str, skill_name: str, skill_type: str, 
                     params: dict, context: dict, result: SkillResult):
        """记录完整的skill执行信息"""
        extra = {
            "skill_id": skill_id,
            "skill_name": skill_name,
            "skill_type": skill_type,
            "input": {
                "params": params,
                "context": context
            },
            "output": {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "metadata": result.metadata,
                "execution_time": result.execution_time,
                "tokens_used": result.tokens_used
            }
        }
        self._write("EXECUTION", f"{skill_name} ({skill_type})", "Skill执行完成", extra)


# 全局日志实例
skill_logger = SkillLogger()


class SkillExecutor:
    """Skill执行器，负责执行各种类型的Skill"""
    
    def __init__(self, skill_manager: SkillManager, model_manager=None, search_manager=None):
        self.skill_manager = skill_manager
        self.model_manager = model_manager
        self.search_manager = search_manager
        self.execution_history: List[Dict[str, Any]] = []
    
    async def execute(self, skill_id: str, params: Dict[str, Any], context: Dict[str, Any] = None) -> SkillResult:
        """
        执行Skill
        
        Args:
            skill_id: Skill ID
            params: 执行参数
            context: 上下文信息
        
        Returns:
            SkillResult: 执行结果
        """
        skill = self.skill_manager.get_by_id(skill_id)
        if not skill:
            error_result = SkillResult(success=False, error=f"Skill '{skill_id}' 不存在")
            skill_logger.error("Unknown", f"Skill不存在: {skill_id}", {"skill_id": skill_id})
            return error_result
        
        if not skill.enabled:
            error_result = SkillResult(success=False, error=f"Skill '{skill.name}' 已禁用")
            skill_logger.error(skill.name, f"Skill已禁用", {"skill_id": skill_id})
            return error_result
        
        # 记录开始执行
        skill_logger.info(skill.name, "=" * 50)
        skill_logger.info(skill.name, "开始执行Skill", {
            "skill_id": skill_id,
            "skill_name": skill.name,
            "skill_type": skill.executor,
            "params": params,
            "context": context or {}
        })
        
        # 验证参数
        validated_params = self._validate_params(skill, params)
        if validated_params.get("error"):
            skill_logger.error(skill.name, f"参数验证失败: {validated_params['error']}", {"params": params})
            return SkillResult(success=False, error=validated_params["error"])
        
        skill_logger.debug(skill.name, f"参数验证通过", {"validated_params": validated_params})
        
        # 合并上下文
        full_context = {**(context or {}), **validated_params}
        skill_logger.debug(skill.name, f"合并后的上下文", {"full_context": full_context})
        
        # 执行前置依赖
        for dep_id in skill.dependencies:
            skill_logger.info(skill.name, f"执行前置依赖: {dep_id}")
            dep_result = await self.execute(dep_id, params, context)
            if not dep_result.success:
                error_msg = f"依赖Skill执行失败: {dep_result.error}"
                skill_logger.error(skill.name, error_msg, {"dep_id": dep_id, "dep_error": dep_result.error})
                return SkillResult(success=False, error=error_msg)
            full_context[f"dep_{dep_id}"] = dep_result.output
            skill_logger.info(skill.name, f"依赖执行成功", {"dep_id": dep_id, "dep_output": dep_result.output[:200] if dep_result.output else ""})
        
        # 根据执行器类型执行
        start_time = datetime.now()
        skill_logger.info(skill.name, f"开始执行 ({skill.executor})", {"start_time": start_time.isoformat()})
        
        try:
            result = await self._execute_by_type(skill, full_context)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time
            
            # 记录执行历史
            self.execution_history.append({
                "skill_id": skill_id,
                "skill_name": skill.name,
                "params": params,
                "result": result.to_dict(),
                "timestamp": datetime.now().isoformat()
            })
            
            # 记录完整的执行信息到日志
            skill_logger.log_execution(skill_id, skill.name, skill.executor, params, context or {}, result)
            
            if result.success:
                skill_logger.info(skill.name, f"执行成功 (耗时: {execution_time:.3f}秒)", {
                    "execution_time": execution_time,
                    "output_length": len(result.output) if result.output else 0
                })
            else:
                skill_logger.error(skill.name, f"执行失败: {result.error}", {
                    "error": result.error,
                    "execution_time": execution_time
                })
            
            return result
            
        except asyncio.TimeoutError:
            error_result = SkillResult(success=False, error=f"Skill执行超时 ({skill.timeout}秒)")
            skill_logger.error(skill.name, f"执行超时", {"timeout": skill.timeout})
            return error_result
        except Exception as e:
            import traceback
            error_msg = f"Skill执行异常: {str(e)}"
            skill_logger.error(skill.name, error_msg, {"exception": str(e), "traceback": traceback.format_exc()})
            return SkillResult(success=False, error=error_msg)
    
    def _validate_params(self, skill: SkillConfig, params: Dict[str, Any]) -> Dict[str, Any]:
        """验证并处理参数"""
        result = {}
        
        for param_def in skill.parameters:
            param_name = param_def.name
            
            # 检查必需参数
            if param_def.required and param_name not in params:
                if param_def.default is None:
                    return {"error": f"缺少必需参数: {param_name}"}
                result[param_name] = param_def.default
            else:
                # 使用提供的值或默认值
                value = params.get(param_name, param_def.default)
                
                # 类型转换
                try:
                    if param_def.type == "number":
                        value = float(value) if value else 0
                    elif param_def.type == "boolean":
                        value = bool(value)
                    elif param_def.type == "list":
                        value = list(value) if value else []
                except:
                    pass
                
                # 验证可选值
                if param_def.options and value not in param_def.options:
                    # 使用第一个选项作为默认值
                    value = param_def.options[0]
                
                result[param_name] = value
        
        return result
    
    async def _execute_by_type(self, skill: SkillConfig, context: Dict[str, Any]) -> SkillResult:
        """根据执行器类型执行"""
        
        if skill.executor == "search":
            return await self._execute_search(skill, context)
        elif skill.executor == "llm":
            return await self._execute_llm(skill, context)
        elif skill.executor == "script":
            return await self._execute_script(skill, context)
        elif skill.executor == "api":
            return await self._execute_api(skill, context)
        else:
            return SkillResult(success=False, error=f"未知的执行器类型: {skill.executor}")
    
    async def _execute_search(self, skill: SkillConfig, context: Dict[str, Any]) -> SkillResult:
        """执行搜索类型Skill"""
        skill_logger.debug(skill.name, "开始执行搜索", {
            "search_manager": str(self.search_manager),
            "adapters": list(self.search_manager.adapters.keys()) if self.search_manager else None,
            "enabled": [s.id for s in self.search_manager.get_enabled()] if self.search_manager else []
        })
        
        if not self.search_manager:
            return SkillResult(success=False, error="搜索管理器未初始化")
        
        query = context.get("query", "")
        num_results = int(context.get("num_results", 5))
        
        skill_logger.info(skill.name, f"搜索参数", {"query": query, "num_results": num_results})
        
        if not query:
            return SkillResult(success=False, error="搜索关键词不能为空")
        
        try:
            skill_logger.debug(skill.name, f"调用search_manager.search", {"query": query, "num_results": num_results})
            results = await self.search_manager.search(query, None, num_results)
            skill_logger.debug(skill.name, f"搜索返回结果", {"results_count": len(results)})
            
            # 格式化搜索结果
            output_parts = []
            for i, result in enumerate(results, 1):
                title = result.title[:100] if result.title else ""
                snippet = result.snippet[:200] if result.snippet else ""
                output_parts.append(f"{i}. {title}")
                output_parts.append(f"   来源: {result.url}")
                output_parts.append(f"   摘要: {snippet}...")
                output_parts.append("")
            
            output = "\n".join(output_parts)
            
            skill_logger.info(skill.name, f"搜索结果格式化完成", {"output_length": len(output)})
            
            return SkillResult(
                success=True,
                output=output,
                metadata={"results_count": len(results), "query": query}
            )
        except Exception as e:
            import traceback
            skill_logger.error(skill.name, f"搜索执行异常", {"error": str(e), "traceback": traceback.format_exc()})
            return SkillResult(success=False, error=f"搜索执行失败: {str(e)}")
    
    async def _execute_llm(self, skill: SkillConfig, context: Dict[str, Any]) -> SkillResult:
        """执行LLM类型Skill"""
        if not self.model_manager:
            return SkillResult(success=False, error="模型管理器未初始化")
        
        # 获取可用模型
        models = self.model_manager.get_all()
        enabled_models = [m for m in models if m.enabled and m.api_key]
        
        if not enabled_models:
            return SkillResult(success=False, error="没有可用的模型")
        
        # 选择第一个可用模型
        model = enabled_models[0]
        
        # 构建提示
        prompt = skill.prompt_template
        
        # 替换模板变量
        for key, value in context.items():
            placeholder = "{" + key + "}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))
        
        # 检查是否还有未替换的变量
        remaining_vars = re.findall(r'\{(\w+)\}', prompt)
        if remaining_vars:
            # 尝试从context获取剩余变量
            for var in remaining_vars:
                if var in context:
                    prompt = prompt.replace(f"{{{var}}}", str(context[var]))
                else:
                    prompt = prompt.replace(f"{{{var}}}", "")
        
        try:
            # 创建模型适配器
            from engine.agent_worker import create_llm_adapter
            adapter = create_llm_adapter(model)
            
            if not adapter:
                return SkillResult(success=False, error="无法创建模型适配器")
            
            # 调用模型
            from agents.agent_config import AgentConfig
            from engine.agent_worker import AgentWorker
            
            temp_agent_config = AgentConfig(
                id=skill.id,
                name=skill.name,
                role_description=skill.description,
                enabled=True
            )
            
            worker = AgentWorker(
                agent_config=temp_agent_config,
                model_config=model,
                llm_adapter=adapter
            )
            
            result = worker.run(prompt)
            
            if result.success:
                return SkillResult(
                    success=True,
                    output=result.output,
                    tokens_used=result.tokens_used,
                    metadata={"model": model.name, "prompt_length": len(prompt)}
                )
            else:
                return SkillResult(success=False, error=result.error_message)
                
        except Exception as e:
            return SkillResult(success=False, error=f"LLM执行失败: {str(e)}")
    
    async def _execute_script(self, skill: SkillConfig, context: Dict[str, Any]) -> SkillResult:
        """执行脚本类型Skill"""
        if not skill.script:
            return SkillResult(success=False, error="脚本内容为空")
        
        try:
            # 创建执行环境
            exec_globals = {
                "context": context,
                "result": None,
                "asyncio": asyncio,
                "json": json
            }
            
            # 执行脚本
            exec(skill.script, exec_globals)
            
            output = exec_globals.get("result", "")
            
            return SkillResult(
                success=True,
                output=str(output),
                metadata={"script_length": len(skill.script)}
            )
        except Exception as e:
            return SkillResult(success=False, error=f"脚本执行失败: {str(e)}")
    
    async def _execute_api(self, skill: SkillConfig, context: Dict[str, Any]) -> SkillResult:
        """执行API类型Skill"""
        if not skill.api_endpoint:
            return SkillResult(success=False, error="API端点为空")
        
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                # 根据context构建请求
                method = context.get("method", "POST")
                headers = context.get("headers", {"Content-Type": "application/json"})
                
                async with session.request(
                    method,
                    skill.api_endpoint,
                    headers=headers,
                    json=context.get("body", context),
                    timeout=aiohttp.ClientTimeout(total=skill.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return SkillResult(
                            success=True,
                            output=json.dumps(data, ensure_ascii=False),
                            metadata={"status": response.status}
                        )
                    else:
                        error_text = await response.text()
                        return SkillResult(
                            success=False,
                            error=f"API返回错误: {response.status} - {error_text[:200]}"
                        )
        except asyncio.TimeoutError:
            return SkillResult(success=False, error="API请求超时")
        except Exception as e:
            return SkillResult(success=False, error=f"API调用失败: {str(e)}")
    
    async def execute_chain(self, skill_ids: List[str], initial_params: Dict[str, Any]) -> List[SkillResult]:
        """
        执行Skill链
        
        Args:
            skill_ids: Skill ID列表
            initial_params: 初始参数
        
        Returns:
            执行结果列表
        """
        results = []
        context = initial_params.copy()
        
        for skill_id in skill_ids:
            result = await self.execute(skill_id, {}, context)
            results.append(result)
            
            if result.success:
                # 将输出添加到上下文，供下一个Skill使用
                context[f"prev_output"] = result.output
                context[f"skill_{skill_id}"] = result.output
            else:
                # 执行失败，停止链
                break
        
        return results
    
    def get_execution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self.execution_history[-limit:]
    
    def clear_execution_history(self):
        """清空执行历史"""
        self.execution_history.clear()