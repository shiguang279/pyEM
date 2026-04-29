"""
materials.py
负责 CST 项目的材料定义与管理。

该模块采用数据驱动的方式，将材料参数与创建逻辑分离。
"""
from typing import Dict, Any, Set
from src.utils.logger import logger

# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTMaterials:
    """
    CST 材料定义管理器

    职责:
        1. 维护已定义材料的缓存，防止重复创建导致报错。
        2. 提供通用的介质材料创建方法。
        3. 提供特定的金属材料（如铜）创建方法。
        4. 批量加载项目所需的默认材料库。
    """

    # 材料参数数据库：将配置与逻辑分离
    # 键为材料名称，值为包含介电常数、损耗和类型的字典
    MATERIAL_DB: Dict[str, Dict[str, Any]] = {
        "FR-4 (lossy)": {"epsilon": 4.4, "tand": 0.02, "type": "Normal"},
        "F4B": {"epsilon": 2.2, "tand": 0.002, "type": "Normal"},
        "PTFE (lossy)": {"epsilon": 2.1, "tand": 0.0002, "type": "Normal"},
        "Rogers 4003C": {"epsilon": 3.55, "tand": 0.0027, "type": "Normal"},
        "my_dielectric": {"epsilon": 9.9, "tand": 0.001, "type": "Normal"},
    }

    def __init__(self, vba):
        """
        初始化材料管理器

        Args:
            vba: CSTVBA 实例，用于向 CST 发送指令 (依赖注入)
        """
        self.vba = vba
        # 使用集合记录已定义的材料名称，实现幂等性检查
        self._defined_materials: Set[str] = set()

        # 初始化时默认创建最常用的铜材料
        self.create_copper()

    def create_material(self, name: str, epsilon: float, tand: float, mat_type: str = "Normal") -> None:
        """
        通用方法：根据参数动态生成 VBA 并创建材料

        Args:
            name: 材料名称
            epsilon: 相对介电常数
            tand: 损耗角正切
            mat_type: 材料类型 (例如 "Normal", "Lossy metal", "PEC")
        """
        # 幂等性检查：如果材料已存在，直接跳过
        if name in self._defined_materials:
            logger.debug(f"Material '{name}' already exists, skipping.")
            return

        logger.info(f">>> Creating material: {name} | Type: {mat_type} | Epsilon: {epsilon} | TanD: {tand}")

        # 动态构建 VBA 代码字符串
        # 格式说明：
        # 1. 使用三引号 f-string：为了在 Python 代码中保持 VBA 的缩进结构，便于阅读和维护。
        # 2. 缩进对齐：Python 字符串内的缩进会被原样保留。CST VBA 解析器对缩进不敏感，
        #    但为了生成的宏代码整洁，我们通常保持 4 个空格或 1 个 Tab 的缩进。
        # 3. 换行符：每一行属性设置必须独占一行，不能合并。
        # 4. 点号 (.) 前缀：在 `With Material ... End With` 块内部，所有属性访问必须以 `.` 开头，
        #    这代表 `Material` 对象的成员。
        # 5. 字符串引号：VBA 中字符串参数必须用双引号 `""` 包裹。
        # 6. 最后的 .Create：这是最关键的一行。在 CST VBA 录制中，所有的属性设置只是配置，
        #    只有调用 `.Create` 方法才会真正将材料写入数据库。
        vba_code = f'''With Material
    .Reset
    .Name "{name}"
    .Folder ""
    .FrqType "all"
    .Type "{mat_type}"
    .SetMaterialUnit "GHz", "mm"
    .Epsilon "{epsilon}"
    .Mu "1.0"
    .Kappa "0.0"
    .TanD "{tand}"
    .TanDFreq "10.0"
    .TanDGiven "True"
    .TanDModel "ConstTanD"
    .KappaM "0.0"
    .TanDM "0.0"
    .TanDMFreq "0.0"
    .TanDMGiven "False"
    .TanDMModel "ConstKappa"
    .DispModelEps "None"
    .DispModelMu "None"
    .DispersiveFittingSchemeEps "General 1st"
    .DispersiveFittingSchemeMu "General 1st"
    .UseGeneralDispersionEps "False"
    .UseGeneralDispersionMu "False"
    .Rho "0.0"
    .ThermalType "Normal"
    .ThermalConductivity "0.24"
    .SetActiveMaterial "all"
    .Colour "0.94", "0.82", "0.76"
    .Wireframe "False"
    .Transparency "0"
    .Create
End With'''

        self.vba.to_cst_history(vba_code, f"Define Material: {name}")
        self._defined_materials.add(name)

    def create_copper(self) -> None:
        """
        创建标准退火铜材料 (Copper annealed)

        类型: Lossy metal (损耗金属)
        参数: 包含电导率、密度、热导率等详细物理属性
        """
        name = "Copper (annealed)"
        
        # 幂等性检查
        if name in self._defined_materials:
            return

        logger.info(f">>> Creating material: {name}")

        # 铜材料的 VBA 模板
        # 格式特殊性说明：
        # 1. 硬编码字符串：由于铜的参数（如电导率 Kappa、热属性）是固定的，
        #    且比介质材料复杂得多，因此不使用 f-string 动态生成，而是直接硬编码。
        # 2. 数值格式：CST VBA 对科学计数法的格式有要求，如 "5.8e+007"。
        #    注意不要写成 Python 的 5.8e7，虽然 CST 可能兼容，但标准录制格式通常带符号位。
        # 3. 单位定义：.SpecificHeat 等参数后面紧跟单位字符串 "J/K/kg"，这是 CST VBA 的特殊语法。
        vba_code = '''With Material
    .Reset
    .Name "Copper (annealed)"
    .Folder ""
    .FrqType "all"
    .Type "Lossy metal"
    .SetMaterialUnit "GHz", "mm"
    .Epsilon "1"
    .Mu "1.0"
    .Kappa "5.8e+007"
    .TanD "0.0"
    .TanDFreq "0.0"
    .TanDGiven "False"
    .TanDModel "ConstTanD"
    .KappaM "0"
    .TanDM "0.0"
    .TanDMFreq "0.0"
    .TanDMGiven "False"
    .TanDMModel "ConstTanD"
    .DispModelEps "None"
    .DispModelMu "None"
    .DispersiveFittingSchemeEps "Nth Order"
    .DispersiveFittingSchemeMu "Nth Order"
    .UseGeneralDispersionEps "False"
    .UseGeneralDispersionMu "False"
    .Rho "8930.0"
    .ThermalType "Normal"
    .ThermalConductivity "401.0"
    .SpecificHeat "390", "J/K/kg"
    .MetabolicRate "0"
    .BloodFlow "0"
    .VoxelConvection "0"
    .MechanicsType "Isotropic"
    .YoungsModulus "120"
    .PoissonsRatio "0.33"
    .ThermalExpansionRate "17"
    .Colour "1", "1", "0"
    .Wireframe "False"
    .Reflection "False"
    .Allowoutline "True"
    .Transparentoutline "False"
    .Transparency "0"
    .Create
End With'''

        self.vba.to_cst_history(vba_code, "Define Material: Copper")
        self._defined_materials.add(name)

    def create_default_materials(self) -> None:
        """
        批量创建项目所需的默认材料

        遍历 MATERIAL_DB 字典，自动创建所有预定义的介质材料，
        并确保铜材料已存在。
        """
        logger.info("Loading default material library...")
        
        # 1. 从字典加载所有介质材料
        for name, props in self.MATERIAL_DB.items():
            self.create_material(name, props["epsilon"], props["tand"], props["type"])
        
        # 2. 确保铜材料也被创建
        self.create_copper()