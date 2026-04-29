# result_gain_processor.py
import os
import time
import numpy as np
import pandas as pd
from typing import Tuple
from .app import CSTBase
from ..utils.logger import logger


class CSTGainProcessor(CSTBase):
    """CST Realized Gain 后处理模块"""

    def extract_realized_gain(self, Theta: float = 0, Phi: float = 90) -> Tuple[np.ndarray, np.ndarray]:
        """
        提取 Realized Gain 数据 (通过 VBA 导出 CSV)
        
        Args:
            Theta: 球坐标系 Theta 角
            Phi: 球坐标系 Phi 角
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: 频率数组, 增益数组
        """
        project_path = self.project.folder()
        csv_filename = "exported_gain_data.csv"
        csv_full_path = os.path.join(project_path, csv_filename)
        
        # 处理路径转义
        vba_safe_path = csv_full_path.replace('\\', '\\\\')
        
        # 清理旧文件
        if os.path.exists(csv_full_path):
            os.remove(csv_full_path)

        # VBA 宏定义 
        vba_macro = f'''
        Sub Main()
            Dim nResults As Long
            Dim paths As Variant, types As Variant, files As Variant, infos As Variant
            Dim k As Long
            Dim currentTreePath As String, currentFileName As String
            Dim gainValue As Double
            Dim freqStr As String, freqValue As Double
            Dim startPos As Long, endPos As Long

            ' 声明一个 Result1D 对象
            Dim oGainCurve As Object
            '创建一个空的 Result1D 对象
            Set oGainCurve = Result1D("")

            ' 定义数组用于暂存数据
            Dim freqArray() As Double
            Dim gainArray() As Double

            ReportInformationToWindow("提取 Realized Gain")
            ReportInformationToWindow("频率 (GHz)       |  实际增益 (dBi)")

            ' 获取所有远场结果
            nResults = ResultTree.GetTreeResults("Farfields", "farfield", "", paths, types, files, infos)

            Dim fileNum As Integer
            Dim savePath As String
            savePath = "{vba_safe_path}"

            fileNum = FreeFile
            Open savePath For Output As #fileNum
            Print #fileNum, "Frequency_GHz,Realized_Gain_dBi" ' 写入表头

            ' 初始化数组大小
            ReDim freqArray(nResults - 1)
            ReDim gainArray(nResults - 1)

            For k = 0 To nResults - 1
                currentTreePath = CStr(paths(k))
                currentFileName = CStr(files(k))

                ' 解析频率
                startPos = InStr(currentFileName, "(f=")
                If startPos > 0 Then
                    endPos = InStr(startPos, currentFileName, ")")
                    If endPos > startPos Then
                        freqStr = Mid(currentFileName, startPos + 3, endPos - startPos - 3)
                        freqValue = CDbl(freqStr)
                        freqStr = Format(freqValue, "0.0000")
                    End If
                End If


                With FarfieldCalculator
                    .ClearList

                    ' 1. 添加评估点
                    ' 默认 Theta=0, Phi=90
                    ' CST 默认坐标系是 Spherical (球坐标)
                    ' 默认半径 1.0 m
                    .AddListEvaluationPoint({Theta}, {Phi}, 1.0, "spherical", "", "")

                    ' 2. 执行计算
                    .CalculateList(currentTreePath, "farfield")

                    ' 3. 获取结果
                    'fieldComponent = <Coord.System> +" " + <Polarization> +" " + <Component> +" " + <ComplexComp.>
                    'Co-polar（共极化）与天线设计的主极化方向一致的分量
                    gainValue = .GetListItem(0, "realized gain", "spherical linear copolar abs")

                End With

                ' 将数据点追加到 Result1D 对象中
                ' oGainCurve.AppendXY freqValue, gainValue

                ' 将数值存入数组
                freqArray(k) = freqValue
                gainArray(k) = gainValue

                ReportInformationToWindow freqStr & "       |  " & Format(gainValue, "0.00")

                ' 写入 CSV
                Print #fileNum, Format(freqValue, "0.0000") & "," & Format(gainValue, "0.0000")

            Next k

            Close #fileNum
            ReportInformationToWindow "数据已导出至: " & savePath
        End Sub
        '''
        # CST API 调用，执行 VBA 代码
        self.project.schematic.execute_vba_code(vba_macro)
        time.sleep(5) # 等待文件生成

        if not os.path.exists(csv_full_path):
            raise FileNotFoundError(f"File not generated: {csv_full_path}")
            
        df = pd.read_csv(csv_full_path)
        return df["Frequency_GHz"].values, df["Realized_Gain_dBi"].values