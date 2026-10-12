import os,json,sys

def _runtime_root():
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass and os.path.isdir(meipass):
            return meipass
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _settings_path_for_runtime():
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
        settings_dir = os.path.join(appdata, 'EmojiManager')
        os.makedirs(settings_dir, exist_ok=True)
        return os.path.join(settings_dir, 'settings.json')
    return os.path.join(_runtime_root(), 'settings.json')


ROOT_DIR = _runtime_root()
SETTINGS_PATH = _settings_path_for_runtime()

#灰阶从深到浅排列，所有颜色的 RGB 值相同。
DEFAULT_PALETTE = {
    'black':        '#000000',
    'bg':           '#0E0E0E',
    'bg_deep':      '#151515',
    'bg_panel':     '#1C1C1C',
    'bg_input':     '#222222',
    'bg_card':      '#292929',
    'border':       '#383838',
    'border_soft':  '#4D4D4D',
    'text_faint':   '#737373',
    'text_dim':     '#9A9A9A',
    'text':         '#BFBFBF',
    'text_hi':      '#DCDCDC',
    'favorite':     '#CECECE',
    'accent':       '#EEEEEE',
    'danger':       '#F5F5F5',
    'white':        '#FFFFFF',
}

#设置界面显示的颜色名称，顺序与灰阶一致。
PALETTE_LABELS = {
    'black':        '纯黑(最深)',
    'bg':           '主背景',
    'bg_deep':      '深层/分隔',
    'bg_panel':     '面板',
    'bg_input':     '输入框',
    'bg_card':      '卡片/按钮',
    'border':       '细边框',
    'border_soft':  '软边框/悬停',
    'text_faint':   '弱化文字',
    'text_dim':     '次要文字',
    'text':         '主文字',
    'text_hi':      '强调文字',
    'favorite':     '收藏星标',
    'accent':       '主强调(近白)',
    'danger':       '删除',
    'white':        '纯白/高光',
}

#默认动画开关
DEFAULT_ANIM = {
    'splash':           True,
    'particles':        True,
    'scanline':         True,
    'selection_pulse':  True,
    'panel_entrance':   True,
}

ANIM_LABELS = {
    'splash':          '启动动画 (Splash)',
    'particles':       '粒子背景',
    'scanline':        '扫描线效果',
    'selection_pulse': '选中卡片呼吸发光',
    'panel_entrance':  '面板入场淡入',
}

DEFAULT_FEATURES = {
    'nested_groups': False,
    'preload': False,
    'encrypted_export': False,
    'similar_search': False,
    'collapse_persist': False,
}

FEATURE_LABELS = {
    'nested_groups': '父集嵌套',
    'preload': '缩略图预加载缓存',
    'encrypted_export': '开启加密混淆导出/导入',
    'similar_search': '相似度查找',
    'collapse_persist': '保存折叠的子父集状态',
}

DEFAULT_SETTINGS = {
    'animations_enabled': True,
    'anim': dict(DEFAULT_ANIM),
    'palette': dict(DEFAULT_PALETTE),
    'features': dict(DEFAULT_FEATURES),
    'dedup_enabled': True,
    'dedup_similarity': 100,
    'similarity_threshold': 90,
    'recent_searches': [],
    'collapsed_groups': [],
}


def load_settings():
    #读取 settings.json，缺失时回退默认；只合并已知键。
    cfg = {
        'animations_enabled': True,
        'anim': dict(DEFAULT_ANIM),
        'palette': dict(DEFAULT_PALETTE),
        'features': dict(DEFAULT_FEATURES),
        'dedup_enabled': True,
        'dedup_similarity': 100,
        'similarity_threshold': 90,
        'recent_searches': [],
        'collapsed_groups': [],
    }
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            _deep_update(cfg, data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def save_settings(cfg):
    tmp = SETTINGS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_PATH)


#应用帮助文本：主窗口与设置界面共用，保证「帮助」在任意入口都能正确加载。
HELP_TEXT = (
    '操作说明\n\n'
    '快捷键：\n'
    '  F1 - 显示帮助\n'
    '  Delete - 删除选中\n'
    '  双击图片 - 预览\n'
    '  右键图片/父集 - 更多操作\n'
    '  by HoWingCraft'
    ' 有BUG联系QQ551794735（￣︶￣）↗　'
)


def anim_enabled(cfg, key):
    return bool(cfg.get('animations_enabled')) and bool(cfg.get('anim', {}).get(key))


def _deep_update(target, source):
    for k, v in source.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_update(target[k], v)
        elif k in target and type(v) is type(target[k]):
            target[k] = v
    return target