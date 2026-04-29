# -*- coding: utf-8 -*-
# cst/vba.py
import time
from src.utils.logger import logger

class CSTVBA:
    """
    CST VBA 脚本执行器
    """
    
    def __init__(self, project):
        """
        初始化 VBA 执行器。
        
        参数:
            project: CST 项目句柄 (cst.interface.Project)。
        """
        self.project = project

    def to_cst_history(self, vba_script: str, description: str) -> None:
        """
        将 VBA 代码注入到 CST 的历史记录中。
        
        参数:
            vba_script (str): VBA 代码字符串。
            description (str): 历史记录中的描述信息。
        """
        try:
            if self.project is None:
                logger.error("项目实例为空，无法执行 VBA。")
                return
            
            # CST API 调用，添加 VBA 代码到 History List
            # AddToHistory creates a new history block in the modeler 
            # with the given header-name and executes the vba_code
            self.project.model3d.add_to_history(description, vba_script)
            logger.debug(f"VBA 脚本已注入: {description}")
            
        except Exception as e:
            logger.error(f"VBA 执行失败: {description} | 错误: {e}")
            raise
    
    def execute(self, vba_code: str) -> None:
        """
        执行 VBA 宏代码。这是一个同步阻塞调用。

        当调用 vba.execute("...") 时，Python 会等待，
        直到 CST 内部的 VBA 引擎完全执行完毕（包括参数写入内存、依赖关系更新）才返回。
        
        该方法通过 CST Schematic 接口的 execute_vba_code 方法来运行 VBA 代码。
        适用于参数设置、求解器控制等通用操作。

        参数:
            vba_code (str): 要执行的 VBA 代码字符串。
        
        异常:
            Exception: 如果 VBA 执行失败或 schematic 接口不可用。
        """
        try:
            if self.project is None:
                logger.error("项目实例为空，无法执行 VBA。")
                raise RuntimeError("CST 项目实例为空")
            
            # ---------------------------------------------------------
            # 执行 VBA 宏代码
            # ---------------------------------------------------------
            # 1. 接口选择：使用 Schematic 接口作为通用 VBA 执行入口。
            #    CST 的 Python API 通过 project.schematic.execute_vba_code 
            #    来运行控制类宏（如 StoreParameter, Rebuild 等）。
            #
            # 2. 语法约束：CST 的 VBA 编译器要求传入的脚本必须包含一个名为 "Main" 
            #    的公共子程序作为入口点。
            #
            # 3. 代码构造：将用户传入的 vba_code 包裹在 Sub Main() ... End Sub 结构中。
            
            # 构造一个完整的 Sub Main 过程
            full_script = f"""
Sub Main()
    {vba_code}
End Sub
"""
            # Executes VBA Code Snippet
            # 当调用 schematic.execute_vba_code("...") 时，Python 会等待，
            # 直到 CST 内部的 VBA 引擎完全执行完毕（包括参数写入内存、依赖关系更新）才返回。
            self.project.schematic.execute_vba_code(full_script)
            # 提供时间用于执行,这是为了防止CST运行中卡死
            time.sleep(5)
            logger.debug(f"VBA 命令已执行: {vba_code[:50]}")
            
        except AttributeError:
            # 如果 schematic 为 None 导致 AttributeError，捕获并给出更清晰的错误
            logger.error("无法执行 VBA：project.schematic 接口不可用。请确认项目类型。")
            raise
        except Exception as e:
            logger.error(f"VBA 执行失败: {e}")
            raise

    def delete_all_results(self):
        """
        删除当前项目的所有结果。
        
        依据文档：
        Project Object -> DeleteResults: "Deletes all results of the actual project."
        """
        # 这里只需要写 Project 里的 方法即可，Sub Main() ... End Sub 默认执行当前 Project
        self.execute("DeleteResults")
        logger.debug(">>> DeleteResults 结果清除成功。")