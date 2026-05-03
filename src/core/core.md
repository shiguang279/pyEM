# 自动化仿真框架核心技术架构文档

## 1. 概述 (Overview)

本框架采用**分层架构设计 (Layered Architecture)** 与**依赖倒置原则 (DIP)**，将仿真任务拆解为**控制逻辑**、**设计参数**与**底层实现**三个正交的维度。

这种设计的核心目标是实现**一套业务逻辑，多平台运行**（如 CST 与 HFSS），并支持**参数驱动建模**与**阵列化蓝图复用**。

## 2. 核心组件关系 (High-Level View)

### 框架分层

- **SimRunner**：控制层
- **SimSetup**：业务层
- **SimWorkflow**：适配层
- **Structure**：构建层
- **IBuilder**：接口层

### 外部依赖

- **CST/HFSS**：仿真软件

### 交互流程

1. SimRunner 驱动生命周期，启动 SimSetup。
2. SimSetup 注入 Workflow，将业务逻辑传递给 SimWorkflow。
3. SimWorkflow 持有 Builder，通过 IBuilder 接口调用底层功能。
4. SimWorkflow 组合 Structure，使用其进行几何建模。
5. IBuilder 的具体实现由 CST/HFSS 提供，框架通过多态机制调用。
6. Structure 在建模时调用 IBuilder 的 API，最终映射为仿真软件的具体操作。

## 3. 详细模块解析 (Component Breakdown)

本框架由四个核心类构成，它们分别位于不同的抽象层级：

| 层级 | 类名 | 职责描述 | 核心设计模式 |
| :--- | :--- | :--- | :--- |
| **L1** | **SimRunner** | **“总指挥”**负责软件的启动/关闭、模式切换（保存 vs 求解）。 | 模板方法模式(Template Method) |
| **L2** | **SimSetup** | **“策略家”**定义“算什么”（频率、尺寸）。不关心底层软件细节。 | 依赖注入(Dependency Injection) |
| **L3** | **SimWorkflow** | **“翻译官”**定义“怎么做”（参数同步、材料定义）。将通用指令翻译给具体软件。 | 抽象基类(Abstract Base Class) |
| **L4** | **Structure** | **“工匠”**执行具体的几何构建（单体模式）或记录蓝图（阵列模式）。 | 状态机模式(State Machine) |

## 4. 关键交互流程 (Interaction Flow)

场景：执行一次阵列天线仿真

1. **初始化 (Initialization)**
   - `SimRunner` 启动，创建仿真软件上下文（Context）。
   - `SimRunner` 实例化 `SimSetup` 子类，并将具体的 `SimWorkflow` 实例注入到 `SimSetup` 中。
   - `SimWorkflow` 在初始化时创建 `Structure` 实例，并将 `IBuilder`（具体的软件 API 封装）注入给 `Structure`。
2. **蓝图录制 (Blueprint Recording)**
   - **流向：** `SimSetup` -> `SimWorkflow` -> `Structure`
   - `SimSetup` 调用 `self.simulation.structure.start_unit_definition("Patch")`。
   - `Structure` 切换至 **录制模式** (`_is_recording=True`)。
   - `SimSetup` 调用 `create_brick` 等方法。
   - `Structure` 拦截这些调用，将参数存入 `_operations` 列表，**不**生成实际几何体。
3. **参数同步与建模 (Execution)**
    - **流向：** `SimSetup` -> `SimWorkflow` -> `IBuilder` -> `Software`
    - `SimSetup` 计算完所有参数（如 `freq=5.8GHz`）。
    - `SimSetup` 调用 `self.simulation.sync_parameters_to_software()`。
    - `SimWorkflow` 调用底层 `IBuilder` 的 API，在软件中创建参数和材料。
    - `SimSetup` 结束录制，`Structure` 将蓝图保存为不可变序列。
4. **阵列实例化 (Array Instantiation)**
   - **流向：** `ArrayStructure` (未展示，但由 `Structure` 衍生) -> `IBuilder`
   - 框架读取 `Structure` 中存储的蓝图序列。
   - 结合阵列排布算法（位置偏移），循环调用 `IBuilder` 批量生成几何体。

## 5. 核心设计 (Design Highlights)

### A. 软件无关性 (Software Agnosticism)

通过 `SimWorkflow` 和 `IBuilder` 的双重抽象，上层业务逻辑（`SimSetup`）完全不知道底层是 CST 还是 HFSS。切换软件只需替换 `SimWorkflow` 的子类和 `IBuilder` 的实现，无需修改业务代码。

### B. 蓝图模式 (Blueprint Pattern)

`Structure` 类利用 `_is_recording` 标志位实现了**元编程**思想。

- **普通模式**：操作即时生效。
- **蓝图模式**：操作被序列化为“代码的代码”（操作字典）。这使得构建 100 个阵列单元时，不需要重复执行复杂的 Python 逻辑判断，只需将蓝图“复印” 100 次并替换坐标参数，极大提升了大规模阵列的建模效率。

### C. 上下文单例 (Context Singleton)

`SimSetup` 利用静态变量 `_current_setup` 实现了线程局部的单例模式。这允许在复杂的几何构建函数（可能位于独立的 `.py` 文件中）直接访问当前的仿真参数，而不需要层层传递参数对象，简化了 API 的使用难度。
