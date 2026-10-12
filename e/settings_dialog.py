
import copy

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QLabel, QCheckBox, QPushButton, QGridLayout, QVBoxLayout,
    QHBoxLayout, QFrame, QColorDialog, QToolButton, QScrollArea,
    QWidget, QSlider, QMessageBox, QInputDialog,
)
from PyQt5.QtGui import QColor

from config import (
    DEFAULT_SETTINGS, PALETTE_LABELS, ANIM_LABELS, save_settings,
    DEFAULT_PALETTE, DEFAULT_ANIM, DEFAULT_FEATURES, FEATURE_LABELS,
    HELP_TEXT,
)


class ColorSwatch(QPushButton):
    def __init__(self, hex_color, on_changed=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(74, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('点击选择颜色')
        self._hex = '#000000'
        self._on_changed = on_changed
        self.set_color(hex_color)
        self.clicked.connect(self._pick)

    def set_color(self, hex_color):
        self._hex = hex_color
        self.setStyleSheet(
            'QPushButton {{ background-color: {}; border: 1px solid #4A4A4A; '
            'border-radius: 2px; }}'.format(hex_color)
        )

    def color(self):
        return self._hex

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._hex), self, '选择颜色')
        if c.isValid():
            self.set_color(c.name())
            if self._on_changed is not None:
                self._on_changed(c.name())


class CollapsibleSection(QFrame):
    def __init__(self, title, collapsed=False, parent=None):
        super().__init__(parent)
        self.setObjectName('panel')
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.toggle = QToolButton()
        self.toggle.setObjectName('collapseHeader')
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setChecked(not collapsed)
        root.addWidget(self.toggle)

        self.body = QWidget()
        root.addWidget(self.body)

        self.toggle.toggled.connect(self._on_toggled)
        self._on_toggled(self.toggle.isChecked())

    def _on_toggled(self, checked):
        self.body.setVisible(bool(checked))
        self.toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def set_body_layout(self, layout):
        self.body.setLayout(layout)


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle('设置 / SETTINGS')
        self.resize(480, 640)
        self.cfg = {
            'animations_enabled': bool(cfg['animations_enabled']),
            'anim': dict(cfg['anim']),
            'palette': dict(cfg['palette']),
            'features': dict(cfg.get('features', {})),
            'dedup_enabled': bool(cfg.get('dedup_enabled', True)),
            'dedup_similarity': int(cfg.get('dedup_similarity', 100)),
            'similarity_threshold': int(cfg.get('similarity_threshold', 90)),
            'recent_searches': list(cfg.get('recent_searches', [])),
            'collapsed_groups': list(cfg.get('collapsed_groups', [])),
        }
        self.feature_checks = {}
        self.swatches = {}
        self.checks = {}
        self._build()

    def _group(self):
        g = QFrame()
        g.setObjectName('panel')
        return g

    def _section_label(self, text):
        label = QLabel(text)
        label.setObjectName('sectionTitle')
        return label

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel('设置 / SETTINGS')
        title.setObjectName('header')
        head.addWidget(title)
        head.addStretch()
        help_btn = QPushButton('帮助')
        help_btn.clicked.connect(self._show_help)
        head.addWidget(help_btn)
        root.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(0, 0, 6, 0)
        content.setSpacing(10)

        #---- 动画 ----
        anim_frame = self._group()
        al = QVBoxLayout(anim_frame)
        al.setContentsMargins(12, 10, 12, 10)
        al.setSpacing(6)
        al.addWidget(self._section_label('动画 / ANIMATIONS'))

        master = QCheckBox('启用动画（总开关）')
        master.setChecked(self.cfg['animations_enabled'])
        master.toggled.connect(self._on_master)
        al.addWidget(master)
        self.master_check = master

        for key, text in ANIM_LABELS.items():
            cb = QCheckBox(text)
            cb.setChecked(bool(self.cfg['anim'].get(key)))
            cb.toggled.connect(lambda checked, k=key: self.cfg['anim'].__setitem__(k, bool(checked)))
            al.addWidget(cb)
            self.checks[key] = cb
        content.addWidget(anim_frame)

        color_frame = CollapsibleSection('配色 / PALETTE ', collapsed=True)
        cl = QVBoxLayout()
        cl.setContentsMargins(12, 4, 12, 10)
        cl.setSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        row = 0
        for key, text in PALETTE_LABELS.items():
            grid.addWidget(QLabel(text), row, 0)
            swatch = ColorSwatch(self.cfg['palette'].get(key, '#000000'),
                                 on_changed=lambda hexv, k=key: self.cfg['palette'].__setitem__(k, hexv))
            grid.addWidget(swatch, row, 1)
            hex_label = QLabel(self.cfg['palette'].get(key, '').upper())
            hex_label.setObjectName('hint')
            grid.addWidget(hex_label, row, 2)
            self.swatches[key] = (swatch, hex_label)
            row += 1
        cl.addLayout(grid)
        color_frame.set_body_layout(cl)
        content.addWidget(color_frame)

        #---- 查重 ----
        dedup_frame = self._group()
        dl = QVBoxLayout(dedup_frame)
        dl.setContentsMargins(12, 10, 12, 10)
        dl.setSpacing(6)
        dl.addWidget(self._section_label('查重 / DEDUP'))

        self.dedup_check = QCheckBox('开启哈希值查重(跳过重复)')
        self.dedup_check.setChecked(self.cfg['dedup_enabled'])
        self.dedup_check.toggled.connect(self._on_dedup_toggled)
        dl.addWidget(self.dedup_check)

        sim_row = QHBoxLayout()
        sim_row.addWidget(QLabel('相似度：'))
        self.similarity_slider = QSlider(Qt.Horizontal)
        self.similarity_slider.setRange(0, 100)
        self.similarity_slider.setValue(self.cfg['dedup_similarity'])
        self.similarity_slider.valueChanged.connect(self._on_similarity)
        sim_row.addWidget(self.similarity_slider, 1)
        self.similarity_label = QLabel('{}%'.format(self.cfg['dedup_similarity']))
        self.similarity_label.setMinimumWidth(44)
        self.similarity_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sim_row.addWidget(self.similarity_label)
        dl.addLayout(sim_row)
        hint = QLabel('tips:开了这个会加载入时间(╯‵□′)╯︵┻━┻')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        dl.addWidget(hint)
        content.addWidget(dedup_frame)

        #---- 实验功能 ----
        feat_frame = self._group()
        fl = QVBoxLayout(feat_frame)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(6)
        fl.addWidget(self._section_label('功能 / FEATURES [实验性]'))
        for key, text in FEATURE_LABELS.items():
            cb = QCheckBox(text)
            cb.setChecked(bool(self.cfg['features'].get(key)))
            cb.toggled.connect(lambda checked, k=key: self.cfg['features'].__setitem__(k, bool(checked)))
            fl.addWidget(cb)
            self.feature_checks[key] = cb
            if key == 'similar_search':
                cb.toggled.connect(self._on_simsearch_toggled)

        #相似度查找阈值（仅开启「相似度查找」时显示）
        self.simsearch_row = QWidget()
        ss = QVBoxLayout(self.simsearch_row)
        ss.setContentsMargins(0, 0, 0, 0)
        ss.setSpacing(4)
        ss_line = QHBoxLayout()
        ss_line.addWidget(QLabel('相似率：'))
        self.simsearch_slider = QSlider(Qt.Horizontal)
        self.simsearch_slider.setRange(0, 100)
        self.simsearch_slider.setValue(int(self.cfg.get('similarity_threshold', 90)))
        self.simsearch_slider.valueChanged.connect(self._on_simsearch_threshold)
        ss_line.addWidget(self.simsearch_slider, 1)
        self.simsearch_label = QLabel('{}%'.format(int(self.cfg.get('similarity_threshold', 90))))
        self.simsearch_label.setMinimumWidth(44)
        self.simsearch_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ss_line.addWidget(self.simsearch_label)
        ss.addLayout(ss_line)
        ss_hint = QLabel('相似度查找的相似率调整')
        ss_hint.setObjectName('hint')
        ss_hint.setWordWrap(True)
        ss.addWidget(ss_hint)
        fl.addWidget(self.simsearch_row)
        content.addWidget(feat_frame)
        self._sync_simsearch_visibility()

        #---- 维护 ----
        maint_frame = self._group()
        ml = QVBoxLayout(maint_frame)
        ml.setContentsMargins(12, 10, 12, 10)
        ml.setSpacing(6)
        ml.addWidget(self._section_label('维护 / MAINTENANCE'))
        clear_btn = QPushButton('一键清除缩略图缓存')
        clear_btn.clicked.connect(self._clear_cache)
        ml.addWidget(clear_btn)
        content.addWidget(maint_frame)

        #---- 标签管理 ----
        tag_frame = self._group()
        tl = QVBoxLayout(tag_frame)
        tl.setContentsMargins(12, 10, 12, 10)
        tl.setSpacing(6)
        tl.addWidget(self._section_label('标签管理 / TAGS'))
        del_tag_btn = QPushButton('删除tag')
        del_tag_btn.clicked.connect(self._delete_tag)
        tl.addWidget(del_tag_btn)
        del_type_btn = QPushButton('删除tag 类型')
        del_type_btn.clicked.connect(self._delete_tag_type)
        tl.addWidget(del_type_btn)
        tag_hint = QLabel('Tips：将从所有表情中自动删除所选tag & 该类型下所有tag ( ^ ∇ ^ )')
        tag_hint.setObjectName('hint')
        tag_hint.setWordWrap(True)
        tl.addWidget(tag_hint)
        content.addWidget(tag_frame)

        content.addStretch(1)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        #---- 操作按钮 ----
        btn_row = QHBoxLayout()
        reset = QPushButton('恢复默认')
        reset.clicked.connect(self._reset)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        apply_btn = QPushButton('应用')
        apply_btn.clicked.connect(self._apply)
        save_btn = QPushButton('保存并关闭')
        save_btn.setObjectName('primary')
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(reset)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        self._sync_similarity()

    def _on_master(self, checked):
        self.cfg['animations_enabled'] = bool(checked)

    def _on_dedup_toggled(self, checked):
        self.cfg['dedup_enabled'] = bool(checked)

    def _on_similarity(self, value):
        self.cfg['dedup_similarity'] = int(value)
        self._sync_similarity()

    def _sync_similarity(self):
        v = int(self.cfg.get('dedup_similarity', 100))
        self.similarity_label.setText('{}%'.format(v))

    def _on_simsearch_toggled(self, checked):
        self._sync_simsearch_visibility()

    def _on_simsearch_threshold(self, value):
        self.cfg['similarity_threshold'] = int(value)
        self.simsearch_label.setText('{}%'.format(int(value)))

    def _sync_simsearch_visibility(self):
        on = bool(self.cfg.get('features', {}).get('similar_search'))
        if hasattr(self, 'simsearch_row'):
            self.simsearch_row.setVisible(on)
            v = int(self.cfg.get('similarity_threshold', 90))
            self.simsearch_label.setText('{}%'.format(v))

    def _show_help(self):
        QMessageBox.information(self, '帮助', HELP_TEXT)

    def _clear_cache(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, 'clear_thumbnail_cache'):
            parent.clear_thumbnail_cache(self)
        else:
            QMessageBox.information(self, '提示', '无法访问主窗口，请关闭设置后在主界面操作。')

    def _delete_tag(self):
        parent = self.parent()
        if parent is None or not hasattr(parent, 'all_tags') or not hasattr(parent, 'remove_tag_everywhere'):
            QMessageBox.information(self, '提示', '无法访问主窗口数据，请关闭设置后在主界面操作。')
            return
        tags = parent.all_tags()
        if not tags:
            QMessageBox.information(self, '提示', '没有任何 tag')
            return
        choice, ok = QInputDialog.getItem(self, '永久删除 tag',
                                          '选择要删除的 tag（将从所有表情中删除）：',
                                          tags, 0, False)
        if not ok:
            return
        parent.remove_tag_everywhere(choice, dialog=self)

    def _delete_tag_type(self):
        parent = self.parent()
        if parent is None or not hasattr(parent, 'all_tag_types') or not hasattr(parent, 'remove_tag_type_everywhere'):
            QMessageBox.information(self, '提示', '无法访问主窗口数据，请关闭设置后在主界面操作。')
            return
        types = parent.all_tag_types()
        if not types:
            QMessageBox.information(self, '提示', '没有任何 tag 类型')
            return
        choice, ok = QInputDialog.getItem(self, '永久删除 tag 类型',
                                          '选择要删除的 tag 类型（将删除所有表情中该类型的所有tag）：',
                                          types, 0, False)
        if not ok:
            return
        parent.remove_tag_type_everywhere(choice, dialog=self)

    def _sync_ui(self):
        self.master_check.setChecked(self.cfg['animations_enabled'])
        for key, cb in self.checks.items():
            cb.setChecked(bool(self.cfg['anim'].get(key)))
        for key, (swatch, hex_label) in self.swatches.items():
            v = self.cfg['palette'].get(key, '#000000')
            swatch.set_color(v)
            hex_label.setText(v.upper())
        for key, cb in self.feature_checks.items():
            cb.setChecked(bool(self.cfg['features'].get(key)))
        self.dedup_check.setChecked(bool(self.cfg.get('dedup_enabled', True)))
        self.similarity_slider.setValue(int(self.cfg.get('dedup_similarity', 100)))
        self._sync_similarity()
        self.simsearch_slider.setValue(int(self.cfg.get('similarity_threshold', 90)))
        self._sync_simsearch_visibility()

    def _apply(self):
        if self.parent() is not None and hasattr(self.parent(), 'apply_settings'):
            self.parent().apply_settings(self.cfg)

    def _save(self):
        self._apply()
        save_settings(self.cfg)
        self.accept()

    def _reset(self):
        self.cfg = copy.deepcopy(DEFAULT_SETTINGS)
        self._sync_ui()
        self._apply()
