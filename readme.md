
# pyEM  (Python for Electromagnetics)

**pyEM (Python for Electromagnetics)** 是一个电磁仿真 Python API。

**pyEM** 未来允许你可以使用 **Python** 在 **CST** (CST Studio Suite)、**Ansys HFSS / AEDT** (High Frequency Structure Simulator of ANSYS Electronic Desktop (AEDT)) 或 **COMSOL** (COMSOL Multiphysics) 软件上运行自动化的仿真流程。

## v0.01 仅支持 CST

- Windows
- CST 版本 2025，推荐最新版本
- **代码未经严格验证**，存在未知问题。
- HFSS 和 COMSOL **不支持**。
- Python 3.10+, NumPy, Matplotlib
- HDF5 数据格式
- multiprocessing 并行

## 欢迎来到 Python for Electromagnetics

简洁的 **pyEM**，未来适用于 CST、HFSS/AEDT 或 COMSOL。它赋予了研究人员定义 **物理设置器(Setup)** 与 **几何设计器(Designer)** 的能力，使其在支持的仿真软件上都能以一致的方式运行。

在 **pyEM** 的研究与开发中，核心范式在于构建高度抽象且物理感知的智能组件。**pyEM** 未来旨在建立一种跨越不同电磁仿真软件（如 CST、HFSS、COMSOL）的统一抽象层。这种架构允许你将复杂的物理场景封装为可复用的对象，确保算法逻辑与底层仿真引擎解耦。

### 参数化扫描建模

此模式适用于设计空间明确、需进行精细化优化的场景。pyEM 允许用户先在仿真软件中构建高精度的模型，定义关键几何尺寸、材料属性或边界条件为变量。随后，系统自动执行参数化扫描，遍历预设的变量组合，生成大量仿真数据。

### ️自动化拓扑建模

此模式适用于概念设计阶段或需突破传统构型限制的场景。pyEM 允许用户集成先进的拓扑优化算法，能够根据用户设定的设计目标及制造约束，自动计算并生成最优的结构分布。

### 主要特点

以微带贴片天线的设计为例，在 pyEM 架构下，你可以通过 Setup 类将频率、基板参数及几何尺寸等关键变量注入到统一的仿真流中。

## 运行示例程序

```shell
python -m examples.metasurface.main
```

## 未来

无具体计划
