#!/usr/bin/env python3
import sys
import subprocess
import json
import re
import os
import time
import shutil
import platform
from i18n import init_i18n, _

def get_video_info(url):
    """獲取影片格式資訊"""
    try:
        print(_("正在獲取影片資訊，請稍候..."))
        
        # 修改URL，確保只處理單個影片而不是播放清單
        # 移除播放清單相關參數
        url = re.sub(r'&list=[^&]*', '', url)
        url = re.sub(r'\?list=[^&]*&', '?', url)
        url = re.sub(r'\?list=[^&]*$', '', url)
        
        # 添加 --no-playlist 參數確保只處理單個影片
        cmd = ["yt-dlp", "-J", "--no-playlist", url]
        print(_("執行命令：{cmd}").format(cmd=' '.join(cmd)))
        
        # 設定逾時時間，防止永久等待
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(_("錯誤：無法獲取影片資訊\n{error}").format(error=result.stderr))
            sys.exit(1)
        
        # 解析 JSON 輸出
        video_info = json.loads(result.stdout)
        return video_info
    except subprocess.TimeoutExpired:
        print(_("錯誤：獲取影片資訊逾時，請檢查網路連線或嘗試簡化URL"))
        sys.exit(1)
    except json.JSONDecodeError:
        print(_("錯誤：解析影片資訊失敗，收到的不是有效的JSON資料"))
        sys.exit(1)
    except Exception as e:
        print(_("獲取影片資訊時發生錯誤：{error}").format(error=e))
        sys.exit(1)

def filter_formats(formats):
    """篩選出影片和聲音格式"""
    video_formats = []
    audio_formats = []
    
    for fmt in formats:
        if fmt.get('vcodec') != 'none' and fmt.get('acodec') == 'none':
            # 僅影片
            video_formats.append(fmt)
        elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
            # 僅聲音
            audio_formats.append(fmt)
    
    return video_formats, audio_formats

def get_best_formats(video_formats, audio_formats):
    """找出最高畫質和最高音質的格式"""
    # 按解析度和位元率排序影片格式
    sorted_videos = sorted(
        video_formats, 
        key=lambda x: (
            x.get('height', 0) or 0,  # 先按照高度排序
            x.get('tbr', 0) or 0      # 然後按照總位元率排序
        ), 
        reverse=True
    )
    
    # 按位元率排序聲音格式
    sorted_audios = sorted(
        audio_formats, 
        key=lambda x: x.get('tbr', 0) or 0,  # 按照總位元率排序
        reverse=True
    )
    
    if not sorted_videos:
        print(_("警告：找不到影片流"))
        return None, sorted_audios[0] if sorted_audios else None
    
    if not sorted_audios:
        print(_("警告：找不到聲音流"))
        return sorted_videos[0], None
    
    return sorted_videos[0], sorted_audios[0]

def print_format_info(format_info, format_type):
    """顯示格式資訊"""
    if not format_info:
        print(_("沒有找到{format_type}格式").format(format_type=format_type))
        return
    
    print(_("最佳{format_type}格式資訊:").format(format_type=format_type))
    print(_("  格式ID: {format_id}").format(format_id=format_info.get('format_id')))
    
    if format_type == "影片":
        print(_("  解析度: {width}x{height}").format(
            width=format_info.get('width'), 
            height=format_info.get('height')
        ))
        print(_("  編碼: {codec}").format(codec=format_info.get('vcodec')))
        print(_("  FPS: {fps}").format(fps=format_info.get('fps')))
    else:  # 聲音
        print(_("  編碼: {codec}").format(codec=format_info.get('acodec')))
        print(_("  頻率: {asr}").format(asr=format_info.get('asr')))
    
    print(_("  位元率: {tbr}k").format(tbr=format_info.get('tbr')))
    
    if format_info.get('filesize_approx'):
        size_mb = format_info.get('filesize_approx', 0) / (1024*1024)
        print(_("  檔案大小: {size:.2f} MB").format(size=size_mb))
    else:
        print(_("  檔案大小: 未知"))
        
    print(_("  副檔名: {ext}").format(ext=format_info.get('ext')))

def detect_hardware_acceleration():
    """偵測系統支援的硬體加速方式"""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        print(_("偵測到 macOS 作業系統，將使用 VideoToolbox 硬體加速"))
        return {
            "encoder": "hevc_videotoolbox",
            "hwaccel": "videotoolbox",
            "options": ["-allow_sw", "1"]  # 允許軟體回退
        }
    
    elif system == "Windows":
        # 嘗試偵測 GPU 類型
        try:
            # 檢查 NVIDIA GPU
            nvidia_result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
            if nvidia_result.returncode == 0:
                print(_("偵測到 NVIDIA GPU，將使用 NVENC 硬體加速"))
                return {
                    "encoder": "hevc_nvenc",
                    "hwaccel": "cuda",
                    "options": ["-rc", "vbr_hq"]  # 使用高品質可變位元率模式
                }
        except FileNotFoundError:
            pass  # 沒有 NVIDIA GPU 或驅動程式
        
        try:
            # 檢查 AMD GPU (Windows)
            # 使用 PowerShell 檢查顯示卡資訊
            ps_command = "Get-WmiObject Win32_VideoController | Select-Object -Property Name"
            gpu_info = subprocess.run(["powershell", "-Command", ps_command], capture_output=True, text=True)
            
            if "AMD" in gpu_info.stdout:
                print(_("偵測到 AMD GPU，將使用 AMF 硬體加速"))
                return {
                    "encoder": "hevc_amf",
                    "hwaccel": "amf",
                    "options": ["-quality", "quality"]
                }
        except Exception:
            pass  # PowerShell 命令執行失敗或無法識別
        
        try:
            # 檢查 Intel GPU (Windows)
            if "Intel" in gpu_info.stdout:
                print(_("偵測到 Intel GPU，將使用 QSV 硬體加速"))
                return {
                    "encoder": "hevc_qsv",
                    "hwaccel": "qsv",
                    "options": ["-load_plugin", "hevc_hw"]
                }
        except Exception:
            pass  # 無法識別 Intel GPU
    
    elif system == "Linux":
        # 在 Linux 上嘗試偵測 GPU
        try:
            # 檢查 NVIDIA GPU
            nvidia_result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
            if nvidia_result.returncode == 0:
                print(_("偵測到 NVIDIA GPU，將使用 NVENC 硬體加速"))
                return {
                    "encoder": "hevc_nvenc",
                    "hwaccel": "cuda",
                    "options": ["-rc", "vbr_hq"]
                }
        except FileNotFoundError:
            pass  # 沒有 NVIDIA GPU 或驅動程式
        
        try:
            # 檢查 VAAPI 支援 (Intel/AMD on Linux)
            vaapi_result = subprocess.run(["vainfo"], capture_output=True, text=True)
            if vaapi_result.returncode == 0 and "HEVC" in vaapi_result.stdout:
                print(_("偵測到 VAAPI 支援 (Intel/AMD GPU)，將使用 VAAPI 硬體加速"))
                return {
                    "encoder": "hevc_vaapi",
                    "hwaccel": "vaapi",
                    "options": ["-vaapi_device", "/dev/dri/renderD128"]
                }
        except FileNotFoundError:
            pass  # 沒有 VAAPI 支援
    
    # 如果沒有找到任何硬體加速方式，使用軟體編碼
    print(_("未偵測到支援的硬體加速，將使用 CPU 編碼"))
    return {
        "encoder": "libx265",
        "hwaccel": None,
        "options": ["-preset", "medium"]
    }

def download_video(url, video_format, audio_format, output_dir=None, convert_hevc=True):
    """下載影片並選擇性轉換為H.265格式"""
    if not video_format and not audio_format:
        print(_("錯誤：沒有找到可下載的格式"))
        return None
    
    # 移除播放清單參數
    url = re.sub(r'&list=[^&]*', '', url)
    url = re.sub(r'\?list=[^&]*&', '?', url)
    url = re.sub(r'\?list=[^&]*$', '', url)
    
    # 準備下載命令
    cmd = ["yt-dlp"]
    
    # 處理格式
    if video_format and audio_format:
        format_str = f"{video_format['format_id']}+{audio_format['format_id']}"
    elif video_format:
        format_str = video_format['format_id']
    else:
        format_str = audio_format['format_id']
    
    cmd.extend(["-f", format_str])
    
    # 不下載播放清單
    cmd.append("--no-playlist")
    
    # 增加進度條顯示
    cmd.append("--progress")
    
    # 處理輸出路徑
    if output_dir:
        # 檢查目錄是否存在，如果不存在則建立
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                print(_("已建立目錄：{dir}").format(dir=output_dir))
            except Exception as e:
                print(_("無法建立目錄 {dir}：{error}").format(dir=output_dir, error=e))
                output_dir = "."
    else:
        output_dir = "."
    
    # 先儲存成臨時檔案名稱，方便後續轉檔
    temp_output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd.extend(["-o", temp_output_template])
    
    # 取得影片實際檔名，供後續轉檔使用
    cmd.extend(["--print", "after_move:filepath"])
    
    # 添加URL
    cmd.append(url)
    
    print(_("即將下載影片，使用以下命令："))
    print(" ".join(cmd))
    print(_("下載中..."))
    
    # 執行下載
    try:
        # 使用即時輸出顯示進度
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        
        output_file = None
        for line in process.stdout:
            print(line, end='')
            # 擷取檔案路徑
            if not output_file and os.path.isfile(line.strip()):
                output_file = line.strip()
            
        process.wait()
        
        if process.returncode != 0:
            print(_("下載失敗，回傳代碼: {code}").format(code=process.returncode))
            return None
        
        print(_("下載完成！"))
        
        # 如果沒有找到檔案路徑，嘗試搜尋目錄中最新的檔案
        if not output_file:
            files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) 
                     if os.path.isfile(os.path.join(output_dir, f))]
            if files:
                output_file = max(files, key=os.path.getmtime)
                print(_("找到下載的檔案：{file}").format(file=output_file))
            else:
                print(_("警告：無法確定下載的檔案位置"))
                return None
        
        return output_file
        
    except Exception as e:
        print(_("下載過程中發生錯誤：{error}").format(error=e))
        return None

def convert_to_hevc(input_file, video_format, audio_format):
    """將影片轉換為H.265格式，保持相同的位元率和解析度，並使用硬體加速"""
    if not input_file or not os.path.exists(input_file):
        print(_("錯誤：找不到要轉換的檔案"))
        return None
    
    print(_("開始將 {file} 轉換為 H.265 格式...").format(file=os.path.basename(input_file)))
    
    # 首先重命名檔案
    base_dir = os.path.dirname(input_file)
    file_ext = os.path.splitext(input_file)[1]
    temp_file = os.path.join(base_dir, f"temp_for_conversion{file_ext}")
    
    # 準備最終輸出檔案名稱 (HEVC_ + 原始檔名.mp4)
    original_basename = os.path.basename(input_file)
    original_name_without_ext = os.path.splitext(original_basename)[0]
    final_output_file = os.path.join(base_dir, f"HEVC_{original_name_without_ext}.mp4")
    
    # 初始轉換時使用臨時輸出名稱
    temp_output_file = os.path.join(base_dir, "converted_HEVC.mp4")
    
    try:
        # 刪除原本臨時檔案
        if os.path.exists(temp_output_file):
            os.remove(temp_output_file)
        # 複製檔案而不是移動，以保留原始檔案
        shutil.copy2(input_file, temp_file)
        print(_("已複製檔案以便轉換"))
        
        # 從原始格式中獲取影片參數
        video_bitrate = None
        if video_format and 'tbr' in video_format:
            # 使用與原影片相同的位元率
            video_bitrate = f"{int(video_format['tbr'])}k"
        else:
            # 如果無法取得原始位元率，使用合理的預設值（根據解析度）
            if video_format and 'height' in video_format:
                height = video_format['height']
                if height >= 2160:    # 4K
                    video_bitrate = "30000k"
                elif height >= 1440:  # 2K
                    video_bitrate = "15000k"
                elif height >= 1080:  # 1080p
                    video_bitrate = "8000k"
                elif height >= 720:   # 720p
                    video_bitrate = "4000k"
                else:                # 480p或更低
                    video_bitrate = "2000k"
            else:
                # 預設位元率
                video_bitrate = "8000k"
        
        # 從原始格式中獲取音訊參數
        audio_bitrate = None
        if audio_format and 'tbr' in audio_format:
            # 使用與原始音訊相同的位元率
            audio_bitrate = f"{int(audio_format['tbr'])}k"
        elif audio_format and 'abr' in audio_format and audio_format['abr'] is not None:
            # 部分格式使用 abr 而非 tbr
            audio_bitrate = f"{int(audio_format['abr'])}k"
        else:
            # 預設音訊位元率
            audio_bitrate = "192k"
            print(_("無法確定原始音訊位元率，使用預設值：{bitrate}").format(bitrate=audio_bitrate))
        
        # 從原始格式中獲取FPS
        fps = None
        if video_format and 'fps' in video_format and video_format['fps'] is not None:
            fps = video_format['fps']
        
        # 取得硬體加速資訊
        hw_accel = detect_hardware_acceleration()
        
        # 使用字串命令而不是陣列，確保參數順序正確
        # 這是根據提供的成功執行的命令格式
        cmd_str = (
            f'ffmpeg -hwaccel {hw_accel["hwaccel"]} -i "{temp_file}" ' +
            f'-c:v {hw_accel["encoder"]} '
        )
        
        # 添加硬體加速特定選項
        for option in hw_accel["options"]:
            if isinstance(option, str) and " " not in option:
                cmd_str += f"{option} "
            else:
                cmd_str += f'"{option}" '

        # 添加FPS參數(如果有)
        if fps:
            cmd_str += f'-r {fps} '
        
        # 根據不同編碼器添加特定選項
        if hw_accel["encoder"] == "libx265":
            cmd_str += '-crf 22 -preset medium -tag:v hvc1 '
        elif hw_accel["encoder"] == "hevc_nvenc":
            cmd_str += f'-rc:v vbr -cq:v 22 -b:v {video_bitrate} ' + \
                     f'-maxrate:v {int(float(video_bitrate.replace("k", "")) * 1.5)}k '
        elif hw_accel["encoder"] == "hevc_videotoolbox":
            cmd_str += f'-q:v 50 -b:v {video_bitrate} -tag:v hvc1 '
        elif hw_accel["encoder"] == "hevc_amf":
            cmd_str += f'-quality quality -b:v {video_bitrate} '
        elif hw_accel["encoder"] == "hevc_qsv":
            cmd_str += f'-b:v {video_bitrate} -global_quality 22 '
        elif hw_accel["encoder"] == "hevc_vaapi":
            cmd_str += f'-b:v {video_bitrate} -global_quality 22 '
        
        # 添加音訊編碼設定 - 使用原始音訊位元率
        cmd_str += f'-c:a aac -b:a {audio_bitrate} "{temp_output_file}"'
        
        print(_("執行轉換命令：{cmd}").format(cmd=cmd_str))
        print(_("使用影片位元率: {vbitrate}, 音訊位元率: {abitrate}").format(
            vbitrate=video_bitrate, 
            abitrate=audio_bitrate
        ))
        
        try:
            # 使用shell=True執行命令字串
            process = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            
            # 顯示進度
            for line in process.stdout:
                if "frame=" in line or "time=" in line:
                    print(f"\r{line.strip()}", end='')
                elif "error" in line.lower() or "fatal" in line.lower():
                    print(f"\n錯誤: {line.strip()}")
                
            process.wait()
            
            if process.returncode == 0:
                print(_("轉換完成！"))
                
                # 顯示檔案大小比較
                original_size = os.path.getsize(input_file)
                converted_size = os.path.getsize(temp_output_file)
                compression_ratio = (1 - converted_size / original_size) * 100
                
                print(_("檔案大小比較:"))
                print(_("  原始檔案: {size:.2f} MB").format(size=original_size / (1024*1024)))
                print(_("  轉換後檔案: {size:.2f} MB").format(size=converted_size / (1024*1024)))
                print(_("  節省空間: {ratio:.2f}%").format(ratio=compression_ratio))
                
                # 重命名輸出檔案為原始檔名 + _HEVC.mp4
                try:
                    # 如果最終輸出檔案已存在，先刪除
                    if os.path.exists(final_output_file):
                        os.remove(final_output_file)
                    
                    shutil.move(temp_output_file, final_output_file)
                    print(_("已將輸出檔案重命名為: {file}").format(file=os.path.basename(final_output_file)))
                except Exception as e:
                    print(_("無法重命名輸出檔案: {error}").format(error=e))
                    # 如果重命名失敗，使用原臨時名稱
                    final_output_file = temp_output_file
                
                # 刪除臨時檔案
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                # 刪除原始檔案
                if os.path.exists(input_file):
                    os.remove(input_file)
                
                return final_output_file
            else:
                print(_("轉換失敗，回傳代碼: {code}").format(code=process.returncode))
                
                # 如果硬體加速失敗，嘗試使用軟體編碼
                if hw_accel["encoder"] != "libx265":
                    print(_("硬體加速轉換失敗，嘗試使用 CPU 軟體編碼..."))
                    fallback_output_file = convert_to_hevc_fallback(temp_file, video_format, audio_format, video_bitrate, audio_bitrate, fps, original_name_without_ext, base_dir)
                    
                    # 刪除臨時檔案
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        
                    return fallback_output_file
                
                    # 刪除原始檔案
                    if os.path.exists(input_file):
                        os.remove(input_file)
                    
                return None
        except Exception as e:
            print(_("轉換過程中發生錯誤：{error}").format(error=e))
            
            # 發生錯誤時也嘗試使用軟體編碼
            if hw_accel["encoder"] != "libx265":
                print(_("硬體加速轉換失敗，嘗試使用 CPU 軟體編碼..."))
                fallback_output_file = convert_to_hevc_fallback(temp_file, video_format, audio_format, video_bitrate, audio_bitrate, fps, original_name_without_ext, base_dir)
                
                # 刪除臨時檔案
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    
                return fallback_output_file
            
            # 刪除臨時檔案
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
            return None
    except Exception as e:
        print(_("處理檔案時發生錯誤：{error}").format(error=e))
        
        # 確保清理臨時檔案
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return None


def convert_to_hevc_fallback(input_file, video_format, audio_format, video_bitrate, audio_bitrate, fps, original_name_without_ext=None, base_dir=None):
    """使用軟體編碼的備用轉換方法"""
    # 如果沒有提供原始檔名相關資訊，則從input_file提取
    if original_name_without_ext is None:
        original_basename = os.path.basename(input_file)
        original_name_without_ext = os.path.splitext(original_basename)[0]
    
    if base_dir is None:
        base_dir = os.path.dirname(input_file)
    
    # 確定輸出檔案名稱
    temp_output_file = os.path.join(base_dir, "converted_HEVC_SW.mp4")
    final_output_file = os.path.join(base_dir, f"{original_name_without_ext}_HEVC_SW.mp4")
    
    # 使用字串命令
    cmd_str = f'ffmpeg -i "{input_file}" '
    
    # 如果有FPS資訊，加入命令
    if fps:
        cmd_str += f'-r {fps} '
    
    # 添加影片和聲音編碼設定
    cmd_str += (
        f'-c:v libx265 -crf 22 -preset medium -tag:v hvc1 ' +
        f'-b:v {video_bitrate} -c:a aac -b:a {audio_bitrate} "{temp_output_file}"'
    )
    
    print(_("執行軟體編碼轉換命令：{cmd}").format(cmd=cmd_str))
    print(_("使用影片位元率: {vbitrate}, 音訊位元率: {abitrate}").format(
        vbitrate=video_bitrate, 
        abitrate=audio_bitrate
    ))
    
    try:
        # 執行ffmpeg轉換
        process = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        
        # 顯示進度
        for line in process.stdout:
            if "frame=" in line or "time=" in line:
                print(f"\r{line.strip()}", end='')
            
        process.wait()
        
        if process.returncode == 0:
            print(_("\n轉換完成！"))
            
            # 顯示檔案大小比較
            original_size = os.path.getsize(input_file)
            converted_size = os.path.getsize(temp_output_file)
            compression_ratio = (1 - converted_size / original_size) * 100
            
            print(_("檔案大小比較:"))
            print(_("  原始檔案: {size:.2f} MB").format(size=original_size / (1024*1024)))
            print(_("  轉換後檔案: {size:.2f} MB").format(size=converted_size / (1024*1024)))
            print(_("  節省空間: {ratio:.2f}%").format(ratio=compression_ratio))
            
            # 重命名輸出檔案
            try:
                # 如果最終輸出檔案已存在，先刪除
                if os.path.exists(final_output_file):
                    os.remove(final_output_file)
                
                shutil.move(temp_output_file, final_output_file)
                print(_("已將輸出檔案重命名為: {file}").format(file=os.path.basename(final_output_file)))
            except Exception as e:
                print(_("無法重命名輸出檔案: {error}").format(error=e))
                # 如果重命名失敗，使用原臨時名稱
                final_output_file = temp_output_file
            
            return final_output_file
        else:
            print(_("轉換失敗，回傳代碼: {code}").format(code=process.returncode))
            return None
    except Exception as e:
        print(_("轉換過程中發生錯誤：{error}").format(error=e))
        return None


def convert_to_hevc_fallback(input_file, video_format, audio_format, video_bitrate, audio_bitrate, fps, original_name_without_ext=None, base_dir=None):
    """使用軟體編碼的備用轉換方法"""
    # 如果沒有提供原始檔名相關資訊，則從input_file提取
    if original_name_without_ext is None:
        original_basename = os.path.basename(input_file)
        original_name_without_ext = os.path.splitext(original_basename)[0]
    
    if base_dir is None:
        base_dir = os.path.dirname(input_file)
    
    # 確定輸出檔案名稱
    temp_output_file = os.path.join(base_dir, "converted_HEVC_SW.mp4")
    final_output_file = os.path.join(base_dir, f"{original_name_without_ext}_HEVC_SW.mp4")
    
    # 使用字串命令
    cmd_str = f'ffmpeg -i "{input_file}" '
    
    # 如果有FPS資訊，加入命令
    if fps:
        cmd_str += f'-r {fps} '
    
    # 添加影片和聲音編碼設定
    cmd_str += (
        f'-c:v libx265 -crf 22 -preset medium -tag:v hvc1 ' +
        f'-b:v {video_bitrate} -c:a aac -b:a {audio_bitrate} "{temp_output_file}"'
    )
    
    print(_("執行軟體編碼轉換命令：{cmd}").format(cmd=cmd_str))
    print(_("使用影片位元率: {vbitrate}, 音訊位元率: {abitrate}").format(
        vbitrate=video_bitrate, 
        abitrate=audio_bitrate
    ))
    
    try:
        # 執行ffmpeg轉換
        process = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        
        # 顯示進度
        for line in process.stdout:
            if "frame=" in line or "time=" in line:
                print(f"\r{line.strip()}", end='')
            
        process.wait()
        
        if process.returncode == 0:
            print(_("\n轉換完成！"))
            
            # 顯示檔案大小比較
            original_size = os.path.getsize(input_file)
            converted_size = os.path.getsize(temp_output_file)
            compression_ratio = (1 - converted_size / original_size) * 100
            
            print(_("檔案大小比較:"))
            print(_("  原始檔案: {size:.2f} MB").format(size=original_size / (1024*1024)))
            print(_("  轉換後檔案: {size:.2f} MB").format(size=converted_size / (1024*1024)))
            print(_("  節省空間: {ratio:.2f}%").format(ratio=compression_ratio))
            
            # 重命名輸出檔案
            try:
                # 如果最終輸出檔案已存在，先刪除
                if os.path.exists(final_output_file):
                    os.remove(final_output_file)
                
                shutil.move(temp_output_file, final_output_file)
                print(_("已將輸出檔案重命名為: {file}").format(file=os.path.basename(final_output_file)))
            except Exception as e:
                print(_("無法重命名輸出檔案: {error}").format(error=e))
                # 如果重命名失敗，使用原臨時名稱
                final_output_file = temp_output_file
            
            return final_output_file
        else:
            print(_("轉換失敗，回傳代碼: {code}").format(code=process.returncode))
            return None
    except Exception as e:
        print(_("轉換過程中發生錯誤：{error}").format(error=e))
        return None

def test_ffmpeg_capabilities():
    """測試 ffmpeg 的編碼器支援情況"""
    print(_("測試 ffmpeg 的編碼器支援情況..."))
    
    try:
        # 取得支援的編碼器列表
        encoders_result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        
        # 檢查各種 HEVC 編碼器是否支援
        encoders = encoders_result.stdout
        
        support_info = {
            "libx265": "libx265" in encoders,
            "hevc_nvenc": "hevc_nvenc" in encoders,
            "hevc_videotoolbox": "hevc_videotoolbox" in encoders,
            "hevc_amf": "hevc_amf" in encoders,
            "hevc_qsv": "hevc_qsv" in encoders,
            "hevc_vaapi": "hevc_vaapi" in encoders
        }
        
        print(_("FFmpeg 編碼器支援情況:"))
        for encoder, supported in support_info.items():
            print(_("  {encoder}: {status}").format(
                encoder=encoder, 
                status=_("支援") if supported else _("不支援")
            ))
        
        # 取得支援的硬體加速方法
        hwaccel_result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True)
        
        print(_("FFmpeg 硬體加速支援情況:"))
        for line in hwaccel_result.stdout.splitlines()[1:]:  # 跳過第一行標題
            if line.strip():
                print(f"  {line.strip()}")
        
        return support_info
    except Exception as e:
        print(_("測試 ffmpeg 能力時發生錯誤: {error}").format(error=e))
        return {}

def main():
    # 檢查必要的程式是否安裝
    try:
        # 檢查 yt-dlp
        version_result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
        print(_("偵測到 yt-dlp 版本: {version}").format(version=version_result.stdout.strip()))
        
        # 檢查 ffmpeg
        ffmpeg_result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        print(_("偵測到 ffmpeg 已安裝"))
        
        # 測試 ffmpeg 能力
        ffmpeg_capabilities = test_ffmpeg_capabilities()
        
    except FileNotFoundError as e:
        if "yt-dlp" in str(e):
            print(_("錯誤：未找到 yt-dlp。請先安裝 yt-dlp。"))
            print(_("可以使用以下命令安裝："))
            print("  pip install yt-dlp")
            sys.exit(1)
        elif "ffmpeg" in str(e):
            print(_("錯誤：未找到 ffmpeg。請先安裝 ffmpeg。"))
            print(_("可以參考 https://ffmpeg.org/download.html 安裝指南"))
            sys.exit(1)
    
    # 獲取影片URL
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input(_("請輸入YouTube影片URL: ")).strip()
    
    if not url:
        print(_("錯誤：URL不能為空"))
        sys.exit(1)
        
    # 檢查URL格式
    if not re.search(r'youtube\.com/watch\?v=|youtu\.be/', url):
        print(_("警告：URL格式可能不正確，請確認是否為有效的YouTube影片URL"))
        continue_anyway = input(_("是否繼續？(y/n): ")).strip().lower()
        if continue_anyway != 'y':
            sys.exit(1)
    
    # 獲取輸出目錄
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    else:
        default_dir = os.path.expanduser("~/Downloads")
        output_dir = input(_("請輸入儲存目錄（預設為{dir}）: ").format(dir=default_dir)).strip()
        if not output_dir:
            output_dir = default_dir
            
    # 檢查目錄是否存在且有寫入權限
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(_("已建立目錄: {dir}").format(dir=output_dir))
        except Exception as e:
            print(_("無法建立目錄 {dir}: {error}").format(dir=output_dir, error=e))
            output_dir = "."
            print(_("將使用目前目錄作為輸出目錄"))
    elif not os.access(output_dir, os.W_OK):
        print(_("警告: 沒有寫入權限到 {dir}").format(dir=output_dir))
        output_dir = "."
        print(_("將使用目前目錄作為輸出目錄"))
    
    print(_("處理URL: {url}").format(url=url))
    
    # 獲取影片資訊
    video_info = get_video_info(url)
    
    # 篩選格式
    video_formats, audio_formats = filter_formats(video_info.get('formats', []))
    
    # 找出最佳格式
    best_video, best_audio = get_best_formats(video_formats, audio_formats)
    
    # 顯示格式資訊
    print_format_info(best_video, _("影片"))
    print_format_info(best_audio, _("聲音"))
    
    # 使用者確認
    confirm = input(_("是否下載以上最佳格式？(y/n): ")).strip().lower()
    if confirm != 'y' and confirm != '':
        print(_("已取消下載"))
        sys.exit(0)
    
    # 下載影片
    output_file = download_video(url, best_video, best_audio, output_dir)
    confirm = input(_("是否進行壓縮？(y/n): ")).strip().lower()
    if confirm != 'y' and confirm != '':
        print(_("不進行壓縮"))
        sys.exit(0)

    if output_file:
        hevc_file = convert_to_hevc(output_file, best_video, best_audio)
        if hevc_file:
            print(_("轉換成功，檔案位置：{file}").format(file=hevc_file))

if __name__ == "__main__":
    main()