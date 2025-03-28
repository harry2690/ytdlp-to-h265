import os
import json
import locale
import sys

class I18n:
    """國際化支援類別"""
    
    def __init__(self, lang=None):
        """
        初始化國際化支援
        
        Args:
            lang (str, optional): 指定語言代碼，如不指定則自動偵測系統語言
        """
        # 儲存所有翻譯
        self.translations = {}
        
        # 設定語言
        if lang:
            self.current_lang = lang
        else:
            self.current_lang = self._detect_system_language()
        
        # 載入翻譯
        self._load_translations()
    
    def _detect_system_language(self):
        """偵測系統語言並返回語言代碼"""
        try:
            # 取得系統預設語言設定
            system_locale, encoding = locale.getdefaultlocale()
            
            if system_locale:
                # 取得語言代碼部分 (例如 zh_TW -> zh)
                lang_code = system_locale.split('_')[0]
                
                # 處理特殊情況：繁體中文
                if system_locale.lower() in ['zh_tw', 'zh_hk']:
                    return 'zh_TW'  # 繁體中文
                elif system_locale.lower() == 'zh_cn':
                    return 'zh_CN'  # 簡體中文
                
                return lang_code
            
            # 如果無法取得，預設使用英文
            return 'en'
        except:
            # 發生錯誤時使用英文
            return 'en'
    
    def _load_translations(self):
        """載入翻譯檔案"""
        try:
            # 尋找翻譯檔案目錄
            script_dir = os.path.dirname(os.path.abspath(__file__))
            lang_dir = os.path.join(script_dir, 'langs')
            
            # 如果目錄不存在，建立它
            if not os.path.exists(lang_dir):
                os.makedirs(lang_dir)
            
            # 嘗試載入特定語言的翻譯
            lang_file = os.path.join(lang_dir, f'{self.current_lang}.json')
            
            # 檢查檔案是否存在
            if os.path.exists(lang_file):
                with open(lang_file, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
            else:
                # 如果找不到目前語言的翻譯檔，嘗試找回退語言
                if '_' in self.current_lang:
                    # 例如：zh_TW -> zh
                    fallback_lang = self.current_lang.split('_')[0]
                    fallback_file = os.path.join(lang_dir, f'{fallback_lang}.json')
                    
                    if os.path.exists(fallback_file):
                        with open(fallback_file, 'r', encoding='utf-8') as f:
                            self.translations = json.load(f)
                    else:
                        # 如果回退語言也沒找到，再嘗試英文
                        en_file = os.path.join(lang_dir, 'en.json')
                        if os.path.exists(en_file):
                            with open(en_file, 'r', encoding='utf-8') as f:
                                self.translations = json.load(f)
                else:
                    # 直接嘗試英文
                    en_file = os.path.join(lang_dir, 'en.json')
                    if os.path.exists(en_file):
                        with open(en_file, 'r', encoding='utf-8') as f:
                            self.translations = json.load(f)
        except Exception as e:
            # 清空翻譯以防止錯誤
            self.translations = {}
    
    def get(self, key, **kwargs):
        """
        取得翻譯文字，如果找不到就返回原始文字
        
        Args:
            key (str): 翻譯的鍵值
            **kwargs: 用於格式化翻譯文字的參數
            
        Returns:
            str: 翻譯後的文字
        """
        if key in self.translations:
            # 找到翻譯，套用格式化參數
            try:
                return self.translations[key].format(**kwargs)
            except KeyError as e:
                # 格式化參數錯誤
                return self.translations[key]
            except Exception as e:
                # 其他錯誤
                return self.translations[key]
        else:
            # 找不到翻譯，返回原始文字
            return key

# 全域的i18n物件
_i18n = None

def init_i18n(lang=None):
    """初始化國際化支援"""
    global _i18n
    _i18n = I18n(lang)
    return _i18n

def _(key, **kwargs):
    """翻譯函數，可作為全域函數使用"""
    global _i18n
    if _i18n is None:
        _i18n = I18n()
    return _i18n.get(key, **kwargs)

# 用法示例：
# init_i18n()  # 初始化，自動偵測系統語言
# print(_("正在獲取影片資訊，請稍候..."))  # 獲取翻譯
