# -*- coding: utf-8 -*-
"""
模块：cst/flow.py
描述：CST 仿真工作流控制器，负责统筹材料、结构、仿真设置与保存。
现在明确使用 CST Project 对象。
"""

import os
from typing import Dict, Any
from src.core.flow import SimFlow 
from src.utils.logger import logger
from .structure import CSTStructureBuilder

class CSTFlow(SimFlow):
    """CST 仿真工作流实现"""

    def __init__(self, builder: CSTStructureBuilder, design_name: str, output_dir: str = "output"):
        """
        初始化 CST 仿真工作流。
        
        Args:
            builder (CSTStructureBuilder): 由 Runner 创建好的 Builder 实例。
            design_name (str): 设计名称。
            output_dir (str): 输出目录。
        """
        super().__init__(builder=builder, design_name=design_name, output_dir=output_dir)
        logger.debug("CSTFlow initialized with provided Builder.")

    def _apply_parameters_to_software(self, params_data: Dict[str, Any], cst_project_obj: Any) -> bool:
        """
        [CST 特有] 将内存中的参数写入 CST 软件。
        Args:
            params_data: 参数字典。
            cst_project_obj: CST 项目对象 (例如 project_ctx.project)。
        """
        if not params_data:
            return True
            
        logger.info(f">>> 正在将 {len(params_data)} 个参数设置到 CST...")
        
        try:
            for name, value in params_data.items():
                value_str = str(value)
                description = f"Parameter {name}"
                
                try:
                    # 调用 CST API 存储参数
                    cst_project_obj.model3d.StoreParameterWithDescription(name, value_str, description)
                    logger.info(f"  - 设置参数: {name} = {value_str}")
                except Exception as e:
                    logger.error(f"写入 CST 参数失败 '{name}': {e}")
                    return False
            
            logger.info(">>> CST 参数设置完成。")
            return True
            
        except Exception as e:
            logger.error(f"同步参数到 CST 时发生致命错误: {e}")
            return False

    def execute_automated_modeling(self) -> None:
        """
        执行自动化几何建模流程。
        """
        if self._designer and self.structure:
            logger.info("[CSTFlow] 开始执行自动化建模...")
            self._designer.execute_design()
            logger.info("[CSTFlow] 建模完成。")
        else:
            logger.error("[CSTFlow] 错误：Designer 未初始化！")
            raise RuntimeError("建模环境未就绪，请先调用 inject_designer。")

    def prepare_save_path(self, project_name: str) -> str:
        """准备并返回项目保存路径"""
        abs_output_dir = os.path.abspath(self.output_dir)
        if not os.path.exists(abs_output_dir):
            os.makedirs(abs_output_dir)
            
        self.save_path = os.path.join(abs_output_dir, f"{project_name}.cst")
        return self.save_path