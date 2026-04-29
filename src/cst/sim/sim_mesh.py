"""
mesh.py 负责 CST 项目的网格划分配置。
"""

# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTMesh:
    """
    职责：处理六面体网格、PBA 技术及网格细化策略。
    """
    
    def __init__(self, vba):
        self.vba = vba

    def set_mesh(self) -> None:
        """配置六面体网格 (Hexahedral Mesh) 及 PBA (理想边界近似) 技术

        设置网格
        - 四面体网格在处理复杂形状时更为灵活，但计算精度可能略低于六面体网格。
        - 三角面元网格：适用于矩量法的 Surface 求解。
        - CST 的时域求解器主要使用六面体网格（Hexahedral Mesh），也就是由很多小立方体组成的网格。

        .MeshType "PBA" 是一个非常关键的设置，它代表了 PBA (Perfect Boundary Approximation，理想边界近似) 技术。
        这是 CST 时域求解器（FIT 求解器）的核心技术之一，用于解决“直角网格”无法精确拟合“曲面或斜面”的问题。
        PBA 是一种共形网格技术。它允许网格线与几何边界不完全重合。
        - 传统方法 (Staircase Mesh)： 当网格遇到一个圆柱体或斜面时，网格只能像“楼梯”一样一级一级地去逼近它。
          这会导致几何模型边缘出现锯齿（阶梯效应），严重影响计算精度，尤其是对于曲面结构（如天线、圆柱腔体）。
        - PBA 技术： 网格本身仍然是直角六面体，但在计算材料属性时，算法会精确计算网格单元被几何边界切割的比例。
          它不再是简单的“非此即彼”，而是根据边界在网格内的实际位置来分配材料属性。它通过一种特殊的加权算法，
          在跨越边界的网格单元中，精确地描述两种不同材料（例如金属和空气）的分布。
          在 VBA 代码中设置 .MeshType "PBA"，主要有以下好处：更高的精度，能够精确捕捉几何细节，
          消除了阶梯近似带来的误差。对于高频、谐振结构（如滤波器、微带天线）尤为重要。

        CST 的网格生成器非常复杂，包含数十个参数（如每波长网格数、最小步长、曲率采样等）。
        当设置 .SetCreator "High Frequency" 时，实际上是调用了 CST 内置的一套针对高频电磁场问题的优化参数集。    
        当选择 "High Frequency" 模式时，CST 会自动调整以下逻辑（通常不需要手动干预）：
        - 波长采样： 根据设置的频率，自动计算波长，并确保每个波长内有足够的网格线。
        - 几何适应： 尝试识别几何模型中的关键特征（如边缘、曲面），并在这些地方适当加密网格，但不会像机械仿真那样过度细分。
        - 材料处理： 配合 .MeshType "PBA"（理想边界近似），确保介质和金属的边界被精确处理。
        """
        
        # --- 核心网格类型设置 ---
        # .MeshType "PBA": 启用理想边界近似，解决直角网格拟合曲面的阶梯效应
        # .SetCreator "High Frequency": 调用高频优化参数集
        vba_mesh = '''
With Mesh
    .MeshType "PBA"
    .SetCreator "High Frequency"
End With

With MeshSettings
    .SetMeshType "Hex"
    .Set "Version", 1% 
    .Set "StepsPerWaveNear", "15"
    .Set "StepsPerWaveFar", "15"
    .Set "WavelengthRefinementSameAsNear", "1"
    .Set "StepsPerBoxNear", "20"
    .Set "StepsPerBoxFar", "1"
    .Set "MaxStepNear", "0"
    .Set "MaxStepFar", "0"
    .Set "ModelBoxDescrNear", "maxedge"
    .Set "ModelBoxDescrFar", "maxedge"
    .Set "UseMaxStepAbsolute", "0"
    .Set "GeometryRefinementSameAsNear", "0"
    .Set "UseRatioLimitGeometry", "1"
    .Set "RatioLimitGeometry", "20"
    .Set "MinStepGeometryX", "0"
    .Set "MinStepGeometryY", "0"
    .Set "MinStepGeometryZ", "0"
    .Set "UseSameMinStepGeometryXYZ", "1"
End With

With MeshSettings
    .SetMeshType "Hex"
    .Set "PlaneMergeVersion", "2"
End With

With MeshSettings
    .SetMeshType "Hex"
    .Set "FaceRefinementType", "NONE"
    .Set "FaceRefinementRatio", "2"
    .Set "FaceRefinementStep", "0"
    .Set "FaceRefinementNSteps", "2"
    .Set "FaceRefinementBufferLines", "3"
    .Set "EllipseRefinementType", "NONE"
    .Set "EllipseRefinementRatio", "2"
    .Set "EllipseRefinementStep", "0"
    .Set "EllipseRefinementNSteps", "2"
    .Set "EdgeRefinementType", "RATIO"
    .Set "EdgeRefinementRatio", "6"
    .Set "EdgeRefinementStep", "0"
    .Set "EdgeRefinementBufferLines", "3"
    .Set "BufferLinesNear", "3"
    .Set "UseDielectrics", "1"
    .Set "EquilibrateOn", "1"
    .Set "Equilibrate", "1.5"
    .Set "IgnoreThinPanelMaterial", "0"
End With

With MeshSettings
    .SetMeshType "Hex"
    .Set "SnapToAxialEdges", "0"
    .Set "SnapToPlanes", "1"
    .Set "SnapToSpheres", "1"
    .Set "SnapToEllipses", "0"
    .Set "SnapToCylinders", "1"
    .Set "SnapToCylinderCenters", "1"
    .Set "SnapToEllipseCenters", "1"
    .Set "SnapToTori", "1"
    .Set "SnapXYZ" , "1", "1", "1"
End With

With Mesh
    .ConnectivityCheck "True"
    .UsePecEdgeModel "True"
    .PointAccEnhancement "0"
    .TSTVersion "0"
    .PBAVersion "2024121625"
    .SetCADProcessingMethod "MultiThread22", "-1"
    .SetGPUForMatrixCalculationDisabled "False"
End With
'''
        self.vba.to_cst_history(vba_mesh, "Mesh Settings")