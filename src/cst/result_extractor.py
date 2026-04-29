# -*- coding: utf-8 -*-
import os
import copy
import time
import datetime
import h5py
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
import cst.results as cstr
from src.core.sim_runner import SimulationMode
from src.core.result_extractor import ResultExtractor
from src.core.sim_setup import SimSetup
from src.cst.vba import CSTVBA
from src.cst.app import CSTProject
from src.utils.logger import logger

class CSTResultExtractor(ResultExtractor):
    """
    CST 专用结果提取器
    """

    def __init__(self, cst_project: CSTProject, setup_dict: Dict[str, Any]):
        """
        Args:
            cst_project: CST 项目对象
            ensure_export_dir: 在 
        """
        super().__init__()
        self.cst_project = cst_project
        self.result_project = None
        self.setup_dict = setup_dict
            
        self.timestamp_prefix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def _ensure_results_loaded(self):
        """
        确保 CST 结果项目已加载。
        
        使用 cst.results 模块进行后台数据读取。
        设置 allow_interactive=True 允许在 CST GUI 打开项目的同时读取数据。
        """
        if self.result_project is None:
            try:
                # 1. 获取原始路径
                filename = self.cst_project.filename()
                
                # 强制转换为绝对路径，防止工作目录切换导致文件找不到
                filename = os.path.abspath(filename)
                
                # 2. 加载结果文件
                # allow_interactive=True: 允许与 CST GUI 共享文件锁，读取当前打开项目的结果
                self.result_project = cstr.ProjectFile(filename, allow_interactive=True)
                
                logger.debug(f"CST 结果引擎已加载 (交互模式): {filename}")
                
            except Exception as e:
                logger.error(f"无法加载结果项目文件: {e}")
                raise

    def execute_export(self) -> Dict[str, Any]:
        """
        核心执行方法。
                
        Returns:
            Dict: 提取的数据字典
        """
        if self.setup_dict is None:
            logger.error("致命错误：setup_dict 为空！请检查 Runner 是否正确传参。")
            raise ValueError("setup_dict 不能为 None")
        export_options = self.setup_dict.get('export_options')
        simulation_mode = self.setup_dict.get('simulation_mode')
        logger.debug(f"开始执行导出任务, 配置项: {export_options}")

        result_dict = {}
        

        for opt in export_options:
            logger.debug(f"Processing option '{opt}'")
            try:
                data_dict = None

                if opt == "s_parameters":
                    data_dict = self.extract_s_parameters(port_type="standard")
                elif opt == "s_floquet":
                    data_dict = self.extract_s_parameters(port_type="floquet")
                elif opt == "realized_gain":
                    data_dict = self.extract_realized_gain()
                elif opt == "farfield":
                    if simulation_mode == SimulationMode.DESIGN:
                        # 单次模式：执行远场3D数据提取
                        file_path = self.extract_farfield_3d()
                        logger.debug(f"远场数据已保存: {file_path}")
                        continue 

                if data_dict is not None:
                    result_dict[opt] = copy.deepcopy(data_dict)

            except Exception as e:
                logger.error(f"导出 {opt} 失败: {e}")
                continue

        return result_dict

    def extract_s_parameters(self, port_type: str = "standard") -> Dict[str, Any]:
        """
        提取 S 参数的统一入口方法。
        """
        if port_type == "standard":
            return self._extract_standard_s_params()
        elif port_type == "floquet":
            return self._extract_floquet_s_params()
        else:
            raise ValueError(f"不支持的端口类型: {port_type}")
        
    def _extract_standard_s_params(self) -> Dict[str, Any]:
        """提取标准 S 参数。"""
        logger.debug("_extract_standard_s_params: Starting extraction.")
        self._ensure_results_loaded()
        
        try:
            result_3d = self.result_project.get_3d()
            all_run_ids = result_3d.get_all_run_ids()
            valid_run_ids = all_run_ids[1:] 
            if not valid_run_ids:
                raise ValueError("未找到有效的仿真结果 (Run ID 为空)")
            target_run_id = valid_run_ids[-1]

            s_param_path = "1D Results\\S-Parameters\\S1,1"
            s11_item = result_3d.get_result_item(s_param_path, run_id=target_run_id)
            time.sleep(1)
            if s11_item is None:
                raise ValueError(f"未找到 S 参数路径: {s_param_path}")

            freq_raw = s11_item.get_xdata()
            s11_raw = s11_item.get_ydata()

            if not freq_raw or not s11_raw:
                raise ValueError("提取的 S 参数数据为空")

            freq = np.asarray(freq_raw)
            s11_complex = np.asarray(s11_raw)

            # 检查有效性
            if s11_complex.dtype == np.object_ or np.isnan(s11_complex).any() or np.isinf(s11_complex).any():
                if s11_complex.dtype == np.object_:
                    if any(v is None for v in s11_complex.flat):
                        raise ValueError("S 参数数据中包含无效值 (None)")
                if np.isnan(s11_complex).any():
                    raise ValueError("S 参数数据中包含 NaN 值")
                if np.isinf(s11_complex).any():
                    raise ValueError("S 参数数据中包含 Inf 值")

            # 计算幅度和相位
            s11_abs = np.abs(s11_complex)
            s11_abs_safe = np.where(s11_abs == 0.0, 1e-20, s11_abs)
            s11_db = 20 * np.log10(s11_abs_safe)
            s11_phase = np.angle(s11_complex, deg=True)

            # 构建数据字典
            data_dict = { 
                "freq": freq,
                "S11_dB": s11_db,
                "S11_Phase": s11_phase,
                "info": {"type": "Standard S-Parameters", "port_type": "standard"}
            }

            logger.debug(f"标准 S 参数提取成功: {len(freq)} 个频点")
            
            if not isinstance(data_dict, dict):
                logger.critical(f"CRITICAL: data_dict is NOT a dict! It's a {type(data_dict)}")
                raise TypeError(f"CRITICAL: _extract_standard_s_params constructed a non-dict: {type(data_dict)}, value: {data_dict}")
            
            return data_dict
                
        except Exception as e:
            error_msg = f"致命错误：标准 S 参数提取失败。请检查 CST 结果树路径是否为 '1D Results\\S-Parameters\\S1,1' 及其数据有效性。详情: {e}"
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

    def _extract_floquet_s_params(self) -> Dict[str, Any]:
        """提取 Floquet S 参数。"""
        logger.debug("_extract_floquet_s_params: Starting extraction.")
        self._ensure_results_loaded()
        
        try:
            run_ids = self.result_project.get_3d().get_all_run_ids()[1:]
            if not run_ids:
                raise ValueError("未找到仿真结果 Run ID")
            target_run_id = run_ids[-1]

            items = [
                ('S11_M1_mag', '1D Results\\S-Parameters\\SZmax(1),Zmax(1)'),
                ('S11_M2_mag', '1D Results\\S-Parameters\\SZmax(2),Zmax(2)')
            ]

            base_freq = None
            collected_data = {}

            for field_name_base, treepath in items:
                floquet_item = self.result_project.get_3d().get_result_item(treepath, run_id=target_run_id)
                if floquet_item is None:
                    logger.warning(f"未找到 Floquet 路径: {treepath}")
                    continue 

                freq_raw = floquet_item.get_xdata()
                s_raw_raw = floquet_item.get_ydata()

                if not freq_raw or not s_raw_raw:
                    logger.warning(f"Floquet 路径 {treepath} 数据为空，跳过")
                    continue

                freq = np.asarray(freq_raw)
                s_raw = np.asarray(s_raw_raw)

                # 检查有效性
                if s_raw.dtype == np.object_:
                    invalid_elements = [v for v in s_raw.flat if v is None]
                    if invalid_elements:
                        raise ValueError(f"Floquet 路径 {treepath} 数据包含 None 值: {invalid_elements}")
                
                if np.isnan(s_raw).any():
                    raise ValueError(f"Floquet 路径 {treepath} 数据包含 NaN 值")
                
                if np.isinf(s_raw).any():
                    raise ValueError(f"Floquet 路径 {treepath} 数据包含 Inf 值")

                # 检查频率一致性
                if base_freq is None:
                    base_freq = freq
                elif not np.array_equal(base_freq, freq):
                    logger.warning(f"Floquet 路径 {treepath} 频率轴与首个路径不一致，跳过")
                    continue

                # 计算幅度和相位
                s_abs = np.abs(s_raw)
                s_abs_safe = np.where(s_abs == 0.0, 1e-20, s_abs)
                s_mag_db = 20 * np.log10(s_abs_safe)
                s_phase_deg = np.angle(s_raw, deg=True)

                # 存储计算结果
                collected_data[field_name_base] = s_mag_db
                phase_field_name = field_name_base.replace('_mag', '_phase')
                collected_data[phase_field_name] = s_phase_deg

            if not collected_data:
                raise ValueError("未能从任何 Floquet 路径提取到有效数据")

            # 构建最终返回字典
            final_data = {
                "freq": base_freq,
                **collected_data,
                "info": {"type": "Floquet S-Parameters", "port_type": "floquet"}
            }

            logger.debug(f"Floquet S 参数提取完成，共 {len(base_freq)} 个频点")
            return final_data

        except Exception as e:
            error_msg = f"致命错误：Floquet S 参数提取失败。请检查 CST 结果树路径是否为 'SZmax(1),Zmax(1)' / 'SZmax(2),Zmax(2)' 及其数据有效性。详情: {e}"
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

    def extract_realized_gain(self, Theta: float = 0, Phi: float = 90) -> Dict[str, Any]:
        """
        提取 Realized Gain 数据。
        """
        vba_logic = f'''
            Dim nResults As Long
            Dim paths As Variant, types As Variant, files As Variant, infos As Variant
            Dim k As Long
            Dim currentTreePath As String, currentFileName As String
            Dim gainValue As Double
            Dim freqStr As String, freqValue As Double
            Dim startPos As Long, endPos As Long
            
            Dim freqResult As String
            Dim gainResult As String
            freqResult = ""
            gainResult = ""
            
            nResults = ResultTree.GetTreeResults("Farfields", "farfield", "", paths, types, files, infos)
            For k = 0 To nResults - 1
                currentTreePath = CStr(paths(k))
                currentFileName = CStr(files(k))
                
                startPos = InStr(currentFileName, "(f=")
                If startPos > 0 Then
                    endPos = InStr(startPos, currentFileName, ")")
                    If endPos > startPos Then
                        freqStr = Mid(currentFileName, startPos + 3, endPos - startPos - 3)
                        freqValue = CDbl(freqStr)
                    End If
                End If
                
                With FarfieldCalculator
                    .ClearList
                    .AddListEvaluationPoint("{Theta}", "{Phi}", 1.0, "spherical", "", "")
                    .CalculateList(currentTreePath, "farfield")
                    gainValue = .GetListItem(0, "realized gain", "spherical linear copolar abs")
                End With
                
                If k > 0 Then 
                    freqResult = freqResult & "|" 
                    gainResult = gainResult & "|"
                End If
                freqResult = freqResult & Format(freqValue, "0.000000")
                gainResult = gainResult & Format(gainValue, "0.000000")
            Next k
            
            SetGlobalVariable "Gain_Freq_String", freqResult
            SetGlobalVariable "Gain_Value_String", gainResult
        '''
        
        vba_executor = CSTVBA(self.project)
        vba_executor.execute(vba_logic)

        try:
            freq_str = self.project.GetGlobalVariable("Gain_Freq_String")
            gain_str = self.project.GetGlobalVariable("Gain_Value_String")
            
            freqs_np = np.array([float(x) for x in freq_str.split('|')]) if freq_str else np.array([])
            gains_np = np.array([float(x) for x in gain_str.split('|')]) if gain_str else np.array([])

            data_dict = {
                "freq": freqs_np,
                "Gain_dBi": gains_np,
                "meta": {"Theta": Theta, "Phi": Phi, "type": "Realized Gain"}
            }
            
            logger.debug("Realized Gain 数据已提取")
            return data_dict

        except Exception as e:
            logger.error(f"处理增益数据失败: {e}")
            raise

    def extract_farfield_3d(self) -> str:
        """提取远场3D数据并保存为HDF5"""
        self._ensure_results_loaded()
        self.project.activate()

        setup = SimSetup.get_current()
        ff_cfg = getattr(setup, 'farfield_config', None)
        if ff_cfg is None:
            raise ValueError(f"SimSetup ({type(setup).__name__}) 缺少 'farfield_config' 属性。")

        required_keys = ['frequency_name', 'mode', 'port']
        missing_keys = [k for k in required_keys if k not in ff_cfg]
        if missing_keys:
            raise ValueError(f"'farfield_config' 缺少必需的键: {missing_keys}")

        farfield_name = ff_cfg['frequency_name']
        mode = ff_cfg['mode']
        port = ff_cfg['port']

        file_base_name = f"{self.timestamp_prefix}_Farfield_f_{farfield_name}_port{port}"
        h5_filename = f"{file_base_name}.h5"
        result_file = os.path.join(self.export_root, h5_filename)

        farfield_plot_obj = self.project.model3d.FarfieldPlot
        ascii_export = self.project.model3d.ASCIIExport
        
        farfield_result_tree_entry = f"Farfields\\farfield (f={farfield_name}) [{port}]"
        
        try:
            self.project.model3d.SelectTreeItem(farfield_result_tree_entry)
        except Exception as e:
            logger.error(f"选择远场结果树项失败: '{farfield_result_tree_entry}'. 错误: {e}")
            raise 

        try:
            farfield_plot_obj.Reset()              
            farfield_plot_obj.SetPlotMode(mode)    
            farfield_plot_obj.Plottype("3d")       
            farfield_plot_obj.Step(1)              
            farfield_plot_obj.Step2(1)             
            farfield_plot_obj.SetLockSteps(True)   
            farfield_plot_obj.SetScaleLinear(True)   
            farfield_plot_obj.Plot()     
            time.sleep(1.0)          
        except Exception as e:
            logger.error(f"配置或更新远场绘图失败。错误: {e}")
            raise

        try:
            logger.debug(f"开始 HDF5 导出到: {result_file}")
            ascii_export.Reset()
            ascii_export.SetFileType("hdf5")       
            ascii_export.FileName(result_file)     
            ascii_export.Mode("FixedWidth")        
            ascii_export.Execute()                 
            logger.debug(f"远场 HDF5 数据已导出: {result_file}")
        except Exception as e:
            logger.error(f"HDF5 导出失败。目标文件: {result_file}. 错误: {e}")
            raise 

        try:
            farfield_plot_obj.Reset()
            farfield_plot_obj.Plottype("3d")
            farfield_plot_obj.Step(5)              
            farfield_plot_obj.SetLockSteps(True)
            farfield_plot_obj.SetScaleLinear(False)  
            farfield_plot_obj.Plot()
        except Exception as e:
            logger.warning(f"重置 GUI 远场设置时出现问题 (不影响数据导出): {e}")

        return result_file
    
    
    
    # def extract_realized_gain(self, Theta: float = 0, Phi: float = 90) -> Tuple[np.ndarray, np.ndarray]:
    #     """
    #     [CST实现] 提取 Realized Gain 数据。
    #     """
    #     csv_filename = f"{self.timestamp_prefix}_Gain.csv" 
    #     csv_full_path = os.path.join(self.project.folder(), csv_filename)
    #     vba_safe_path = csv_full_path.replace('\\', '\\\\')
        
    #     if os.path.exists(csv_full_path):
    #         os.remove(csv_full_path)

    #     # VBA 逻辑体
    #     vba_logic = f'''
    #         Dim nResults As Long
    #         Dim paths As Variant, types As Variant, files As Variant, infos As Variant
    #         Dim k As Long
    #         Dim currentTreePath As String, currentFileName As String
    #         Dim gainValue As Double
    #         Dim freqStr As String, freqValue As Double
    #         Dim startPos As Long, endPos As Long

    #         ReportInformationToWindow("Extracting Realized Gain...")

    #         nResults = ResultTree.GetTreeResults("Farfields", "farfield", "", paths, types, files, infos)

    #         Dim fileNum As Integer
    #         Dim savePath As String
    #         savePath = "{vba_safe_path}"

    #         fileNum = FreeFile
    #         Open savePath For Output As #fileNum
    #         Print #fileNum, "Frequency_GHz,Realized_Gain_dBi"

    #         For k = 0 To nResults - 1
    #             currentTreePath = CStr(paths(k))
    #             currentFileName = CStr(files(k))

    #             startPos = InStr(currentFileName, "(f=")
    #             If startPos > 0 Then
    #                 endPos = InStr(startPos, currentFileName, ")")
    #                 If endPos > startPos Then
    #                     freqStr = Mid(currentFileName, startPos + 3, endPos - startPos - 3)
    #                     freqValue = CDbl(freqStr)
    #                 End If
    #             End If

    #             With FarfieldCalculator
    #                 .ClearList
    #                 .AddListEvaluationPoint("{Theta}", "{Phi}", 1.0, "spherical", "", "")
    #                 .CalculateList(currentTreePath, "farfield")
    #                 gainValue = .GetListItem(0, "realized gain", "spherical linear copolar abs")
    #             End With

    #             Print #fileNum, Format(freqValue, "0.0000") & "," & Format(gainValue, "0.0000")

    #         Next k

    #         Close #fileNum
    #         ReportInformationToWindow "Gain data export completed."
    #     '''
        
    #     logger.info(f"正在计算 Realized Gain (Theta={Theta}, Phi={Phi})...")
        
    #     # 使用 CSTVBA 类执行代码
    #     vba_executor = CSTVBA(self.project)
    #     # 这是一个阻塞代码，执行结束后 Python 才会继续执行
    #     vba_executor.execute(vba_logic)

    #     # 等待文件写入完成
    #     time.sleep(3)
        
    #     if not os.path.exists(csv_full_path):
    #         raise FileNotFoundError(f"增益数据文件未生成: {csv_full_path}")
            
    #     try:
    #         df = pd.read_csv(csv_full_path)
    #         logger.info(f"成功提取 {len(df)} 个频点的增益数据。")
    #         return df["Frequency_GHz"].values, df["Realized_Gain_dBi"].values
            
    #     except Exception as e:
    #         logger.error(f"读取增益 CSV 失败: {e}")
    #         raise