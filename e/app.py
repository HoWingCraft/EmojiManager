
import os,sys,json,time,shutil,hashlib,zipfile
import random

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLineEdit, QComboBox, QSpinBox, QCheckBox,
    QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QInputDialog, QMenu, QDialog, QListWidget,
    QListWidgetItem, QListView, QStackedWidget, QTableWidget, QHeaderView,
    QProgressDialog, QAbstractItemView, QStyledItemDelegate, QStyle,
    QTableWidgetItem, QToolButton, QGraphicsOpacityEffect,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QRectF, QPointF, QPoint, QRect
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QBrush, QPixmap, QPixmapCache, QImage, QImageReader,
    QMovie, QFont, QStandardItemModel, QStandardItem, QCursor, qGray,
)

from config import anim_enabled, HELP_TEXT, save_settings
from theme import apply_theme
from animations import AmbientBackground, fade_in, PulseRepainter, pulse_alpha
from settings_dialog import SettingsDialog
import crypto

#路径和常量

def _runtime_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ROOT_DIR = _runtime_root()
DATA_DIR = os.path.join(ROOT_DIR, 'EmojiData')
EMOJI_DIR = os.path.join(DATA_DIR, 'emojis')
GROUP_DIR = os.path.join(DATA_DIR, 'groups')
THUMB_DIR = os.path.join(DATA_DIR, 'cache', 'thumbnails')
EMOJIS_JSON = os.path.join(DATA_DIR, 'emojis.json')
GROUPS_JSON = os.path.join(DATA_DIR, 'groups.json')

UNC_ID = 'uncategorized'
UNC_NAME = '未分类'
ALL_MARK = '@@all@@'

IMG_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
IMG_FILTER = '图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)'
IMPORT_FILTER = '图片 / 加密图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.prtsenc)'

THUMB_SIZE = 140
CELL_W = 156
CELL_H = 184

GROUP_COLORS = ['#EEEEEE', '#DCDCDC', '#BFBFBF', '#9A9A9A', '#737373', '#4D4D4D']

#父集压缩包使用的格式标识
PACK_SCHEMA = 'prts.emoji.group/v1'


def ensure_dirs():
    for d in (EMOJI_DIR, GROUP_DIR):
        os.makedirs(d, exist_ok=True)


def abs_emoji(rel):
    return os.path.join(EMOJI_DIR, rel) if rel else None


def _unique_stored_name(ext):
    while True:
        name = '{}_{}{}'.format(int(time.time()), random.randint(1000, 9999), ext)
        if not os.path.exists(os.path.join(EMOJI_DIR, name)):
            return name


def _safe_filename(name, fallback='未命名'):
    bad = '<>:"/\\|?*'
    cleaned = ''.join('_' if c in bad else c for c in str(name))
    cleaned = cleaned.strip().strip('. ')
    return cleaned or fallback


def rel_root(abs_path):
    return os.path.relpath(abs_path, ROOT_DIR)


def abs_cached(rel):
    return os.path.join(ROOT_DIR, rel) if rel else None


def thumb_path_for(src_abs, mtime, size):
    key = '{}|{}|{}'.format(os.path.abspath(src_abs), mtime, size)
    return os.path.join(THUMB_DIR, hashlib.md5(key.encode('utf-8')).hexdigest() + '.png')


def _sha1(path):
    h = hashlib.sha1()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def is_animated_gif(path):
    try:
        r = QImageReader(path)
        fmt = bytes(r.format()).lower()
        return fmt == b'gif' and r.imageCount() > 1
    except Exception:
        return path.lower().endswith('.gif')


def _fit(w, h, max_w, max_h):
    if w <= 0 or h <= 0:
        return max_w, max_h
    r = min(max_w / float(w), max_h / float(h), 1.0)
    return w * r, h * r


def _dhash(path):
    #使用 9x8 灰度图的相邻像素亮度差生成 64 位 dHash。
    try:
        r = QImageReader(path)
        r.setAutoTransform(True)
        img = r.read()
        if img.isNull():
            return None
        img = img.scaled(9, 8, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        bits = 0
        for y in range(8):
            for x in range(8):
                a = qGray(img.pixel(x, y))
                b = qGray(img.pixel(x + 1, y))
                bits = (bits << 1) | (1 if a < b else 0)
        return bits
    except Exception:
        return None


def _similarity_pct(a, b):
    if a is None or b is None:
        return 0
    dist = (a ^ b).bit_count()
    return round((1.0 - dist / 64.0) * 100)


def _tag_type(tag):
    if isinstance(tag, str) and ':' in tag:
        t = tag.split(':', 1)[0].strip()
        if t:
            return t
    return '未分类'


def _tag_value(tag):
    if isinstance(tag, str) and ':' in tag:
        return tag.split(':', 1)[1].strip() or tag
    return tag


#JSON 读写和备份

def safe_write_json(path, data):
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + '.bak')
        except OSError:
            pass
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        try:
            if os.path.exists(path):
                shutil.copy2(path, path + '.corrupt.bak')
        except OSError:
            pass
        return default


def load_data_from_disk():
    ensure_dirs()
    item_dicts = _read_json(EMOJIS_JSON, [])
    group_dicts = _read_json(GROUPS_JSON, [])

    if not isinstance(item_dicts, list):
        item_dicts = []
    if not isinstance(group_dicts, list):
        group_dicts = []

    group_changed = False
    unc = next((g for g in group_dicts if g.get('group_id') == UNC_ID), None)
    if unc is None:
        unc = {
            'group_id': UNC_ID, 'name': UNC_NAME, 'cover_path': None,
            'timestamp': time.time(), 'color': '#9A9A9A',
            'is_favorite': False, 'is_system': True,
        }
        group_dicts.insert(0, unc)
        group_changed = True
    else:
        if unc.get('is_system') is not True or not unc.get('name'):
            group_changed = True
        unc['is_system'] = True
        unc['name'] = unc.get('name') or UNC_NAME

    valid_ids = {g.get('group_id') for g in group_dicts}
    changed = False
    for d in item_dicts:
        gid = d.get('group_id')
        if not gid or gid not in valid_ids:
            d['group_id'] = UNC_ID
            changed = True

    if changed:
        safe_write_json(EMOJIS_JSON, item_dicts)
    if group_changed:
        safe_write_json(GROUPS_JSON, group_dicts)
    return item_dicts, group_dicts


#图片和父集的数据模型

class EmojiItem:
    def __init__(self, path, name, group_id=None, tags=None, timestamp=None,
                 thumbnail=None, is_favorite=False):
        self.path = path
        self.name = name if name else '未命名'
        self.group_id = group_id or UNC_ID
        self.tags = list(tags) if tags else []
        self.timestamp = timestamp or time.time()
        self.thumbnail = thumbnail
        self.is_favorite = bool(is_favorite)

        self.thumb_abs = None
        self.exists = True

    def to_dict(self):
        return {
            'path': self.path, 'name': self.name, 'group_id': self.group_id,
            'tags': self.tags, 'timestamp': self.timestamp,
            'thumbnail': self.thumbnail, 'is_favorite': self.is_favorite,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            d.get('path'), d.get('name'),
            d.get('group_id') or UNC_ID,
            d.get('tags'), d.get('timestamp'),
            d.get('thumbnail'), d.get('is_favorite', False),
        )


class EmojiGroup:
    def __init__(self, group_id, name, cover_path=None, timestamp=None, color=None,
                 is_favorite=False, is_system=False, priority=None, parent_id=None,
                 tag_types=None):
        self.group_id = group_id
        self.name = name
        self.cover_path = cover_path
        self.timestamp = timestamp or time.time()
        self.color = color or GROUP_COLORS[0]
        self.is_favorite = bool(is_favorite)
        self.is_system = bool(is_system)
        self.priority = priority if priority is not None else 0
        self.parent_id = parent_id or None
        self.tag_types = list(tag_types) if tag_types else []

    def to_dict(self):
        return {
            'group_id': self.group_id, 'name': self.name,
            'cover_path': self.cover_path, 'timestamp': self.timestamp,
            'color': self.color, 'is_favorite': self.is_favorite,
            'is_system': self.is_system,
            'priority': self.priority, 'parent_id': self.parent_id,
            'tag_types': self.tag_types,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            d.get('group_id'), d.get('name') or '未命名',
            d.get('cover_path'), d.get('timestamp'), d.get('color'),
            d.get('is_favorite', False), d.get('is_system', False),
            d.get('priority'), d.get('parent_id'),
            d.get('tag_types'),
        )


#后台任务

class DataLoaderThread(QThread):
    loaded = pyqtSignal(list, list)
    failed = pyqtSignal(str)

    def run(self):
        try:
            items, groups = load_data_from_disk()
            self.loaded.emit(items, groups)
        except Exception as e:
            self.failed.emit(str(e))


def _build_thumbnail(src_abs, out_abs):
    reader = QImageReader(src_abs)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        return False
    img = img.scaled(THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    os.makedirs(THUMB_DIR, exist_ok=True)
    return img.save(out_abs, 'PNG')


class ThumbnailThread(QThread):
    progress = pyqtSignal(int, int)
    ready = pyqtSignal(object, str, bool)   #图片条目、缩略图路径和文件状态
    done = pyqtSignal()

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items

    def run(self):
        total = len(self.items)
        for i, item in enumerate(self.items):
            src = abs_emoji(item.path)
            exists = os.path.isfile(src) if src else False
            thumb_abs = None
            if exists:
                try:
                    st = os.stat(src)
                    thumb_abs = thumb_path_for(src, st.st_mtime, st.st_size)
                    if not os.path.exists(thumb_abs):
                        _build_thumbnail(src, thumb_abs)
                except Exception:
                    thumb_abs = None
            self.ready.emit(item, thumb_abs, exists)
            self.progress.emit(i + 1, total)
        self.done.emit()


class ImportThread(QThread):
    progress = pyqtSignal(int, int, str)
    result = pyqtSignal(list, list)

    def __init__(self, jobs, group_id, existing_items, parent=None,
                 dedup_enabled=True, similarity=100):

        super().__init__(parent)
        self.jobs = jobs
        self.group_id = group_id or UNC_ID
        self.existing_items = existing_items
        self.dedup_enabled = bool(dedup_enabled)
        self.similarity = int(similarity)

    def run(self):
        skipping = []
        sha_seen = set()
        dhashes = []


        total_existing = len(self.existing_items)
        for i, it in enumerate(self.existing_items):
            if self.dedup_enabled:
                p = abs_emoji(it.path)
                if p and os.path.isfile(p):
                    h = _sha1(p)
                    if h:
                        sha_seen.add(h)
                    if 0 < self.similarity < 100:
                        dh = getattr(it, '_dhash', None)
                        if dh is None:
                            dh = _dhash(p)
                            it._dhash = dh
                        if dh is not None:
                            dhashes.append(dh)
            self.progress.emit(i + 1, total_existing, '去重')

        new_items = []
        total = len(self.jobs)
        for i, (src, name) in enumerate(self.jobs):
            raw = None
            ext = None
            h = None
            dh = None

            if crypto.is_encrypted_path(src):
                dec = None
                try:
                    with open(src, 'rb') as f:
                        dec = crypto.decrypt_blob(f.read())
                except OSError:
                    dec = None
                if dec is None:
                    skipping.append('「{}」无法解密,已跳过'.format(name))
                    self.progress.emit(i + 1, total, '导入')
                    continue
                enc_name, ext, raw = dec
                name = enc_name or name
                h = hashlib.sha1(raw).hexdigest()
            else:
                ext = os.path.splitext(src)[1].lower() or '.png'
                h = _sha1(src)
                if self.dedup_enabled and 0 < self.similarity < 100:
                    dh = _dhash(src)

            if self.dedup_enabled:
                if h and h in sha_seen:
                    skipping.append('「{}」重复,已跳过'.format(name))
                    self.progress.emit(i + 1, total, '导入')
                    continue
                if dh is not None:
                    if any(_similarity_pct(dh, e) >= self.similarity for e in dhashes):
                        skipping.append('「{}」重复,已跳过'.format(name))
                        self.progress.emit(i + 1, total, '导入')
                        continue

            if h:
                sha_seen.add(h)
            if dh is not None:
                dhashes.append(dh)

            ext = ext or '.png'
            new_name = _unique_stored_name(ext)
            try:
                if raw is not None:
                    with open(os.path.join(EMOJI_DIR, new_name), 'wb') as f:
                        f.write(raw)
                else:
                    shutil.copy2(src, os.path.join(EMOJI_DIR, new_name))
            except OSError:
                skipping.append('「{}」复制失败'.format(name))
                self.progress.emit(i + 1, total, '导入')
                continue

            new_items.append({
                'path': new_name, 'name': name, 'group_id': self.group_id,
                'tags': [], 'timestamp': time.time(), 'thumbnail': None,
                'is_favorite': False,
            })
            self.progress.emit(i + 1, total, '导入')

        self.result.emit(new_items, skipping)


class ExportThread(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str, int)
    error = pyqtSignal(str)

    def __init__(self, items, dest_dir, parent=None, encrypt=False):
        super().__init__(parent)
        self.items = items
        self.dest_dir = dest_dir
        self.encrypt = bool(encrypt)

    def run(self):
        try:
            os.makedirs(self.dest_dir, exist_ok=True)
            total = len(self.items)
            for i, item in enumerate(self.items):
                src = abs_emoji(item.path)
                if src and os.path.isfile(src):
                    base = os.path.basename(item.path)
                    safe_name = _safe_filename(item.name)
                    if self.encrypt:
                        base_stem = os.path.splitext(base)[0]
                        dest = os.path.join(self.dest_dir, '{}_{}.prtsenc'.format(safe_name, base_stem))
                        k = 1
                        while os.path.exists(dest):
                            dest = os.path.join(self.dest_dir, '{}_{}_{}.prtsenc'.format(safe_name, k, base_stem))
                            k += 1
                        blob = crypto.encrypt_path(src, item.name)
                        with open(dest, 'wb') as f:
                            f.write(blob)
                    else:
                        dest = os.path.join(self.dest_dir, '{}_{}'.format(safe_name, base))
                        k = 1
                        while os.path.exists(dest):
                            dest = os.path.join(self.dest_dir, '{}_{}_{}'.format(safe_name, k, base))
                            k += 1
                        shutil.copy2(src, dest)
                self.progress.emit(i + 1, total)
            self.finished_ok.emit(self.dest_dir, total)
        except Exception as e:
            self.error.emit(str(e))


#网格图片和缩略图

def get_thumb_pixmap(item):
    ta = item.thumb_abs
    if ta and os.path.exists(ta):
        key = 't:' + ta
        pm = QPixmapCache.find(key)
        if pm is not None and not pm.isNull():
            return pm
        pm = QPixmap(ta)
        if not pm.isNull():
            QPixmapCache.insert(key, pm)
            return pm

    src = abs_emoji(item.path)
    item.exists = bool(src and os.path.isfile(src))
    if not item.exists:
        return None
    try:
        st = os.stat(src)
    except OSError:
        return None
    key = 'emoji:{}|{}|{}'.format(os.path.abspath(src), st.st_mtime, st.st_size)
    pm = QPixmapCache.find(key)
    if pm is not None and not pm.isNull():
        return pm
    reader = QImageReader(src)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        return None
    scaled = img.scaled(THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm = QPixmap.fromImage(scaled)
    if pm.isNull():
        return None
    QPixmapCache.insert(key, pm)
    return pm


class EmojiThumbDelegate(QStyledItemDelegate):
    def __init__(self, palette=None, pulse_enabled=True, parent=None):
        super().__init__(parent)
        self.pulse_enabled = bool(pulse_enabled)
        self.name_font = QFont('Microsoft YaHei', 9)
        self.small_font = QFont('Microsoft YaHei', 8)
        self.star_font = None
        self.set_palette(palette or {})

    def set_palette(self, p):
        bg = QColor(p.get('bg', '#0A0C0F'))
        accent = QColor(p.get('accent', '#EEEEEE'))
        self.border = QColor(p.get('border', '#252E37'))
        self.bg = QColor(p.get('bg_card', '#171E24'))
        self.sel_bg = QColor(
            int(bg.red() * 0.78 + accent.red() * 0.22),
            int(bg.green() * 0.78 + accent.green() * 0.22),
            int(bg.blue() * 0.78 + accent.blue() * 0.22),
        )
        self.sel_border = QColor(p.get('accent', '#EEEEEE'))
        self.hover_border = QColor(p.get('text_hi', '#DCDCDC'))
        self.placeholder_bg = QColor(p.get('bg_input', '#0E1317'))
        self.placeholder_fg = QColor(p.get('text_faint', '#56636D'))
        self.name_color = QColor(p.get('text', '#E8EFF3'))
        self.favorite_color = QColor(p.get('favorite', '#F5D97A'))
        self.tag_color = QColor(p.get('text_dim', '#9A9A9A'))

    def set_pulse_enabled(self, on):
        self.pulse_enabled = bool(on)

    def sizeHint(self, option, index):
        return QSize(CELL_W, CELL_H)

    def paint(self, painter, option, index):
        item = index.data(Qt.UserRole)
        if not isinstance(item, EmojiItem):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        rect = option.rect
        card = QRectF(rect.left() + 3.0, rect.top() + 3.0, rect.width() - 6.0, rect.height() - 6.0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.sel_bg if selected else self.bg)
        painter.drawRoundedRect(card, 6, 6)

        if selected:
            bc = QColor(self.sel_border)
            bc.setAlphaF(pulse_alpha(self.pulse_enabled))
            painter.setPen(QPen(bc, 2))
        elif hovered:
            painter.setPen(QPen(self.hover_border, 1))
        else:
            painter.setPen(QPen(self.border, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(card, 6, 6)

        if item.is_favorite:
            if self.star_font is None:
                self.star_font = QFont('Microsoft YaHei', 12)
                self.star_font.setBold(True)
            painter.setFont(self.star_font)
            painter.setPen(QPen(self.favorite_color, 1))
            painter.drawText(QRectF(card.right() - 24, card.top() + 1, 20, 20), Qt.AlignCenter, '★')


        thumb_area = QRectF(card.left() + 6, card.top() + 6, card.width() - 12, THUMB_SIZE - 16)
        pm = get_thumb_pixmap(item)
        if pm is not None:
            rw, rh = _fit(pm.width(), pm.height(), thumb_area.width(), thumb_area.height())
            target = QRectF(thumb_area.center().x() - rw / 2, thumb_area.center().y() - rh / 2, rw, rh)
            painter.drawPixmap(target.toRect(), pm)
        else:
            painter.setBrush(QColor(self.placeholder_bg))
            painter.setPen(QPen(self.border, 1))
            painter.drawRoundedRect(thumb_area, 4, 4)
            painter.setFont(self.small_font)
            painter.setPen(QPen(self.placeholder_fg, 1))
            painter.drawText(thumb_area, Qt.AlignCenter, '无图' if not item.exists else '…')

        below_top = thumb_area.bottom() + 4
        name_rect = QRectF(card.left() + 6, below_top, card.width() - 12, 16)
        painter.setFont(self.name_font)
        painter.setPen(QPen(self.name_color, 1))
        elided = painter.fontMetrics().elidedText(item.name, Qt.ElideRight, int(name_rect.width()))
        painter.drawText(name_rect, Qt.AlignHCenter | Qt.AlignTop, elided)

        if item.tags:
            tag_rect = QRectF(card.left() + 6, name_rect.bottom() + 1, card.width() - 12,
                              card.bottom() - name_rect.bottom() - 6)
            painter.setFont(self.small_font)
            painter.setPen(QPen(self.tag_color, 1))
            tag_text = '　'.join(item.tags)
            tag_elided = painter.fontMetrics().elidedText(tag_text, Qt.ElideRight, int(tag_rect.width()))
            painter.drawText(tag_rect, Qt.AlignHCenter | Qt.AlignTop, tag_elided)

        painter.restore()


#图片预览区

class PreviewWindow(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background-color: #0F1216; border: 1px solid #2A323B; border-radius: 6px;')
        self.setMouseTracking(True)
        self._name = ''
        self._error = ''
        self.movie = None
        self.pixmap = QPixmap()
        self.zoom = 1.0
        self._min_zoom = 0.05
        self._max_zoom = 20.0
        self._offset = QPointF(0, 0)
        self._dragging = False
        self._last = QPoint()
        self._user_zoomed = False
        self._build_zoom_bar()

    def _build_zoom_bar(self):
        self._zoom_bar = QWidget(self)
        self._zoom_bar.setObjectName('zoomBar')
        self._zoom_bar.setStyleSheet(
            'QWidget#zoomBar { background: transparent; }'
            'QPushButton#zoomBtn { background: transparent; border: none; '
            'color: rgba(220,220,220,0.85); font-size: 13px; padding: 2px 10px; }'
            'QPushButton#zoomBtn:hover { color: #FFFFFF; }'
        )
        lay = QHBoxLayout(self._zoom_bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        for text, slot in (('−', lambda: self.zoom_by(1 / 1.25)),
                           ('适应', self.zoom_fit),
                           ('＋', lambda: self.zoom_by(1.25)),
                           ('100%', self.zoom_actual)):
            b = QPushButton(text)
            b.setObjectName('zoomBtn')
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            lay.addWidget(b)
        eff = QGraphicsOpacityEffect(self._zoom_bar)
        eff.setOpacity(0.75)
        self._zoom_bar.setGraphicsEffect(eff)
        self._zoom_bar.adjustSize()
        self._zoom_bar.hide()

    def _position_zoom_bar(self):
        hint = self._zoom_bar.sizeHint()
        w, h = hint.width(), hint.height()
        self._zoom_bar.setGeometry((self.width() - w) // 2, self.height() - h - 12, w, h)

    def _update_zoom_bar_visibility(self, y):
        has_img = (not self.pixmap.isNull()
                   or (self.movie is not None and not self.movie.currentPixmap().isNull()))
        show = has_img and y >= self.height() - 78
        if show:
            self._position_zoom_bar()
        self._zoom_bar.setVisible(show)

    def _source_size(self):
        if not self.pixmap.isNull():
            return self.pixmap.size()
        if self.movie is not None and not self.movie.currentPixmap().isNull():
            return self.movie.currentPixmap().size()
        return QSize()

    def show_path(self, path, name):
        if self.movie:
            self.movie.stop()
        self.movie = None
        self.pixmap = QPixmap()
        self._error = ''
        self._name = name or ''
        self.zoom = 1.0
        self._offset = QPointF(0, 0)
        self._user_zoomed = False
        self._zoom_bar.hide()
        if not path or not os.path.isfile(path):
            self._error = '无法加载：{}'.format(name)
            self.update()
            return
        if is_animated_gif(path):
            movie = QMovie(path)
            if movie.isValid():
                self.movie = movie
                movie.frameChanged.connect(lambda _f: self.update())
                movie.start()
                self._fit()
                self.update()
                return
        self.pixmap = QPixmap(path)
        if self.pixmap.isNull():
            self._error = '无法加载：{}'.format(name)
            self.update()
            return
        self._fit()
        self.update()

    def clear(self):
        if self.movie:
            self.movie.stop()
        self.movie = None
        self.pixmap = QPixmap()
        self._error = ''
        self.zoom = 1.0
        self._offset = QPointF(0, 0)
        self._zoom_bar.hide()
        self.update()

    def _fit(self):
        src = self._source_size()
        w, h = self.width(), self.height()
        if src.width() <= 0 or src.height() <= 0 or w <= 0 or h <= 0:
            self.zoom = 1.0
            return
        self.zoom = min(w / src.width(), h / src.height(), 1.0)
        self._offset = QPointF(0, 0)
        self._user_zoomed = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_zoom_bar()
        if not self._user_zoomed:
            self._fit()
            self.update()

    def zoom_actual(self):
        self.zoom = 1.0
        self._offset = QPointF(0, 0)
        self._user_zoomed = True
        self.update()

    def zoom_fit(self):
        self._fit()
        self.update()

    def zoom_by(self, factor):
        self.zoom = max(self._min_zoom, min(self._max_zoom, self.zoom * factor))
        self._user_zoomed = True
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#0F1216'))
        if self._error:
            painter.setPen(QColor('#8C97A0'))
            painter.drawText(self.rect(), Qt.AlignCenter, self._error)
            painter.end()
            return
        src = self._source_size()
        if src.width() <= 0 or src.height() <= 0:
            painter.end()
            return
        scaled = src * self.zoom
        cx = self.width() / 2 + self._offset.x()
        cy = self.height() / 2 + self._offset.y()
        target = QRectF(cx - scaled.width() / 2, cy - scaled.height() / 2,
                        scaled.width(), scaled.height())
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if not self.pixmap.isNull():
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        elif self.movie is not None and not self.movie.currentPixmap().isNull():
            pm = self.movie.currentPixmap()
            painter.drawPixmap(target, pm, QRectF(pm.rect()))
        painter.setPen(QColor('#8C97A0'))
        painter.drawText(QRectF(8, self.height() - 24, 160, 20),
                         Qt.AlignLeft | Qt.AlignVCenter, '{}%'.format(int(round(self.zoom * 100))))
        painter.end()

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
        new_zoom = max(self._min_zoom, min(self._max_zoom, self.zoom * factor))
        src = self._source_size()
        if self.zoom > 0 and src.width() > 0 and src.height() > 0:
            before = event.pos()
            cx = self.width() / 2 + self._offset.x()
            cy = self.height() / 2 + self._offset.y()
            px = (before.x() - cx) / self.zoom
            py = (before.y() - cy) / self.zoom
            self._offset = QPointF(before.x() - px * new_zoom - self.width() / 2,
                                   before.y() - py * new_zoom - self.height() / 2)
        self.zoom = new_zoom
        self._user_zoomed = True
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last = event.pos()
            self._user_zoomed = True
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            d = event.pos() - self._last
            self._offset += QPointF(d.x(), d.y())
            self._last = event.pos()
            self.update()
            event.accept()
        self._update_zoom_bar_visibility(event.pos().y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.unsetCursor()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.zoom_fit()
            event.accept()

    def leaveEvent(self, event):
        self._zoom_bar.hide()
        super().leaveEvent(event)


#图片导入对话框

class ImportDialog(QDialog):
    def __init__(self, files, groups, default_gid, parent=None, nested=False):
        super().__init__(parent)
        self.setWindowTitle('导入图片')
        self.resize(700, 540)
        self.files = files

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel('导入到父集：'))
        self.group_combo = QComboBox()
        self.group_combo.addItem(UNC_NAME, UNC_ID)

        def _depth_of(g):
            ids = {x.group_id for x in groups}
            d = 0
            cur = g
            seen = {g.group_id}
            while cur.parent_id and cur.parent_id in ids and cur.parent_id not in seen:
                seen.add(cur.parent_id)
                d += 1
                cur = next((x for x in groups if x.group_id == cur.parent_id), None)
                if cur is None:
                    break
            return d

        sorted_groups = sorted([g for g in groups if g.group_id != UNC_ID],
                               key=lambda g: (_depth_of(g), g.priority, g.timestamp))
        for g in sorted_groups:
            label = ('　' * _depth_of(g) + g.name) if nested else g.name
            self.group_combo.addItem(label, g.group_id)
        idx = self.group_combo.findData(default_gid)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)
        row.addWidget(self.group_combo, 1)
        layout.addLayout(row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel('命名方式：'))
        self.single_radio = QRadioButton('单独命名（逐张填写）')
        self.batch_radio = QRadioButton('批量命名（前缀+序号）')
        self.single_radio.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.single_radio)
        mode_group.addButton(self.batch_radio)
        mode_row.addWidget(self.single_radio)
        mode_row.addWidget(self.batch_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel('前缀：'))
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText('例如「表情」')
        batch_row.addWidget(self.prefix_edit)
        batch_row.addWidget(QLabel('起始序号：'))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 100000)
        batch_row.addWidget(self.start_spin)
        apply_btn = QPushButton('按 前缀+序号 应用')
        apply_btn.clicked.connect(self.apply_prefix)
        batch_row.addWidget(apply_btn)
        default_btn = QPushButton('全部用默认名')
        default_btn.clicked.connect(self.apply_default)
        batch_row.addWidget(default_btn)
        self.batch_wrap = QWidget()
        self.batch_wrap.setLayout(batch_row)
        layout.addWidget(self.batch_wrap)

        self.batch_radio.toggled.connect(self._on_mode_changed)
        self._on_mode_changed()

        self.table = QTableWidget(len(files), 2)
        self.table.setHorizontalHeaderLabels(['源文件', '名称'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)
        for i, f in enumerate(files):
            base = crypto.peek_name(f) if crypto.is_encrypted_path(f) else None
            if not base:
                base = os.path.splitext(os.path.basename(f))[0]
            src_item = QTableWidgetItem(os.path.basename(f))
            src_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, src_item)
            self.table.setItem(i, 1, QTableWidgetItem(base))
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        ok = QPushButton('开始导入')
        ok.setObjectName('primary')
        ok.clicked.connect(self.accept)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def apply_prefix(self):
        prefix = self.prefix_edit.text().strip()
        start = self.start_spin.value()
        for i in range(self.table.rowCount()):
            self.table.item(i, 1).setText('{}{}'.format(prefix, start + i))

    def apply_default(self):
        for i in range(self.table.rowCount()):
            base = os.path.splitext(os.path.basename(self.files[i]))[0]
            self.table.item(i, 1).setText(base)

    def _on_mode_changed(self):
        self.batch_wrap.setVisible(self.batch_radio.isChecked())

    def result(self):
        gid = self.group_combo.currentData()
        jobs = []
        for i in range(self.table.rowCount()):
            name = self.table.item(i, 1).text().strip()
            if not name:
                name = os.path.splitext(os.path.basename(self.files[i]))[0]
            jobs.append((self.files[i], name))
        return jobs, gid


class BatchRenameDialog(QDialog):

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle('集中命名（{} 张）'.format(len(items)))
        self.resize(640, 460)
        self.items = items

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel('批量命名 前缀：'))
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText('例如「表情」')
        batch_row.addWidget(self.prefix_edit)
        batch_row.addWidget(QLabel('起始序号：'))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 100000)
        batch_row.addWidget(self.start_spin)
        apply_btn = QPushButton('按 前缀+序号 应用')
        apply_btn.clicked.connect(self.apply_prefix)
        batch_row.addWidget(apply_btn)
        restore_btn = QPushButton('恢复原名')
        restore_btn.clicked.connect(self.apply_restore)
        batch_row.addWidget(restore_btn)
        layout.addLayout(batch_row)

        self.table = QTableWidget(len(items), 2)
        self.table.setHorizontalHeaderLabels(['原名称', '新名称'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)
        for i, it in enumerate(items):
            src_item = QTableWidgetItem(it.name)
            src_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, src_item)
            self.table.setItem(i, 1, QTableWidgetItem(it.name))
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        ok = QPushButton('应用')
        ok.setObjectName('primary')
        ok.clicked.connect(self.accept)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def apply_prefix(self):
        prefix = self.prefix_edit.text().strip()
        start = self.start_spin.value()
        for i in range(self.table.rowCount()):
            self.table.item(i, 1).setText('{}{}'.format(prefix, start + i))

    def apply_restore(self):
        for i, it in enumerate(self.items):
            self.table.item(i, 1).setText(it.name)

    def names(self):
        return [self.table.item(i, 1).text().strip() for i in range(self.table.rowCount())]


#主窗口

class EmojiManagerSystem(QMainWindow):
    def __init__(self, app, cfg):
        super().__init__()
        self.cfg = cfg
        ensure_dirs()
        if not self._preload_enabled():
            _legacy_cache = os.path.join(DATA_DIR, 'cache')
            if os.path.isdir(_legacy_cache):
                shutil.rmtree(_legacy_cache, ignore_errors=True)
        QPixmapCache.setCacheLimit(64 * 1024)           #将图片缓存限制为 64 MB

        self.app = app
        self.palette = dict(cfg['palette'])
        self.anim = dict(cfg['anim'])
        self._entrance_played = False
        self.items = []
        self.groups = []
        self.current_group_id = None
        self._preview_item = None
        self.thumb_threads = []
        self._sim_ids = None
        self._sim_ref = None
        self._filter_type = None
        self._filter_tag = None
        self._collapsed_groups = set()
        self.search_popup = None
        self._suppress_search_reset = False

        self.build_ui()
        self.setWindowTitle('PRTS · 管理终端')
        self.resize(1440, 840)
        self.statusBar().showMessage('正在加载数据…')

        self.loader = DataLoaderThread(self)
        self.loader.loaded.connect(self._on_loaded)
        self.loader.failed.connect(self._on_load_failed)
        self.loader.start()

    def build_ui(self):
        central = AmbientBackground(self.palette, self.anim)
        self.ambient = central
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        left = QFrame()
        left.setObjectName('panel')
        left.setFixedWidth(240)
        self.left_panel = left
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 14, 12, 12)
        left_layout.setSpacing(8)

        header = QLabel('父集 / GROUPS')
        header.setObjectName('header')
        left_layout.addWidget(header)

        self.group_list = QListWidget()
        self.group_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_list.customContextMenuRequested.connect(self._on_group_menu)
        self.group_list.currentItemChanged.connect(self._on_group_clicked)
        self.group_list.itemDoubleClicked.connect(self._on_group_double_clicked)
        left_layout.addWidget(self.group_list, 1)

        new_btn = QPushButton('＋ 新建父集')
        new_btn.setObjectName('primary')
        new_btn.clicked.connect(lambda: self.create_group())
        left_layout.addWidget(new_btn)

        import_pack_btn = QPushButton('导入父集 (.zip)')
        import_pack_btn.clicked.connect(self.import_group_zip)
        left_layout.addWidget(import_pack_btn)

        root.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        top = QFrame()
        top.setObjectName('panel')
        self.top_panel = top
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('搜索名称 / 标签')
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.search_edit.editingFinished.connect(self._on_search_committed)
        top_layout.addWidget(self.search_edit, 1)

        self.search_expand = QPushButton('+')
        self.search_expand.setFixedWidth(32)
        self.search_expand.setToolTip('展开')
        self.search_expand.clicked.connect(self._toggle_search_popup)
        top_layout.addWidget(self.search_expand)

        self.format_combo = QComboBox()
        self.format_combo.addItems(['全部', 'gif', 'NOT git', 'PNG', 'JPG', 'BMP', 'WebP'])
        self.format_combo.setToolTip('按图片格式筛选')
        self.format_combo.currentIndexChanged.connect(lambda _i: self.rebuild_model())
        top_layout.addWidget(self.format_combo)

        self.fav_check = QCheckBox('只看收藏')
        self.fav_check.toggled.connect(lambda _v: self.rebuild_model())
        top_layout.addWidget(self.fav_check)

        import_btn = QPushButton('导入图片')
        import_btn.setObjectName('primary')
        import_btn.clicked.connect(self.import_images)
        top_layout.addWidget(import_btn)

        import_folder_btn = QPushButton('导入文件夹')
        import_folder_btn.clicked.connect(self.import_folder)
        top_layout.addWidget(import_folder_btn)

        export_btn = QPushButton('导出')
        export_btn.clicked.connect(self.export_flow)
        top_layout.addWidget(export_btn)

        settings_btn = QPushButton('设置')
        settings_btn.clicked.connect(self.open_settings)
        top_layout.addWidget(settings_btn)

        center_layout.addWidget(top)

        self.sim_banner = QFrame()
        self.sim_banner.setObjectName('panel')
        sim_lay = QHBoxLayout(self.sim_banner)
        sim_lay.setContentsMargins(10, 6, 10, 6)
        sim_lay.setSpacing(8)
        self.sim_label = QLabel('')
        self.sim_label.setObjectName('sectionTitle')
        sim_lay.addWidget(self.sim_label, 1)
        sim_clear = QPushButton('退出相似度查找')
        sim_clear.clicked.connect(self.clear_sim_filter)
        sim_lay.addWidget(sim_clear)
        self.sim_banner.setVisible(False)
        center_layout.addWidget(self.sim_banner)

        self.model = QStandardItemModel(self)
        self.grid_view = QListView()
        self.grid_view.setModel(self.model)
        self.grid_view.setViewMode(QListView.IconMode)
        self.grid_view.setResizeMode(QListView.Adjust)
        self.grid_view.setMovement(QListView.Static)
        self.grid_view.setUniformItemSizes(True)
        self.grid_view.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self.grid_view.setSpacing(4)
        self.grid_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grid_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.grid_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.delegate = EmojiThumbDelegate(self.palette, self.anim.get('selection_pulse', True), self.grid_view)
        self.grid_view.setItemDelegate(self.delegate)
        self.grid_view.setMouseTracking(True)
        self.grid_view.setLayoutMode(QListView.Batched)
        self.grid_view.setBatchSize(120)
        self.grid_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid_view.customContextMenuRequested.connect(self._on_grid_menu)
        self.grid_view.doubleClicked.connect(self._on_grid_double)
        self.grid_view.setStyleSheet('background-color: transparent; border: none;')

        self.pulse = PulseRepainter(self.grid_view, self.anim)
        self.grid_view.selectionModel().selectionChanged.connect(lambda *a: self.pulse.sync())

        self.empty_label = QLabel('这里空空如也\n点击「导入图片」开始收集表情包')
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setObjectName('hint')

        self.grid_stack = QStackedWidget()
        self.grid_stack.addWidget(self.grid_view)
        self.grid_stack.addWidget(self.empty_label)
        center_layout.addWidget(self.grid_stack, 1)

        root.addWidget(center, 1)

        right = QFrame()
        right.setObjectName('panel')
        right.setFixedWidth(380)
        self.right_panel = right
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 14, 12, 12)
        right_layout.setSpacing(8)

        pheader = QLabel('在线预览 / PREVIEW')
        pheader.setObjectName('header')
        right_layout.addWidget(pheader)

        self.preview = PreviewWindow()
        right_layout.addWidget(self.preview, 1)

        self.preview_name = QLabel('选择表情包进行预览')
        self.preview_name.setObjectName('sectionTitle')
        self.preview_name.setWordWrap(True)
        right_layout.addWidget(self.preview_name)

        btn_grid = QGridLayout()
        btn_grid.setSpacing(6)

        b_preview = QPushButton('预览')
        b_preview.clicked.connect(self.preview_selected)
        btn_grid.addWidget(b_preview, 0, 0)

        b_rename = QPushButton('重命名')
        b_rename.clicked.connect(self.rename_selected)
        btn_grid.addWidget(b_rename, 0, 1)

        b_fav = QPushButton('收藏 / 取消')
        b_fav.clicked.connect(self.toggle_favorite_selected)
        btn_grid.addWidget(b_fav, 1, 0)

        b_move = QPushButton('移动到父集')
        b_move.clicked.connect(self._move_selected_menu)
        btn_grid.addWidget(b_move, 1, 1)

        b_delete = QPushButton('删除')
        b_delete.setObjectName('danger')
        b_delete.clicked.connect(self.delete_selected)
        btn_grid.addWidget(b_delete, 2, 0, 1, 2)

        right_layout.addLayout(btn_grid)
        root.addWidget(right)

        self._build_search_popup()

    def _build_search_popup(self):
        self.search_popup = QFrame(self, Qt.Popup)
        self.search_popup.setObjectName('panel')
        self.search_popup.setFixedWidth(300)
        popup_lay = QVBoxLayout(self.search_popup)
        popup_lay.setContentsMargins(8, 8, 8, 8)
        popup_lay.setSpacing(4)

        h_recent = QLabel('最近搜索')
        h_recent.setObjectName('sectionTitle')
        popup_lay.addWidget(h_recent)
        self.recent_list = QListWidget()
        self.recent_list.setFixedHeight(110)
        self.recent_list.itemClicked.connect(self._on_recent_clicked)
        popup_lay.addWidget(self.recent_list)

        h_tags = QLabel('全部 tag')
        h_tags.setObjectName('sectionTitle')
        popup_lay.addWidget(h_tags)
        self.tag_list = QListWidget()
        self.tag_list.setFixedHeight(120)
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        popup_lay.addWidget(self.tag_list)

        h_types = QLabel('tag 类型')
        h_types.setObjectName('sectionTitle')
        popup_lay.addWidget(h_types)
        self.type_list = QListWidget()
        self.type_list.setFixedHeight(120)
        self.type_list.itemClicked.connect(self._on_type_clicked)
        popup_lay.addWidget(self.type_list)

    #动画和设置

    def play_entrance(self):
        if self._entrance_played:
            return
        self._entrance_played = True
        if not anim_enabled(self.cfg, 'panel_entrance'):
            return
        panels = (self.left_panel, self.top_panel, self.right_panel)
        for i, panel in enumerate(panels):
            def _clear(w=panel):
                w.setGraphicsEffect(None)
            fade_in(panel, 320, i * 60, on_done=_clear)

    def open_settings(self):
        SettingsDialog(self.cfg, self).exec_()

    def apply_settings(self, cfg):
        self.cfg = cfg
        self.palette = dict(cfg['palette'])
        self.anim = dict(cfg['anim'])
        apply_theme(self.app, self.palette)
        self.ambient.set_palette(self.palette)
        self.ambient.set_anim(self.anim)
        self.delegate.set_palette(self.palette)
        self.delegate.set_pulse_enabled(self.anim.get('selection_pulse', True))
        self.pulse.set_enabled(self.anim.get('selection_pulse', True))
        if self._collapse_persist_enabled():
            cfg['collapsed_groups'] = sorted(self._collapsed_groups)
        else:
            cfg['collapsed_groups'] = []
        self.refresh_group_list()
        self.grid_view.viewport().update()

    #加载数据

    def _on_loaded(self, item_dicts, group_dicts):
        self.items = [EmojiItem.from_dict(d) for d in item_dicts if d.get('path')]
        self.groups = [EmojiGroup.from_dict(d) for d in group_dicts if d.get('group_id')]
        if not any(g.group_id == UNC_ID for g in self.groups):
            self.groups.insert(0, EmojiGroup(UNC_ID, UNC_NAME, color='#9A9A9A', is_system=True))
        ids = {g.group_id for g in self.groups}
        for g in self.groups:
            if g.parent_id and g.parent_id not in ids:
                g.parent_id = None
        self._normalize_priority()
        self._restore_collapsed_groups()
        self._refresh_runtime()
        self.refresh_group_list()
        self.rebuild_model()
        self.statusBar().showMessage('共 {} 张图片 · {} 个父集'.format(len(self.items), len(self.groups)))

        if self._preload_enabled():
            need = [it for it in self.items if not (it.thumb_abs and os.path.exists(it.thumb_abs))]
            if need:
                self._start_thumbnails(need)

    def _on_load_failed(self, err):
        self.statusBar().showMessage('加载数据失败：{}'.format(err))
        self._on_loaded([], [])

    def _refresh_runtime(self):
        for it in self.items:
            src = abs_emoji(it.path)
            it.exists = bool(src and os.path.isfile(src))
            if it.thumbnail:
                ta = abs_cached(it.thumbnail)
                it.thumb_abs = ta if (ta and os.path.exists(ta)) else None
            else:
                it.thumb_abs = None

    def _start_thumbnails(self, items):
        if not items:
            return
        t = ThumbnailThread(items, self)
        t.progress.connect(self._on_thumb_progress)
        t.ready.connect(self._on_thumb_ready)
        t.done.connect(self._on_thumb_done)
        self.thumb_threads.append(t)
        t.start()

    def _on_thumb_progress(self, n, total):
        self.statusBar().showMessage('生成缩略图 {}/{}…'.format(n, total))

    def _on_thumb_ready(self, item, thumb_abs, exists):
        item.thumb_abs = thumb_abs if (thumb_abs and os.path.exists(thumb_abs)) else None
        item.exists = exists
        if thumb_abs and os.path.exists(thumb_abs):
            item.thumbnail = rel_root(thumb_abs)
        self.grid_view.viewport().update()

    def _on_thumb_done(self):
        self.save_data()
        self.refresh_group_list()
        self.statusBar().showMessage('共 {} 张图片 · {} 个父集'.format(len(self.items), len(self.groups)))
        self.grid_view.viewport().update()

    def clear_thumbnail_cache(self, owner_dialog=None):
        cleared = 0
        freed = 0
        if os.path.isdir(THUMB_DIR):
            for fn in os.listdir(THUMB_DIR):
                p = os.path.join(THUMB_DIR, fn)
                if os.path.isfile(p):
                    try:
                        freed += os.path.getsize(p)
                        os.remove(p)
                        cleared += 1
                    except OSError:
                        pass
        for it in self.items:
            if it.thumbnail or it.thumb_abs:
                it.thumbnail = None
                it.thumb_abs = None
        QPixmapCache.clear()
        self.save_data()
        self.rebuild_model()
        self.grid_view.viewport().update()

        def _fmt(n):
            if n >= 1024 * 1024:
                return '{:.1f} MB'.format(n / 1024.0 / 1024.0)
            if n >= 1024:
                return '{:.1f} KB'.format(n / 1024.0)
            return '{} B'.format(n)

        msg = ('已清除 {} 个缩略图缓存文件,释放 {}.'.format(cleared, _fmt(freed))
               if cleared else '没有需要清除的缩略图缓存 ')
        QMessageBox.information(owner_dialog if owner_dialog is not None else self,
                                '清除缩略图缓存', msg)
        return cleared, freed

    #保存数据

    def save_data(self):
        safe_write_json(EMOJIS_JSON, [e.to_dict() for e in self.items])
        safe_write_json(GROUPS_JSON, [g.to_dict() for g in self.groups])

    #图片显示和筛选

    def _fmt_ok(self, item):
        f = self.format_combo.currentText()
        ext = os.path.splitext(item.path)[1].lower() or '.png'
        if f == '动图 (GIF)':
            return ext == '.gif'
        if f == '静态图':
            return ext != '.gif'
        if f == 'PNG':
            return ext == '.png'
        if f == 'JPG':
            return ext in ('.jpg', '.jpeg')
        if f == 'BMP':
            return ext == '.bmp'
        if f == 'WebP':
            return ext == '.webp'
        return True

    def visible_items(self):
        items = list(self.items)
        if self.current_group_id is not None:
            items = [it for it in items if it.group_id == self.current_group_id]
        if self.fav_check.isChecked():
            items = [it for it in items if it.is_favorite]
        if self._sim_ids is not None:
            items = [it for it in items if id(it) in self._sim_ids]
        if self._filter_type:
            items = [it for it in items
                     if any(_tag_type(t) == self._filter_type for t in it.tags)]
        if self._filter_tag:
            items = [it for it in items if self._filter_tag in it.tags]
        items = [it for it in items if self._fmt_ok(it)]
        q = self.search_edit.text().strip().lower()
        if q:
            items = [it for it in items
                     if q in it.name.lower() or any(q in t.lower() for t in it.tags)]
        items.sort(key=lambda it: (not it.is_favorite, it.name.lower()))
        return items

    def rebuild_model(self):
        vis = self.visible_items()
        self.model.removeRows(0, self.model.rowCount())
        for it in vis:
            std = QStandardItem()
            std.setData(it, Qt.UserRole)
            std.setEditable(False)
            self.model.appendRow(std)
        self.grid_stack.setCurrentIndex(0 if vis else 1)
        self.grid_view.viewport().update()

    #tag 类型 / 搜索

    def all_tags(self):
        tags = set()
        for it in self.items:
            for t in it.tags:
                tags.add(t)
        return sorted(tags)

    def all_tag_types(self):
        types = set()
        for g in self.groups:
            for t in (g.tag_types or []):
                types.add(t)
        for it in self.items:
            for t in it.tags:
                tt = _tag_type(t)
                if tt != '未分类':
                    types.add(tt)
        return sorted(types)

    def _on_search_changed(self, text):
        if self._suppress_search_reset:
            self.rebuild_model()
            return
        self._filter_type = None
        self._filter_tag = None
        self.rebuild_model()
        if self.search_popup is not None and self.search_popup.isVisible():
            self._populate_search_popup(text)

    def _on_search_committed(self):
        q = self.search_edit.text().strip()
        if q:
            self._record_search(q)

    def _record_search(self, q):
        rec = [r for r in self.cfg.get('recent_searches', []) if r != q]
        rec.insert(0, q)
        self.cfg['recent_searches'] = rec[:5]
        try:
            save_settings(self.cfg)
        except OSError:
            pass

    def _toggle_search_popup(self):
        if self.search_popup.isVisible():
            self.search_popup.hide()
        else:
            self._show_search_popup()

    def _show_search_popup(self):
        self._populate_search_popup(self.search_edit.text())
        pos = self.search_edit.mapToGlobal(QPoint(0, self.search_edit.height() + 3))
        self.search_popup.move(pos)
        self.search_popup.show()
        self.search_popup.raise_()

    def _populate_search_popup(self, text=''):
        text = (text or '').strip().lower()
        self.recent_list.blockSignals(True)
        self.recent_list.clear()
        for r in self.cfg.get('recent_searches', []):
            self.recent_list.addItem(QListWidgetItem(r))
        self.recent_list.blockSignals(False)

        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for t in self.all_tags():
            if not text or text in t.lower():
                self.tag_list.addItem(QListWidgetItem(t))
        self.tag_list.blockSignals(False)

        self.type_list.blockSignals(True)
        self.type_list.clear()
        for tp in self.all_tag_types():
            if not text or text in tp.lower():
                self.type_list.addItem(QListWidgetItem(tp))
        self.type_list.blockSignals(False)

    def _on_recent_clicked(self, item):
        txt = item.text()
        self._suppress_search_reset = True
        self._filter_type = None
        self._filter_tag = None
        self.search_edit.setText(txt)
        self._suppress_search_reset = False
        self.search_popup.hide()
        self.rebuild_model()

    def _on_tag_clicked(self, item):
        tag = item.text()
        self._suppress_search_reset = True
        self._filter_type = None
        self._filter_tag = tag
        self.search_edit.setText(tag)
        self._suppress_search_reset = False
        self.search_popup.hide()
        self.rebuild_model()

    def _on_type_clicked(self, item):
        tp = item.text()
        self._suppress_search_reset = True
        self._filter_type = tp
        self._filter_tag = None
        self.search_edit.setText(tp + ':')
        self._suppress_search_reset = False
        self.search_popup.hide()
        self.rebuild_model()

    #相似度查找

    def _similarity_search(self, ref_item):
        pool = [it for it in self.items if it.group_id == ref_item.group_id]
        if len(pool) < 1:
            QMessageBox.information(self, '提示', '没有可比较的图片')
            return
        try:
            ref_dh = _dhash(abs_emoji(ref_item.path))
        except Exception as e:
            QMessageBox.warning(self, '提示', '无法计算参照图哈希：{}'.format(e))
            return
        if ref_dh is None:
            QMessageBox.warning(self, '提示', '无法读取参照图片')
            return
        threshold = self._similarity_threshold()
        matches = []
        for it in pool:
            p = abs_emoji(it.path)
            if not p or not os.path.isfile(p):
                continue
            dh = getattr(it, '_dhash', None)
            if dh is None:
                try:
                    dh = _dhash(p)
                except Exception:
                    dh = None
                it._dhash = dh
            if dh is None:
                continue
            sim = _similarity_pct(ref_dh, dh)
            if sim >= threshold or id(it) == id(ref_item):
                matches.append((sim, it))
        matches.sort(key=lambda x: -x[0])
        ids = {id(it) for _sim, it in matches}
        self._sim_ids = ids
        self._sim_ref = ref_item
        self.sim_label.setText('相似度查找：{} 张（基于「{}」,阈值 {}%）'.format(
            len(ids), ref_item.name, threshold))
        self.sim_banner.setVisible(True)
        self.rebuild_model()

    def clear_sim_filter(self):
        self._sim_ids = None
        self._sim_ref = None
        self.sim_banner.setVisible(False)
        self.rebuild_model()

    #父集排序和嵌套

    def _nested_enabled(self):
        cfg = getattr(self, 'cfg', {})
        return bool(cfg.get('features', {}).get('nested_groups'))

    def _preload_enabled(self):
        cfg = getattr(self, 'cfg', {})
        return bool(cfg.get('features', {}).get('preload'))

    def _encrypt_enabled(self):
        cfg = getattr(self, 'cfg', {})
        return bool(cfg.get('features', {}).get('encrypted_export'))

    def _dedup_enabled(self):
        cfg = getattr(self, 'cfg', {})
        return bool(cfg.get('dedup_enabled', True))

    def _dedup_similarity(self):
        cfg = getattr(self, 'cfg', {})
        return int(cfg.get('dedup_similarity', 100))

    def _similar_search_enabled(self):
        cfg = getattr(self, 'cfg', {})
        return bool(cfg.get('features', {}).get('similar_search'))

    def _collapse_persist_enabled(self):
        cfg = getattr(self, 'cfg', {})
        return bool(cfg.get('features', {}).get('collapse_persist'))

    def _similarity_threshold(self):
        cfg = getattr(self, 'cfg', {})
        v = int(cfg.get('similarity_threshold', 90))
        return max(0, min(100, v))

    def _group_sort_key(self, g):
        #系统父集置顶,其余按优先级和创建时间排序
        return (0 if g.is_system else 1, g.priority, g.timestamp)

    def _ordered_groups(self):
        by_parent = {}
        for g in self.groups:
            by_parent.setdefault(g.parent_id, []).append(g)
        ordered = []
        seen = set()

        def walk(pid, depth):
            for c in sorted(by_parent.get(pid, []), key=self._group_sort_key):
                if c.group_id in seen:
                    continue
                seen.add(c.group_id)
                ordered.append((c, depth))
                walk(c.group_id, depth + 1)

        walk(None, 0)
        for g in self.groups:
            if g.group_id not in seen:
                ordered.append((g, 0))
        return ordered

    def _display_groups(self):
        if self._nested_enabled():
            return [(g, d) for g, d in self._ordered_groups()
                    if not self._group_hidden_by_collapse(g)]
        return [(g, 0) for g in sorted(self.groups, key=self._group_sort_key)]

    def _siblings(self, group):
        pid = group.parent_id
        return sorted([g for g in self.groups if g.parent_id == pid and not g.is_system],
                      key=self._group_sort_key)

    def _normalize_priority(self):
        by_parent = {}
        for g in self.groups:
            if g.is_system:
                continue
            by_parent.setdefault(g.parent_id, []).append(g)
        for siblings in by_parent.values():
            for i, g in enumerate(sorted(siblings, key=self._group_sort_key)):
                g.priority = i

    def _next_group_priority(self, parent_id):
        siblings = [g for g in self.groups if g.parent_id == parent_id and not g.is_system]
        return max([g.priority for g in siblings], default=-1) + 1

    def _unique_group_name(self, base):
        base = str(base).strip() or '新建父集'
        name = base
        k = 1
        while any(g.name == name for g in self.groups):
            name = '{}_{}'.format(base, k)
            k += 1
        return name

    def _group_depth(self, g):
        depth = 0
        cur = g
        seen = {g.group_id}
        while cur.parent_id:
            nxt = self._find_group(cur.parent_id)
            if nxt is None or nxt.group_id in seen:
                break
            seen.add(nxt.group_id)
            depth += 1
            cur = nxt
        return depth

    def _group_display_name(self, g):
        if not self._nested_enabled():
            return g.name
        return '{}{}'.format('　' * self._group_depth(g), g.name)

    def _group_has_children(self, gid):
        return any(g.parent_id == gid for g in self.groups)

    def _group_is_collapsed(self, gid):
        return gid in self._collapsed_groups

    def _group_hidden_by_collapse(self, g):
        cur = g
        seen = set()
        while cur.parent_id:
            if cur.parent_id in seen:
                break
            seen.add(cur.parent_id)
            if self._group_is_collapsed(cur.parent_id):
                return True
            cur = self._find_group(cur.parent_id)
            if cur is None:
                break
        return False

    def _toggle_group_collapse(self, gid):
        if gid in self._collapsed_groups:
            self._collapsed_groups.discard(gid)
        else:
            self._collapsed_groups.add(gid)
        if self._collapse_persist_enabled():
            self._save_collapsed_groups()
        self.refresh_group_list()

    def _save_collapsed_groups(self):
        self.cfg['collapsed_groups'] = sorted(self._collapsed_groups)
        save_settings(self.cfg)

    def _restore_collapsed_groups(self):
        self._collapsed_groups = set()
        if self._collapse_persist_enabled():
            stored = self.cfg.get('collapsed_groups', [])
            if isinstance(stored, list):
                valid = {g.group_id for g in self.groups}
                self._collapsed_groups = {g for g in stored if isinstance(g, str) and g in valid}

    def refresh_group_list(self):
        self.group_list.blockSignals(True)
        self.group_list.clear()

        all_item = QListWidgetItem('全部图片  ({})'.format(len(self.items)))
        all_item.setData(Qt.UserRole, ALL_MARK)
        self.group_list.addItem(all_item)

        for g, depth in self._display_groups():
            cnt = sum(1 for it in self.items if it.group_id == g.group_id)
            star = '★ ' if g.is_favorite else ''
            mark = '▣ ' if g.is_system else ''
            fold = ''
            if self._nested_enabled() and self._group_has_children(g.group_id):
                fold = '▸ ' if self._group_is_collapsed(g.group_id) else '▾ '
            indent = '　' * depth + ('└ ' if depth > 0 else '')
            itm = QListWidgetItem('{}{}{}{}{}  ({})'.format(indent, mark, star, fold, g.name, cnt))
            itm.setData(Qt.UserRole, g.group_id)
            self.group_list.addItem(itm)

        target = ALL_MARK if self.current_group_id is None else self.current_group_id
        for i in range(self.group_list.count()):
            if self.group_list.item(i).data(Qt.UserRole) == target:
                self.group_list.setCurrentRow(i)
                break
        self.group_list.blockSignals(False)

    def _find_group(self, gid):
        return next((g for g in self.groups if g.group_id == gid), None)

    def _group_name(self, gid):
        g = self._find_group(gid)
        return g.name if g else UNC_NAME

    def _on_group_clicked(self, cur, prev):
        if cur is None:
            return
        gid = cur.data(Qt.UserRole)
        self.current_group_id = None if gid == ALL_MARK else gid
        self.rebuild_model()

    def _on_group_double_clicked(self, item):
        gid = item.data(Qt.UserRole)
        if gid == ALL_MARK:
            return
        if self._nested_enabled() and self._group_has_children(gid):
            self._toggle_group_collapse(gid)

    #选择图片

    def selected_items(self):
        out = []
        for ix in self.grid_view.selectedIndexes():
            it = ix.data(Qt.UserRole)
            if isinstance(it, EmojiItem) and id(it) not in [id(x) for x in out]:
                out.append(it)
        return out

    def _single_selected(self):
        items = self.selected_items()
        if not items:
            QMessageBox.warning(self, '提示', '请先选择一张图片')
            return None
        if len(items) > 1:
            QMessageBox.warning(self, '提示', '请只选择一张图片')
            return None
        return items[0]

    #图片预览

    def preview_item(self, item):
        self._preview_item = item
        self.preview.show_path(abs_emoji(item.path), item.name)
        group_txt = UNC_NAME if item.group_id == UNC_ID else self._group_name(item.group_id)
        fav = ' · ★收藏' if item.is_favorite else ''
        self.preview_name.setText('{}  ·  {} {}'.format(item.name, group_txt, fav))

    def preview_selected(self):
        it = self._single_selected()
        if it:
            self.preview_item(it)

    def _on_grid_double(self, ix):
        it = ix.data(Qt.UserRole)
        if isinstance(it, EmojiItem):
            self.preview_item(it)

    #图片命名

    def rename_selected(self):
        items = self.selected_items()
        if not items:
            QMessageBox.warning(self, '提示', '请先选择图片')
            return
        if len(items) == 1:
            it = items[0]
            name, ok = QInputDialog.getText(self, '重命名', '新名称：', text=it.name)
            if not ok:
                return
            name = name.strip()
            if not name:
                QMessageBox.warning(self, '提示', '名称不能为空')
                return
            it.name = name
            self.save_data()
            self.rebuild_model()
            self.preview_item(it)
            return
        dlg = BatchRenameDialog(items, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        changed = False
        for it, new_name in zip(items, dlg.names()):
            new_name = (new_name or '').strip() or '未命名'
            if new_name != it.name:
                it.name = new_name
                changed = True
        if changed:
            self.save_data()
            self.rebuild_model()

    #收藏图片

    def toggle_favorite_selected(self):
        items = self.selected_items()
        if not items:
            QMessageBox.warning(self, '提示', '请先选择图片')
            return
        for it in items:
            it.is_favorite = not it.is_favorite
        self.save_data()
        self.rebuild_model()

    def _set_favorite_group(self, group):
        group.is_favorite = not group.is_favorite
        self.save_data()
        self.refresh_group_list()

    #导入图片

    def import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择图片', '', IMPORT_FILTER)
        if not paths:
            return
        default_gid = self.current_group_id or UNC_ID
        dlg = ImportDialog(paths, self.groups, default_gid, self, self._nested_enabled())
        if dlg.exec_() != QDialog.Accepted:
            return
        jobs, gid = dlg.result()

        self.progress_dialog = QProgressDialog('准备导入…', '取消', 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowTitle('导入中')

        self.import_thread = ImportThread(jobs, gid, list(self.items), self,
                                          self._dedup_enabled(), self._dedup_similarity())
        self.import_thread.progress.connect(self._on_import_progress)
        self.import_thread.result.connect(self._on_import_done)
        self.import_thread.start()

    def _on_import_progress(self, n, total, phase):
        #保留对进度框的引用,避免自动关闭时回调再次访问已清空的对象
        dlg = self.progress_dialog
        if dlg is None:
            return
        try:
            dlg.setMaximum(max(1, total))
            dlg.setValue(n)
            dlg.setLabelText('{}：{}/{}'.format(phase, n, total))
        except RuntimeError:
            self.progress_dialog = None

    def _on_import_done(self, new_dicts, skips):
        try:
            if self.import_thread:
                self.import_thread.progress.disconnect()
        except Exception:
            pass
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        new_items = [EmojiItem.from_dict(d) for d in new_dicts]
        self.items.extend(new_items)
        self.save_data()
        self.refresh_group_list()
        self.rebuild_model()
        if self._preload_enabled():
            self._start_thumbnails(new_items)

        headline = getattr(self, '_import_headline', None)
        self._import_headline = None
        if headline:
            msg = '{},共 {} 张图片'.format(headline, len(new_items))
        else:
            msg = '成功导入 {} 张图片'.format(len(new_items))
        if skips:
            msg += '\n\n' + '\n'.join(skips)
        QMessageBox.information(self, '导入完成', msg)

    #导出图片

    def export_flow(self):
        items = self.selected_items()
        if not items:
            if self.current_group_id is not None:
                group = self._find_group(self.current_group_id)
                label = group.name if group else UNC_NAME
                if QMessageBox.question(self, '导出', '未选中图片,是否导出父集「{}」的全部图片？'.format(label)) != QMessageBox.Yes:
                    return
                items = [it for it in self.items if it.group_id == self.current_group_id]
            else:
                if QMessageBox.question(self, '导出', '未选中图片,是否导出全部图片？') != QMessageBox.Yes:
                    return
                items = list(self.items)
        if not items:
            QMessageBox.warning(self, '提示', '没有可导出的图片')
            return

        dest = QFileDialog.getExistingDirectory(self, '选择导出目录')
        if not dest:
            return

        self.progress_dialog = QProgressDialog('正在导出…', '取消', 0, len(items), self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowTitle('导出中')

        self.export_thread = ExportThread(items, dest, self, self._encrypt_enabled())
        self.export_thread.progress.connect(self._on_export_progress)
        self.export_thread.finished_ok.connect(self._on_export_done)
        self.export_thread.error.connect(self._on_export_error)
        self.export_thread.start()

    def _on_export_progress(self, n, total):
        dlg = self.progress_dialog
        if dlg is None:
            return
        try:
            dlg.setValue(n)
        except RuntimeError:
            self.progress_dialog = None

    def _on_export_done(self, dest_dir, total):
        try:
            if self.export_thread:
                self.export_thread.progress.disconnect()
        except Exception:
            pass
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        QMessageBox.information(self, '导出成功', '已导出 {} 张图片至：\n{}'.format(total, dest_dir))

    def _on_export_error(self, err):
        try:
            if self.export_thread:
                self.export_thread.progress.disconnect()
        except Exception:
            pass
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        QMessageBox.critical(self, '导出失败', str(err))

    #移动图片

    def _move_selected_menu(self):
        items = self.selected_items()
        if not items:
            QMessageBox.warning(self, '提示', '请先选择图片')
            return
        menu = QMenu(self)
        for g, _depth in self._display_groups():
            act = menu.addAction(self._group_display_name(g))
            act.setData(g.group_id)
            act.triggered.connect(lambda _checked, gid=g.group_id: self.move_items(items, gid))
        menu.exec_(QCursor.pos())

    def move_items(self, items, target_gid):
        if target_gid is None:
            return
        changed = [it for it in items if it.group_id != target_gid]
        if not changed:
            QMessageBox.information(self, '提示', '所选图片已在目标父集中')
            return
        if QMessageBox.question(self, '确认移动',
                                '将 {} 张图片移动到父集「{}」？'.format(len(changed), self._group_name(target_gid))) != QMessageBox.Yes:
            return
        for it in changed:
            it.group_id = target_gid
        self.save_data()
        self.refresh_group_list()
        self.rebuild_model()

    #删除图片

    def delete_selected(self):
        items = self.selected_items()
        if not items:
            QMessageBox.warning(self, '提示', '请先选择图片')
            return
        favs = [it for it in items if it.is_favorite]
        if favs:
            QMessageBox.warning(self, '已收藏', '其中有 {} 张图片已收藏,请先取消收藏再删除 '.format(len(favs)))
            return
        names = '、'.join(it.name for it in items[:5])
        if len(items) > 5:
            names += '…'
        if QMessageBox.question(self, '确认删除',
                                '确定删除 {} 张图片吗？\n{}\n（将从磁盘删除文件,不可恢复）'.format(len(items), names)) != QMessageBox.Yes:
            return
        ids = {id(it) for it in items}
        for it in items:
            p = abs_emoji(it.path)
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.items = [it for it in self.items if id(it) not in ids]
        self.save_data()
        self.refresh_group_list()
        self.rebuild_model()
        self.preview.clear()
        self.preview_name.setText('选择表情包进行预览')
        self._preview_item = None

    #管理父集

    def create_group(self, parent_id=None, title='新建父集'):
        name, ok = QInputDialog.getText(self, title, '父集名称：')
        if not ok:
            return None
        name = name.strip()
        if not name:
            QMessageBox.warning(self, '提示', '名称不能为空')
            return None
        if any(g.name == name for g in self.groups):
            QMessageBox.warning(self, '提示', '已存在同名父集')
            return None
        gid = hashlib.md5('{}{}'.format(name, time.time()).encode()).hexdigest()[:12]
        color = GROUP_COLORS[len(self.groups) % len(GROUP_COLORS)]
        group = EmojiGroup(gid, name, color=color,
                           priority=self._next_group_priority(parent_id), parent_id=parent_id)
        self.groups.append(group)
        self.save_data()
        self.current_group_id = gid
        self.refresh_group_list()
        self.rebuild_model()
        return group

    def _create_child_group(self, parent_group):
        if parent_group.is_system:
            QMessageBox.warning(self, '提示', '系统保留父集「未分类」不能包含子父集')
            return
        self.create_group(parent_id=parent_group.group_id,
                          title='新建子父集（属于「{}」）'.format(parent_group.name))

    def _can_reparent(self, group, new_parent_id):
        if new_parent_id is None:
            return True
        if new_parent_id == group.group_id:
            return False
        seen = {group.group_id}
        cur = self._find_group(new_parent_id)
        while cur is not None:
            if cur.group_id in seen:
                return False
            seen.add(cur.group_id)
            cur = self._find_group(cur.parent_id) if cur.parent_id else None
        return True

    def _reparent_group(self, group, new_parent_id):
        if new_parent_id:
            p = self._find_group(new_parent_id)
            if p is None or p.is_system:
                QMessageBox.warning(self, '提示', '不能移动到系统保留父集')
                return
        if not self._can_reparent(group, new_parent_id):
            QMessageBox.warning(self, '提示', '不能移动到该父集（会形成循环依赖）')
            return
        group.parent_id = new_parent_id or None
        group.priority = self._next_group_priority(new_parent_id)
        self._normalize_priority()
        self.save_data()
        self.refresh_group_list()

    def _move_group_priority(self, group, delta):
        if group.is_system:
            return
        siblings = self._siblings(group)
        idx = next((i for i, g in enumerate(siblings) if g.group_id == group.group_id), None)
        if idx is None:
            return
        j = idx + delta
        if j < 0 or j >= len(siblings):
            return
        siblings[idx], siblings[j] = siblings[j], siblings[idx]
        for i, g in enumerate(siblings):
            g.priority = i
        self.save_data()
        self.refresh_group_list()

    @staticmethod
    def _sanitize_name(name):
        return _safe_filename(name, '父集')

    def _unique_zip_name(self, seen, base, ext, suffix='', k=0):
        cand = '{}{}{}'.format(base, ext, suffix) if k == 0 else '{}_{}{}{}'.format(base, k, ext, suffix)
        return cand if cand not in seen else self._unique_zip_name(seen, base, ext, suffix, k + 1)

    def export_group_zip(self, group):
        items = [it for it in self.items if it.group_id == group.group_id]
        if not items:
            QMessageBox.information(self, '提示', '该父集没有图片,无法导出压缩包')
            return
        default_name = '{}_父集.zip'.format(self._sanitize_name(group.name))
        dest, _ = QFileDialog.getSaveFileName(self, '导出父集压缩包', default_name, 'ZIP 压缩包 (*.zip)')
        if not dest:
            return
        if not dest.lower().endswith('.zip'):
            dest += '.zip'
        try:
            self._write_group_zip(dest, group, items, self._encrypt_enabled())
        except Exception as e:
            QMessageBox.critical(self, '导出失败', str(e))
            return
        kind = '（已加密混淆）' if self._encrypt_enabled() else ''
        QMessageBox.information(self, '导出成功', '已将父集「{}」{}导出为：\n{}'.format(group.name, kind, dest))

    def _write_group_zip(self, dest, group, items, encrypt=False):
        manifest = {
            'schema': PACK_SCHEMA,
            'group': {
                'name': group.name, 'group_id': group.group_id,
                'color': group.color, 'is_favorite': group.is_favorite,
            },
            'items': [],
            'encrypted': bool(encrypt),
        }
        seen_names = set()
        suffix = '.prtsenc' if encrypt else ''
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('pack.mcmeta', json.dumps({
                'pack': {'pack_format': 1, 'description': 'PRTS 表情包父集 · {}'.format(group.name)}
            }, ensure_ascii=False, indent=2))
            for it in items:
                src = abs_emoji(it.path)
                if not src or not os.path.isfile(src):
                    continue
                base = self._sanitize_name(os.path.splitext(os.path.basename(os.path.abspath(src)))[0]) or 'emoji'
                ext = os.path.splitext(os.path.abspath(src))[1].lower() or '.png'
                fname = self._unique_zip_name(seen_names, base, ext, suffix)
                seen_names.add(fname)
                arcname = 'images/' + fname
                if encrypt:
                    zf.writestr(arcname, crypto.encrypt_path(src, it.name))
                else:
                    zf.write(src, arcname)
                manifest['items'].append({
                    'name': it.name, 'filename': arcname,
                    'tags': list(it.tags), 'is_favorite': it.is_favorite,
                    'timestamp': it.timestamp,
                })
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))

    def import_group_zip(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入父集压缩包', '', 'ZIP 压缩包 (*.zip)')
        if not path:
            return
        try:
            new_items, skipped, meta = self._load_group_zip(path)
        except Exception as e:
            QMessageBox.critical(self, '导入失败', '格式不正确,导入失败：\n{}'.format(e))
            return
        group_name = self._unique_group_name(
            (meta.get('name') or self._sanitize_name(
                os.path.splitext(os.path.basename(path))[0])).strip() or '导入父集')
        gid = hashlib.md5('{}{}'.format(group_name, time.time()).encode()).hexdigest()[:12]
        group = EmojiGroup(gid, group_name, color=GROUP_COLORS[len(self.groups) % len(GROUP_COLORS)],
                           is_favorite=bool(meta.get('is_favorite', False)),
                           priority=self._next_group_priority(None))
        self.groups.append(group)
        for it in new_items:
            it.group_id = gid
        self.items.extend(new_items)
        self.save_data()
        self.current_group_id = gid
        self.refresh_group_list()
        self.rebuild_model()
        if self._preload_enabled():
            self._start_thumbnails(new_items)
        msg = '成功导入父集「{}」,共 {} 张图片'.format(group_name, len(new_items))
        if skipped:
            msg += '\n\n' + '\n'.join(skipped)
        QMessageBox.information(self, '导入完成', msg)

    def _load_group_zip(self, path):
        if not zipfile.is_zipfile(path):
            raise ValueError('不是有效的 ZIP 压缩包')
        with zipfile.ZipFile(path, 'r') as zf:
            names = set(zf.namelist())
            if 'pack.mcmeta' not in names or 'manifest.json' not in names:
                raise ValueError('缺少 pack.mcmeta 或 manifest.json（非 PRTS 父集压缩包格式）')
            try:
                manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
            except Exception:
                raise ValueError('manifest.json 解析失败')
            if not isinstance(manifest, dict) or manifest.get('schema') != PACK_SCHEMA:
                raise ValueError('manifest.json 的 schema 不匹配（期望 {}）'.format(PACK_SCHEMA))
            if not isinstance(manifest.get('group'), dict) or not manifest['group'].get('name'):
                raise ValueError('manifest.json 缺少父集名称')
            if not isinstance(manifest.get('items'), list):
                raise ValueError('manifest.json 缺少 items 列表')
            dedup_enabled = self._dedup_enabled()
            existing = set()
            if dedup_enabled:
                for it in self.items:
                    p = abs_emoji(it.path)
                    h = _sha1(p) if (p and os.path.isfile(p)) else None
                    if h:
                        existing.add(h)
            new_items = []
            skipped = []
            for entry in manifest['items']:
                fname = entry.get('filename')
                if not fname or fname not in names:
                    skipped.append('「{}」缺失文件,已跳过'.format(entry.get('name', '?')))
                    continue
                data = zf.read(fname)
                name = entry.get('name') or '未命名'
                ext = os.path.splitext(fname)[1].lower() or '.png'
                if crypto.is_encrypted_blob(data):
                    dec = crypto.decrypt_blob(data)
                    if dec is None:
                        skipped.append('「{}」无法解密,已跳过'.format(name))
                        continue
                    name = dec[0] or name
                    ext = dec[1] or ext
                    data = dec[2]
                h = hashlib.sha1(data).hexdigest()
                if dedup_enabled and h in existing:
                    skipped.append('「{}」重复,已跳过'.format(name))
                    continue
                existing.add(h)
                oname = _unique_stored_name(ext)
                with open(os.path.join(EMOJI_DIR, oname), 'wb') as f:
                    f.write(data)
                new_items.append(EmojiItem(oname, name, UNC_ID,
                                           list(entry.get('tags') or []), entry.get('timestamp'),
                                           None, bool(entry.get('is_favorite', False))))
            return new_items, skipped, manifest['group']

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择文件夹（批量导入其中图片）')
        if not folder:
            return
        found = []
        for root, _dirs, files in os.walk(folder):
            for fn in sorted(files):
                if fn.lower().endswith(IMG_EXTS) or crypto.is_encrypted_path(fn):
                    found.append(os.path.join(root, fn))
        if not found:
            QMessageBox.warning(self, '提示', '该文件夹中没有找到图片文件')
            return

        prev_gid = self.current_group_id
        group_name = self._unique_group_name(os.path.basename(os.path.abspath(folder)).strip() or '文件夹导入')
        gid = hashlib.md5('{}{}'.format(group_name, time.time()).encode()).hexdigest()[:12]
        group = EmojiGroup(gid, group_name, color=GROUP_COLORS[len(self.groups) % len(GROUP_COLORS)],
                           priority=self._next_group_priority(None))
        self.groups.append(group)
        self.save_data()
        self.current_group_id = gid
        self.refresh_group_list()
        self.rebuild_model()

        dlg = ImportDialog(found, self.groups, gid, self, self._nested_enabled())
        if dlg.exec_() != QDialog.Accepted:
            self.groups = [g for g in self.groups if g.group_id != gid]
            self.current_group_id = prev_gid
            self.save_data()
            self.refresh_group_list()
            self.rebuild_model()
            return

        jobs, target_gid = dlg.result()
        if target_gid != gid and not any(it.group_id == gid for it in self.items):
            self.groups = [g for g in self.groups if g.group_id != gid]
            self.current_group_id = target_gid
            self.save_data()
            self.refresh_group_list()

        self._import_headline = '已复制文件夹图片到父集「{}」'.format(self._group_name(target_gid))

        self.progress_dialog = QProgressDialog('准备导入…', '取消', 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowTitle('导入中')
        self.import_thread = ImportThread(jobs, target_gid, list(self.items), self,
                                          self._dedup_enabled(), self._dedup_similarity())
        self.import_thread.progress.connect(self._on_import_progress)
        self.import_thread.result.connect(self._on_import_done)
        self.import_thread.start()

    def _on_group_menu(self, pos):
        item = self.group_list.itemAt(pos)
        if item is None:
            return
        gid = item.data(Qt.UserRole)
        if gid == ALL_MARK:
            return
        group = self._find_group(gid)
        if group is None:
            return
        menu = QMenu(self)
        cover_act = menu.addAction('设置封面')
        clean_act = menu.addAction('检测并删除无法读取的图片')
        if group.is_system:
            rename_act = fav_act = del_act = None
            up_act = down_act = child_act = None
            detach_act = None
        else:
            rename_act = menu.addAction('重命名父集')
            fav_act = menu.addAction('取消收藏' if group.is_favorite else '收藏父集')
            del_act = menu.addAction('删除父集')
            menu.addSeparator()
            up_act = menu.addAction('↑ 上移')
            down_act = menu.addAction('↓ 下移')
            child_act = menu.addAction('新建子父集') if self._nested_enabled() else None
            detach_act = None
            if self._nested_enabled():
                reparent_menu = menu.addMenu('移动到父集（更改所属）')
                for g in self.groups:
                    if g.is_system or g.group_id == group.group_id:
                        continue
                    if not self._can_reparent(group, g.group_id):
                        continue
                    act = reparent_menu.addAction(self._group_display_name(g))
                    act.setData(g.group_id)
                    act.triggered.connect(lambda _c, gid=g.group_id: self._reparent_group(group, gid))
                if group.parent_id:
                    detach_act = menu.addAction('移出父集')
        menu.addSeparator()
        fold_act = None
        if self._nested_enabled() and self._group_has_children(group.group_id):
            fold_act = menu.addAction('展开子父集' if self._group_is_collapsed(group.group_id) else '折叠子父集')
        add_type_act = None
        remove_type_act = None
        if not group.is_system:
            add_type_act = menu.addAction('添加 tag 类型')
            remove_type_act = menu.addAction('移除某类型 tag（本父集全部图片）')
        list_types_act = menu.addAction('列出所有 tag 类型')
        menu.addSeparator()
        export_act = menu.addAction('导出为压缩包 (.zip)')
        chosen = menu.exec_(self.group_list.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == cover_act:
            self.set_group_cover(group)
        elif chosen == clean_act:
            self._clean_broken_in_group(group)
        elif rename_act is not None and chosen == rename_act:
            self.rename_group(group)
        elif fav_act is not None and chosen == fav_act:
            self._set_favorite_group(group)
        elif del_act is not None and chosen == del_act:
            self.delete_group(group)
        elif up_act is not None and chosen == up_act:
            self._move_group_priority(group, -1)
        elif down_act is not None and chosen == down_act:
            self._move_group_priority(group, 1)
        elif child_act is not None and chosen == child_act:
            self._create_child_group(group)
        elif detach_act is not None and chosen == detach_act:
            self._reparent_group(group, None)
        elif fold_act is not None and chosen == fold_act:
            self._toggle_group_collapse(group.group_id)
        elif add_type_act is not None and chosen == add_type_act:
            self._add_group_tag_type(group)
        elif remove_type_act is not None and chosen == remove_type_act:
            self._remove_tag_type_from_group(group)
        elif chosen == list_types_act:
            self._list_tag_types()
        elif chosen == export_act:
            self.export_group_zip(group)

    #tag 类型 / 批量移除

    def _add_group_tag_type(self, group):
        name, ok = QInputDialog.getText(self, '添加 tag 类型', '该父集的 tag 类型名（如：角色 / 来源 / 情绪）：')
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if ':' in name:
            QMessageBox.warning(self, '提示', '类型名不能包含冒号（:）')
            return
        if name in (group.tag_types or []):
            QMessageBox.warning(self, '提示', '该类型已存在')
            return
        group.tag_types = list(group.tag_types or []) + [name]
        self.save_data()
        self.refresh_group_list()
        QMessageBox.information(self, '完成', '已为该父集添加 tag 类型「{}」'.format(name))

    def _remove_tag_type_from_group(self, group):
        items = [it for it in self.items if it.group_id == group.group_id]
        types = sorted({_tag_type(t) for it in items for t in it.tags})
        if not types:
            QMessageBox.information(self, '提示', '该父集的图片没有任何 tag')
            return
        choice, ok = QInputDialog.getItem(self, '移除某类型 tag',
                                          '选择要移除的 tag 类型（将删除该父集全部图片中此类型的 tag）：',
                                          types, 0, False)
        if not ok:
            return
        count = 0
        for it in items:
            keep = [t for t in it.tags if _tag_type(t) != choice]
            removed = len(it.tags) - len(keep)
            if removed:
                it.tags = keep
                count += removed
        if not count:
            QMessageBox.information(self, '提示', '没有找到该类型的 tag')
            return
        if choice in (group.tag_types or []):
            group.tag_types = [x for x in group.tag_types if x != choice]
        self.save_data()
        self.rebuild_model()
        self.refresh_group_list()
        QMessageBox.information(self, '完成', '已移除 {} 个 tag（类型「{}」）'.format(count, choice))

    def _list_tag_types(self):
        from collections import Counter
        counts = Counter(_tag_type(t) for it in self.items for t in it.tags)
        lines = []
        for tp in self.all_tag_types():
            lines.append('· {}（{} 个 tag）'.format(tp, counts.get(tp, 0)))
        if counts.get('未分类', 0):
            lines.append('· 未分类（{} 个 tag）'.format(counts['未分类']))
        if not lines:
            lines.append('（尚无任何 tag）')
        QMessageBox.information(self, '所有 tag 类型', '\n'.join(lines))

    def _add_item_tag(self, items):
        options = ['无类型', '新建类型…'] + self.all_tag_types()
        choice, ok = QInputDialog.getItem(self, '添加 tag', '选择 tag 类型：', options, 0, False)
        if not ok:
            return
        type_name = None
        if choice == '新建类型…':
            tn, ok2 = QInputDialog.getText(self, '新建类型', '类型名：')
            if not ok2:
                return
            tn = tn.strip()
            if not tn:
                return
            if ':' in tn:
                QMessageBox.warning(self, '提示', '类型名不能包含冒号（:）')
                return
            type_name = tn
        elif choice != '无类型':
            type_name = choice
        value, ok3 = QInputDialog.getText(self, '添加 tag', 'tag 内容：')
        if not ok3:
            return
        value = value.strip()
        if not value:
            return
        tag = '{}:{}'.format(type_name, value) if type_name else value
        changed = False
        for it in items:
            if tag not in it.tags:
                it.tags = list(it.tags) + [tag]
                changed = True
        if changed:
            self.save_data()
            self.rebuild_model()

    def _remove_item_tags(self, items, tag):
        changed = False
        for it in items:
            if tag in it.tags:
                it.tags = [t for t in it.tags if t != tag]
                changed = True
        if not changed:
            return
        tt = _tag_type(tag)
        if tt != '未分类':
            still = any(tt == _tag_type(t) for x in self.items for t in x.tags)
            if not still:
                for g in self.groups:
                    if tt in (g.tag_types or []):
                        g.tag_types = [x for x in g.tag_types if x != tt]
        self.save_data()
        self.rebuild_model()
        self.refresh_group_list()

    #全局 tag / tag 类型管理（设置中调用）

    def remove_tag_everywhere(self, tag, dialog=None):
        parent = dialog if dialog is not None else self
        count = 0
        for it in self.items:
            if tag in it.tags:
                it.tags = [t for t in it.tags if t != tag]
                count += 1
        if not count:
            QMessageBox.information(parent, '提示', '未找到 tag「{}」'.format(tag))
            return
        tt = _tag_type(tag)
        if tt != '未分类':
            still = any(tt == _tag_type(t) for x in self.items for t in x.tags)
            if not still:
                for g in self.groups:
                    if tt in (g.tag_types or []):
                        g.tag_types = [x for x in g.tag_types if x != tt]
        self.save_data()
        self.rebuild_model()
        self.refresh_group_list()
        QMessageBox.information(parent, '完成',
                                '已从 {} 个表情中移除 tag「{}」'.format(count, tag))

    def remove_tag_type_everywhere(self, type_name, dialog=None):
        parent = dialog if dialog is not None else self
        count = 0
        for it in self.items:
            keep = [t for t in it.tags if _tag_type(t) != type_name]
            removed = len(it.tags) - len(keep)
            if removed:
                it.tags = keep
                count += removed
        if not count:
            QMessageBox.information(parent, '提示', '没有找到类型「{}」的 tag'.format(type_name))
            return
        for g in self.groups:
            if type_name in (g.tag_types or []):
                g.tag_types = [x for x in g.tag_types if x != type_name]
        self.save_data()
        self.rebuild_model()
        self.refresh_group_list()
        QMessageBox.information(parent, '完成',
                                '已删除 {} 个 tag（类型「{}」）'.format(count, type_name))

    def rename_group(self, group):
        if group.is_system:
            return
        name, ok = QInputDialog.getText(self, '重命名父集', '新名称：', text=group.name)
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, '提示', '名称不能为空')
            return
        if any(g.name == name and g.group_id != group.group_id for g in self.groups):
            QMessageBox.warning(self, '提示', '已存在同名父集')
            return
        group.name = name
        self.save_data()
        self.refresh_group_list()
        self.rebuild_model()

    def set_group_cover(self, group):
        path, _ = QFileDialog.getOpenFileName(self, '选择封面图片', '', IMG_FILTER)
        if not path:
            return
        ext = os.path.splitext(path)[1].lower() or '.png'
        cover_name = '{}_cover{}'.format(group.group_id, ext)
        cover_abs = os.path.join(GROUP_DIR, cover_name)
        shutil.copy2(path, cover_abs)
        group.cover_path = rel_root(cover_abs)
        self.save_data()
        self.refresh_group_list()

    def _group_unreadable_items(self, group):
        bad = []
        for it in self.items:
            if it.group_id != group.group_id:
                continue
            p = abs_emoji(it.path)
            if not p or not os.path.isfile(p):
                bad.append(it)
                continue
            try:
                if not QImageReader(p).canRead():
                    bad.append(it)
            except Exception:
                bad.append(it)
        return bad

    def _clean_broken_in_group(self, group):
        bad = self._group_unreadable_items(group)
        if not bad:
            QMessageBox.information(self, '检测完成', '父集「{}」中没有无法读取的图片'.format(group.name))
            return
        target = [it for it in bad if not it.is_favorite]
        fav_n = len(bad) - len(target)
        if not target:
            QMessageBox.warning(self, '提示', '检测到 {} 张无法读取的图片,但均已收藏,本次不处理'.format(len(bad)))
            return
        names = '、'.join(it.name for it in target[:5])
        if len(target) > 5:
            names += '…'
        text = '检测到 {} 张无法读取的图片,是否一键删除？\n{}'.format(len(target), names)
        if fav_n:
            text += '\n（另 {} 张已收藏,将跳过）'.format(fav_n)
        if QMessageBox.question(self, '删除无法读取的图片', text) != QMessageBox.Yes:
            return
        ids = {id(it) for it in target}
        for it in target:
            p = abs_emoji(it.path)
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.items = [it for it in self.items if id(it) not in ids]
        self.save_data()
        self.refresh_group_list()
        self.rebuild_model()
        if self._preview_item is not None and any(id(it) == id(self._preview_item) for it in target):
            self.preview.clear()
            self.preview_name.setText('选择表情包进行预览')
            self._preview_item = None
        QMessageBox.information(self, '完成', '已删除 {} 张无法读取的图片'.format(len(target)))

    def delete_group(self, group):
        if group.is_system:
            return
        if group.is_favorite:
            QMessageBox.warning(self, '已收藏', '该父集已收藏,请先取消收藏再删除 ')
            return
        children = [it for it in self.items if it.group_id == group.group_id]

        box = QMessageBox(self)
        box.setWindowTitle('删除父集')
        box.setText('删除父集「{}」？\n包含 {} 张图片,请选择处理方式：'.format(group.name, len(children)))
        btn_a = box.addButton('连同子集一起删除', QMessageBox.DestructiveRole)
        btn_b = box.addButton('仅删除父集,保留子集', QMessageBox.AcceptRole)
        box.addButton('取消', QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()

        if clicked is btn_a:
            favs = [it for it in children if it.is_favorite]
            if favs:
                QMessageBox.warning(self, '已收藏', '其中有 {} 张已收藏图片,已取消删除 '.format(len(favs)))
                return
            ids = {id(it) for it in children}
            for it in children:
                p = abs_emoji(it.path)
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            self.items = [it for it in self.items if id(it) not in ids]
        elif clicked is btn_b:
            for it in children:
                it.group_id = UNC_ID
        else:
            return

        self.groups = [g for g in self.groups if g.group_id != group.group_id]
        if self.current_group_id == group.group_id:
            self.current_group_id = None
        self.save_data()
        self.refresh_group_list()
        self.rebuild_model()

    #图片右键菜单

    def _selected_or_item(self, item):
        sel = self.selected_items()
        if any(id(x) == id(item) for x in sel):
            return sel
        return [item]

    def _on_grid_menu(self, pos):
        index = self.grid_view.indexAt(pos)
        if not index.isValid():
            return
        item = index.data(Qt.UserRole)
        if not isinstance(item, EmojiItem):
            return
        target_items = self._selected_or_item(item)

        menu = QMenu(self)
        prev = menu.addAction('预览')
        ren = menu.addAction('重命名')
        fav = menu.addAction('取消收藏' if item.is_favorite else '收藏')
        tag_act = menu.addAction('添加 tag')
        rmtag_menu = menu.addMenu('移除 tag')
        tags = sorted({t for it in target_items for t in it.tags})
        if tags:
            for t in tags:
                a = rmtag_menu.addAction(t)
                a.triggered.connect(lambda _c, tg=t: self._remove_item_tags(target_items, tg))
        else:
            rmtag_menu.setEnabled(False)
        move_menu = menu.addMenu('移动到父集')
        for g, _depth in self._display_groups():
            mact = move_menu.addAction(self._group_display_name(g))
            mact.setData(g.group_id)
            mact.triggered.connect(lambda _c, gid=g.group_id: self.move_items(target_items, gid))
        sim_act = menu.addAction('相似度查找（本父集内）') if self._similar_search_enabled() else None
        delex = menu.addAction('删除')

        chosen = menu.exec_(self.grid_view.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == prev:
            self.preview_item(item)
        elif chosen == ren:
            self.grid_view.setCurrentIndex(index)
            self.rename_selected()
        elif chosen == fav:
            item.is_favorite = not item.is_favorite
            self.save_data()
            self.rebuild_model()
        elif chosen == tag_act:
            self._add_item_tag(target_items)
        elif sim_act is not None and chosen == sim_act:
            self._similarity_search(item)
        elif chosen == delex:
            self.grid_view.setCurrentIndex(index)
            self.delete_selected()

    #帮助和快捷键

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F1:
            self.show_help()
        elif event.key() == Qt.Key_Delete:
            self.delete_selected()
        else:
            super().keyPressEvent(event)

    def show_help(self):
        QMessageBox.information(self, '帮助', HELP_TEXT)
