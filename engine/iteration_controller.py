"""Iteration controller for managing agent execution loop"""
import time
import threading
import random
from typing import List, Callable, Optional, Dict, Any
from dataclasses import dataclass

from agents.agent_config import AgentConfig
from agents.agent_manager import AgentManager
from models.model_config import ModelConfig
from models.model_manager import ModelManager
from engine.agent_worker import AgentWorker, AgentResult, create_llm_adapter
from applogging.log_manager import LogManager


@dataclass
class IterationState:
    """Current state of iteration"""
    current_iteration: int = 0
    total_iterations: int = 10
    current_agent_index: int = 0
    current_agent_name: str = ""
    current_model_name: str = ""  # 当前使用的模型名称
    total_tokens: int = 0
    elapsed_time: float = 0.0
    is_running: bool = False
    is_paused: bool = False
    should_stop: bool = False
    current_document: str = ""
    search_count: int = 0
    search_logs: List[Dict[str, Any]] = None  # 搜索日志
    
    def __post_init__(self):
        if self.search_logs is None:
            self.search_logs = []


class IterationController:
    """Controller for managing iteration loop"""

    def __init__(
        self,
        agent_manager: AgentManager,
        model_manager: ModelManager,
        log_manager: LogManager = None,
        iterations: int = 10,
        search_manager: Any = None
    ):
        self.agent_manager = agent_manager
        self.model_manager = model_manager
        self.log_manager = log_manager
        self.total_iterations = iterations
        self.search_manager = search_manager

        self.state = IterationState(total_iterations=iterations)
        self.workers: Dict[str, AgentWorker] = {}
        self._thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None

        # Callbacks
        self.on_state_update: Optional[Callable[[IterationState], None]] = None
        self.on_agent_result: Optional[Callable[[AgentResult], None]] = None
        self.on_iteration_complete: Optional[Callable[[int, str], None]] = None
        self.on_all_complete: Optional[Callable[[str], None]] = None

    def run_iteration_sync(self, iteration: int, document: str) -> str:
        """Run a single iteration synchronously - used by web server"""
        return self._run_iteration(iteration, document)

    def run_iteration_stream(self, iteration: int, document: str, agent_ids: Optional[List[str]] = None):
        """Run a single iteration with streaming output - yields chunks from LLM"""
        if agent_ids:
            agents = [self.agent_manager.get(agent_id) for agent_id in agent_ids if self.agent_manager.get(agent_id)]
        else:
            agents = self.agent_manager.get_enabled()
        
        current_doc = document
        max_retries = 3

        search_context = self._perform_search(document, iteration)
        if search_context:
            current_doc = f"【搜索参考信息】\n{search_context}\n\n【原始文档】\n{document}"

        for idx, agent_config in enumerate(agents):
            if self.state.should_stop:
                yield {"type": "stop", "message": "用户停止"}
                return

            model_config = None
            adapter = None
            retry_count = 0
            tried_models = set()  # 记录已尝试的模型ID

            while retry_count < max_retries:
                # 重新随机选择模型（排除已尝试的）
                all_models = self.model_manager.get_all()
                available_models = [
                    m for m in all_models 
                    if m.api_key and m.model_type not in ("image", "video") and m.id not in tried_models
                ]
                
                # 如果所有模型都尝试过了，重新随机选择
                if not available_models:
                    available_models = [
                        m for m in all_models 
                        if m.api_key and m.model_type not in ("image", "video")
                    ]
                
                if not available_models:
                    retry_count += 1
                    continue
                
                model_config = random.choice(available_models)
                tried_models.add(model_config.id)

                adapter = create_llm_adapter(model_config)
                if not adapter:
                    retry_count += 1
                    continue

                worker = AgentWorker(
                    agent_config=agent_config,
                    model_config=model_config,
                    llm_adapter=adapter
                )

                yield {"type": "agent_start", "agent_name": agent_config.name, "model_name": model_config.name, "iteration": iteration}

                full_output = ""
                stats = None
                for chunk in worker.run_stream(current_doc):
                    if chunk["type"] == "error":
                        yield {"type": "error", "message": chunk["content"]}
                        retry_count += 1
                        break
                    
                    if chunk["type"] == "chunk":
                        full_output += chunk["content"]
                        yield {"type": "chunk", "content": chunk["content"]}
                    
                    if chunk["type"] == "complete":
                        current_doc = chunk["content"]
                        # 获取统计信息
                        if "stats" in chunk:
                            stats = chunk["stats"]
                        yield {"type": "agent_complete", "agent_name": agent_config.name, "content": current_doc, "stats": stats}
                        break

                if chunk.get("type") == "complete":
                    break

            if retry_count >= max_retries:
                yield {"type": "error", "message": f"Agent {agent_config.name} 所有模型调用均失败"}

        yield {"type": "iteration_complete", "content": current_doc}

    def _get_random_model(self) -> Optional[ModelConfig]:
        """随机选择一个已配置的文本模型（排除文生图和文生视频模型）"""
        all_models = self.model_manager.get_all()
        # 只选择有API密钥且是文本模型的
        configured_models = [m for m in all_models if m.api_key and m.model_type not in ("image", "video")]
        if not configured_models:
            return None
        return random.choice(configured_models)

    def _init_workers(self):
        """Initialize agent workers - 每次迭代重新随机分配模型"""
        self.workers = {}
        enabled_agents = self.agent_manager.get_enabled()

        for agent_config in enabled_agents:
            # 随机选择一个模型
            model_config = self._get_random_model()
            if model_config and model_config.api_key:
                adapter = create_llm_adapter(model_config)
                if adapter:
                    # 创建新的worker，使用随机选择的模型
                    self.workers[agent_config.id] = AgentWorker(
                        agent_config=agent_config,
                        model_config=model_config,
                        llm_adapter=adapter
                    )

    def _update_state(self, **kwargs):
        """Update state and notify callback"""
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)

        if self._start_time:
            self.state.elapsed_time = time.time() - self._start_time

        if self.on_state_update:
            self.on_state_update(self.state)

    def _perform_search(self, query: str, iteration: int) -> str:
        """在迭代时执行搜索，获取相关信息"""
        if not self.search_manager:
            return ""

        try:
            start_time = time.time()
            # 使用搜索管理器进行搜索
            results = self.search_manager.search_sync(query, num_results=3)
            elapsed_time = time.time() - start_time
            
            search_log_entry = {
                "iteration": iteration,
                "query": query[:100],
                "timestamp": time.strftime("%H:%M:%S"),
                "elapsed_time": round(elapsed_time, 2),
                "result_count": len(results) if results else 0,
                "results": []
            }
            
            if results and len(results) > 0:
                # 构建搜索上下文
                context_parts = []
                for i, result in enumerate(results, 1):
                    if result.title and (result.snippet or result.url):
                        context_parts.append(f"{i}. {result.title}")
                        if result.url:
                            context_parts.append(f"   来源: {result.url}")
                        if result.snippet:
                            context_parts.append(f"   摘要: {result.snippet[:200]}...")
                        context_parts.append("")
                    
                    search_log_entry["results"].append({
                        "title": result.title,
                        "url": result.url,
                        "snippet": result.snippet[:200] if result.snippet else ""
                    })
                
                search_context = "\n".join(context_parts)
                
                # 更新搜索计数
                self._update_state(search_count=self.state.search_count + 1)
                
                # 记录搜索日志
                self._update_state(search_logs=self.state.search_logs + [search_log_entry])
                
                # 记录日志
                self._add_log("INFO", f"第 {iteration} 次迭代完成搜索，获取到 {len(results)} 条结果")
                
                return search_context
            else:
                # 记录搜索日志（无结果）
                self._update_state(search_logs=self.state.search_logs + [search_log_entry])
                self._add_log("INFO", f"第 {iteration} 次迭代搜索未找到结果")
                return ""
        except Exception as e:
            search_log_entry = {
                "iteration": iteration,
                "query": query[:100],
                "timestamp": time.strftime("%H:%M:%S"),
                "elapsed_time": 0,
                "result_count": 0,
                "error": str(e),
                "results": []
            }
            self._update_state(search_logs=self.state.search_logs + [search_log_entry])
            self._add_log("WARNING", f"第 {iteration} 次迭代搜索失败: {str(e)}")
            return ""

    def _run_iteration(self, iteration: int, document: str) -> str:
        """Run one iteration with all enabled agents - 每个agent随机选择模型，失败时重试"""
        enabled_agents = self.agent_manager.get_enabled()
        current_doc = document
        max_retries = 3  # 最大重试次数

        # 在迭代开始时进行搜索，获取相关信息
        search_context = self._perform_search(document, iteration)
        if search_context:
            # 将搜索结果添加到文档前面作为上下文
            current_doc = f"【搜索参考信息】\n{search_context}\n\n【原始文档】\n{document}"

        for idx, agent_config in enumerate(enabled_agents):
            if self.state.should_stop:
                break

            # 每个agent随机选择一个模型，失败时重试并换其他模型
            model_config = None
            adapter = None
            retry_count = 0
            last_error = ""
            tried_models = set()  # 记录已尝试的模型ID

            while retry_count < max_retries:
                # 重新随机选择模型（排除已尝试的）
                all_models = self.model_manager.get_all()
                available_models = [
                    m for m in all_models 
                    if m.api_key and m.model_type not in ("image", "video") and m.id not in tried_models
                ]
                
                # 如果所有模型都尝试过了，重新随机选择
                if not available_models:
                    available_models = [
                        m for m in all_models 
                        if m.api_key and m.model_type not in ("image", "video")
                    ]
                
                if not available_models:
                    retry_count += 1
                    continue
                
                model_config = random.choice(available_models)
                tried_models.add(model_config.id)

                adapter = create_llm_adapter(model_config)
                if not adapter:
                    retry_count += 1
                    continue

                # Update state - agent starting
                self._update_state(
                    current_iteration=iteration,
                    current_agent_index=idx,
                    current_agent_name=agent_config.name,
                    current_model_name=model_config.name,
                    current_document=current_doc
                )

                # 创建新的worker，使用随机选择的模型，上下文只保持上一个agent的输出
                worker = AgentWorker(
                    agent_config=agent_config,
                    model_config=model_config,
                    llm_adapter=adapter
                )

                # Run agent - 只传入当前文档作为输入，不保留历史上下文
                result = worker.run(current_doc)

                # Log result
                self.log_manager.log_agent_result(result, iteration, idx + 1)

                # Notify callback
                if self.on_agent_result:
                    self.on_agent_result(result)

                if result.success:
                    # 成功，更新文档
                    current_doc = result.output
                    self._update_state(total_tokens=self.state.total_tokens + result.tokens_used)
                    break
                else:
                    # 失败，记录错误并重试
                    last_error = result.error_message
                    retry_count += 1
                    # 更新状态显示重试信息
                    self._update_state(
                        current_iteration=iteration,
                        current_agent_index=idx,
                        current_agent_name=agent_config.name,
                        current_model_name=f"{model_config.name} (重试{retry_count}/{max_retries})"
                    )

            if retry_count >= max_retries:
                # 所有模型都失败了
                self._add_log("ERROR", f"Agent {agent_config.name} 所有模型调用均失败: {last_error}")

        return current_doc

    def _add_log(self, level: str, message: str):
        """Add log entry"""
        from applogging.log_entry import LogEntry
        entry = LogEntry(
            agent_id="system",
            agent_name="System",
            iteration=self.state.current_iteration,
            step=self.state.current_agent_index + 1,
            output=f"[{level}] {message}",
            success=(level != "ERROR"),
            error_message=message if level == "ERROR" else ""
        )
        self.log_manager.log_agent_result(entry, self.state.current_iteration, self.state.current_agent_index + 1)

    def _analyze_instruction(self, instruction: str) -> str:
        """分析用户指令，判断是否需要联网搜索"""
        if not instruction.strip():
            return instruction
        
        self._add_log("INFO", "开始分析用户指令...")
        self._update_state(current_agent_name="指令分析器", current_model_name="分析模型")
        
        # 获取一个可用的模型进行分析
        model_config = self._get_random_model()
        if not model_config or not model_config.api_key:
            self._add_log("WARNING", "无可用模型进行指令分析，直接使用原始指令")
            return instruction
        
        try:
            adapter = create_llm_adapter(model_config)
            if not adapter:
                self._add_log("WARNING", "无法创建模型适配器，直接使用原始指令")
                return instruction
            
            # 第一步：判断是否需要联网搜索
            need_search = False
            search_context = ""
            
            if self.search_manager:
                self._add_log("INFO", "判断是否需要联网搜索...")
                
                # 使用模型判断是否需要搜索
                search_decision_prompt = f"""请分析以下用户指令，判断是否需要联网搜索来获取最新信息或补充知识。

用户指令：
{instruction}

请分析并回答：
1. 这个指令是否需要获取最新的信息、数据或新闻？（是/否）
2. 这个指令是否涉及需要补充专业知识或背景信息？（是/否）
3. 这个指令是否涉及需要引用参考资料或案例？（是/否）

如果以上任何一个问题的回答是"是"，请回答"是，需要搜索"，并简要说明需要搜索的关键词（用中文，3-5个关键词，用逗号分隔）。
如果全部回答"否"，请回答"否，无需搜索"。

请严格按照以下格式回答：
[判断]: 是/否
[关键词]: 关键词1, 关键词2, ...（如果判断为"否"，则写"无"）"""

                from engine.agent_worker import AgentWorker, AgentResult
                from agents.agent_config import AgentConfig
                
                temp_agent_config = AgentConfig(
                    id="search_decider",
                    name="搜索判断器",
                    role_description="判断是否需要联网搜索",
                    enabled=True
                )
                
                search_decider = AgentWorker(
                    agent_config=temp_agent_config,
                    model_config=model_config,
                    llm_adapter=adapter
                )
                
                decision_result = search_decider.run(search_decision_prompt)
                
                if decision_result.success:
                    decision_text = decision_result.output.strip().lower()
                    
                    # 解析判断结果
                    if "是" in decision_text and "判断" in decision_text:
                        need_search = True
                        self._add_log("INFO", "判断结果：需要联网搜索")
                        
                        # 提取搜索关键词
                        keywords = instruction  # 默认使用原始指令作为搜索词
                        if "关键词" in decision_text:
                            try:
                                kw_start = decision_text.find("关键词")
                                kw_line = decision_text[kw_start:].split("\n")[0]
                                extracted_kw = kw_line.split(":")[-1].strip()
                                if extracted_kw and extracted_kw != "无":
                                    keywords = extracted_kw
                            except:
                                pass
                        
                        self._add_log("INFO", f"提取搜索关键词: {keywords[:50]}...")
                        self._update_state(total_tokens=self.state.total_tokens + decision_result.tokens_used)
                    else:
                        self._add_log("INFO", "判断结果：无需联网搜索，直接使用原始指令")
                        self._update_state(total_tokens=self.state.total_tokens + decision_result.tokens_used)
                else:
                    self._add_log("WARNING", f"搜索判断失败: {decision_result.error_message}")
            
            # 第二步：如果需要搜索，执行搜索
            if need_search and self.search_manager:
                self._add_log("INFO", "开始联网搜索...")
                search_context = self._perform_search(instruction, 0)
                
                if search_context:
                    self._add_log("INFO", f"联网搜索完成，获取到 {len(search_context)} 字符的参考资料")
                else:
                    self._add_log("WARNING", "联网搜索未获取到有效结果")
            
            # 第三步：基于分析结果构建输出
            self._add_log("INFO", "生成方案框架...")
            
            # 构建分析提示
            if search_context:
                analysis_prompt = f"""请结合以下搜索参考资料，为用户指令生成一个详细的执行方案框架。

【用户指令】
{instruction}

【搜索参考资料】
{search_context}

请从以下方面进行分析：
1. 指令的核心目标和意图
2. 需要完成的主要任务模块
3. 每个模块的关键要点（结合参考资料）
4. 预期的输出格式和结构

请以结构化的方式输出分析结果，为后续的详细内容生成提供框架指导。"""
            else:
                analysis_prompt = f"""请分析以下用户指令，并生成一个详细的执行方案框架。

用户指令：
{instruction}

请从以下方面进行分析：
1. 指令的核心目标和意图
2. 需要完成的主要任务模块
3. 每个模块的关键要点
4. 预期的输出格式和结构

请以结构化的方式输出分析结果，为后续的详细内容生成提供框架指导。"""
            
            # 创建临时配置进行分析
            temp_agent_config = AgentConfig(
                id="analyzer",
                name="指令分析器",
                role_description="分析用户指令，生成执行方案框架",
                enabled=True
            )
            
            worker = AgentWorker(
                agent_config=temp_agent_config,
                model_config=model_config,
                llm_adapter=adapter
            )
            
            result = worker.run(analysis_prompt)
            
            if result.success:
                self._add_log("INFO", f"指令分析完成，生成了 {len(result.output)} 字符的方案框架")
                self._update_state(total_tokens=self.state.total_tokens + result.tokens_used)
                
                # 将分析结果与原始指令合并
                if search_context:
                    combined_output = f"""【用户原始指令】
{instruction}

【联网搜索资料】
{search_context}

【AI分析方案框架】
{result.output}

请基于以上分析框架和参考资料，详细展开每个模块的内容，生成完整、专业的输出文档。"""
                else:
                    combined_output = f"""【用户原始指令】
{instruction}

【AI分析方案框架】
{result.output}

请基于以上分析框架，详细展开每个模块的内容，生成完整、专业的输出文档。"""
                return combined_output
            else:
                self._add_log("WARNING", f"指令分析失败: {result.error_message}")
                return instruction
                
        except Exception as e:
            self._add_log("WARNING", f"指令分析过程出错: {str(e)}")
            return instruction

    def _run_loop(self, initial_document: str):
        """Main loop running in background thread"""
        self._start_time = time.time()
        self._update_state(is_running=True, should_stop=False)

        # 先分析用户指令
        analyzed_document = self._analyze_instruction(initial_document)
        current_doc = analyzed_document

        for i in range(1, self.total_iterations + 1):
            if self.state.should_stop:
                break

            # Run iteration
            current_doc = self._run_iteration(i, current_doc)

            # Notify iteration complete
            if self.on_iteration_complete:
                self.on_iteration_complete(i, current_doc)

        # Complete
        self._update_state(is_running=False, current_document=current_doc)

        if self.on_all_complete:
            self.on_all_complete(current_doc)

    def start(self, initial_document: str):
        """Start the iteration loop"""
        if self.state.is_running:
            return

        self._init_workers()
        self._update_state(current_iteration=0, current_agent_index=0, total_tokens=0)

        self._thread = threading.Thread(target=self._run_loop, args=(initial_document,))
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Stop the iteration loop"""
        self.state.should_stop = True
        self._update_state(is_running=False)

    def pause(self):
        """Pause the iteration"""
        self.state.is_paused = True
        self._update_state(is_paused=True)

    def resume(self):
        """Resume the iteration"""
        self.state.is_paused = False
        self._update_state(is_paused=False)

    def is_running(self) -> bool:
        """Check if running"""
        return self.state.is_running

    def get_state(self) -> IterationState:
        """Get current state"""
        return self.state

    def get_current_document(self) -> str:
        """Get current document content"""
        return self.state.current_document
