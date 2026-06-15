"""Skill管理器"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from .skill_config import SkillConfig, DEFAULT_SKILLS


class SkillManager:
    """Skill管理器，负责Skill的加载、保存和管理"""
    
    def __init__(self, config_path: str = "skills.json"):
        self.config_path = config_path
        self.skills: Dict[str, SkillConfig] = {}
        self._load_skills()
    
    def _load_skills(self):
        """加载Skills配置"""
        # 尝试从配置文件加载
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for skill_data in data.get("skills", []):
                        skill = SkillConfig.from_dict(skill_data)
                        self.skills[skill.id] = skill
            except Exception as e:
                print(f"加载Skills配置失败: {e}")
        
        # 如果没有配置，使用默认Skills
        if not self.skills:
            for skill in DEFAULT_SKILLS:
                self.skills[skill.id] = skill
            self._save_skills()
    
    def _save_skills(self):
        """保存Skills配置"""
        try:
            data = {
                "skills": [skill.to_dict() for skill in self.skills.values()]
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存Skills配置失败: {e}")
    
    def get_all(self) -> List[SkillConfig]:
        """获取所有Skills"""
        return list(self.skills.values())
    
    def get_enabled(self) -> List[SkillConfig]:
        """获取所有启用的Skills"""
        return [s for s in self.skills.values() if s.enabled]
    
    def get_by_id(self, skill_id: str) -> Optional[SkillConfig]:
        """根据ID获取Skill"""
        return self.skills.get(skill_id)
    
    def get_by_name(self, name: str) -> Optional[SkillConfig]:
        """根据名称获取Skill"""
        for skill in self.skills.values():
            if skill.name == name:
                return skill
        return None
    
    def get_by_type(self, skill_type: str) -> List[SkillConfig]:
        """根据类型获取Skills"""
        from .skill_config import SkillType
        try:
            type_enum = SkillType(skill_type)
            return [s for s in self.skills.values() if s.skill_type == type_enum]
        except:
            return []
    
    def add(self, skill: SkillConfig) -> bool:
        """添加新Skill"""
        if skill.id in self.skills:
            return False
        self.skills[skill.id] = skill
        self._save_skills()
        return True
    
    def update(self, skill: SkillConfig) -> bool:
        """更新Skill"""
        if skill.id not in self.skills:
            return False
        self.skills[skill.id] = skill
        self._save_skills()
        return True
    
    def delete(self, skill_id: str) -> bool:
        """删除Skill"""
        if skill_id not in self.skills:
            return False
        del self.skills[skill_id]
        self._save_skills()
        return True
    
    def enable(self, skill_id: str) -> bool:
        """启用Skill"""
        skill = self.get_by_id(skill_id)
        if skill:
            skill.enabled = True
            self._save_skills()
            return True
        return False
    
    def disable(self, skill_id: str) -> bool:
        """禁用Skill"""
        skill = self.get_by_id(skill_id)
        if skill:
            skill.enabled = False
            self._save_skills()
            return True
        return False
    
    def search(self, query: str) -> List[SkillConfig]:
        """搜索Skills"""
        results = []
        query_lower = query.lower()
        for skill in self.skills.values():
            if query_lower in skill.name.lower() or \
               query_lower in skill.description.lower() or \
               any(query_lower in tag.lower() for tag in skill.tags):
                results.append(skill)
        return results
    
    def validate_skill(self, skill: SkillConfig) -> List[str]:
        """验证Skill配置"""
        errors = []
        
        if not skill.name:
            errors.append("Skill名称不能为空")
        
        if not skill.executor:
            errors.append("必须指定执行器类型")
        
        if skill.executor == "llm" and not skill.prompt_template:
            errors.append("LLM执行器必须提供提示模板")
        
        if skill.executor == "script" and not skill.script:
            errors.append("脚本执行器必须提供脚本内容")
        
        # 检查依赖
        for dep_id in skill.dependencies:
            if dep_id not in self.skills:
                errors.append(f"依赖的Skill '{dep_id}' 不存在")
        
        return errors
    
    def get_skill_dependencies(self, skill_id: str) -> List[SkillConfig]:
        """获取Skill的所有依赖"""
        skill = self.get_by_id(skill_id)
        if not skill:
            return []
        
        dependencies = []
        for dep_id in skill.dependencies:
            dep_skill = self.get_by_id(dep_id)
            if dep_skill:
                dependencies.append(dep_skill)
        return dependencies
    
    def get_skill_tree(self, skill_id: str) -> Dict[str, Any]:
        """获取Skill的依赖树"""
        skill = self.get_by_id(skill_id)
        if not skill:
            return {}
        
        tree = {
            "skill": skill.to_dict(),
            "dependencies": []
        }
        
        for dep_id in skill.dependencies:
            dep_tree = self.get_skill_tree(dep_id)
            if dep_tree:
                tree["dependencies"].append(dep_tree)
        
        return tree
    
    def import_skills(self, file_path: str) -> int:
        """从文件导入Skills"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                count = 0
                for skill_data in data.get("skills", []):
                    skill = SkillConfig.from_dict(skill_data)
                    # 生成新ID避免冲突
                    from uuid import uuid4
                    skill.id = str(uuid4())
                    if self.add(skill):
                        count += 1
                return count
        except Exception as e:
            print(f"导入Skills失败: {e}")
            return 0
    
    def export_skills(self, file_path: str, skill_ids: List[str] = None) -> bool:
        """导出Skills到文件"""
        try:
            if skill_ids:
                skills_to_export = [self.skills[id].to_dict() for id in skill_ids if id in self.skills]
            else:
                skills_to_export = [skill.to_dict() for skill in self.skills.values()]
            
            data = {"skills": skills_to_export}
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出Skills失败: {e}")
            return False
    
    def reset_to_default(self):
        """重置为默认Skills"""
        self.skills.clear()
        for skill in DEFAULT_SKILLS:
            self.skills[skill.id] = skill
        self._save_skills()