from PyQt5.QtGui import QColor, QPalette

_QSS = """\
QMainWindow { background-color: %(bg)s; }
QWidget { color: %(text)s;
    font-family: 'Consolas','Microsoft YaHei UI','Microsoft YaHei',monospace; font-size: 13px; }
QFrame#panel { background-color: %(bg_panel)s; border: 1px solid %(border)s; border-radius: 0; }
QLabel#header { color: %(white)s; font-size: 14px; font-weight: 600; }
QLabel#sectionTitle { color: %(text_dim)s; font-size: 12px; }
QLabel#hint { color: %(text_faint)s; font-size: 12px; }
QToolButton#collapseHeader { background: transparent; border: none; color: %(text_dim)s;
    font-size: 12px; padding: 8px 10px; }
QPushButton { background-color: %(bg_card)s; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 0; padding: 6px 12px; }
QPushButton:hover { background-color: %(accent)s; color: %(black)s; border-color: %(accent)s; }
QPushButton:pressed { background-color: %(white)s; color: %(black)s; }
QPushButton:disabled { color: %(text_faint)s; border-color: %(border)s; background-color: %(bg_input)s; }
QPushButton#primary { background-color: %(accent)s; color: %(black)s; font-weight: 600; border: 1px solid %(accent)s; }
QPushButton#primary:hover { background-color: %(white)s; color: %(black)s; }
QPushButton#danger { color: %(danger)s; border: 1px solid %(border)s; background-color: %(bg_card)s; }
QPushButton#danger:hover { background-color: %(danger)s; color: %(black)s; border-color: %(danger)s; }
QLineEdit, QComboBox, QSpinBox { background-color: %(bg_input)s; color: %(text)s;
    border: 1px solid %(border)s; border-radius: 0; padding: 5px 8px; }
QLineEdit:focus, QComboBox:focus { border-color: %(accent)s; }
QComboBox QAbstractItemView { background-color: %(bg_panel)s; color: %(text)s;
    border: 1px solid %(border)s; selection-background-color: %(accent)s; selection-color: %(black)s; }
QListWidget { background-color: transparent; border: none; outline: none; }
QListWidget::item { color: %(text_dim)s; padding: 7px 10px; border-left: 2px solid transparent; }
QListWidget::item:hover { background-color: %(bg_card)s; color: %(text)s; }
QListWidget::item:selected { background-color: %(bg_card)s; color: %(white)s; border-left: 2px solid %(accent)s; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: %(border_soft)s; border-radius: 2px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 9px; }
QScrollBar::handle:horizontal { background: %(border_soft)s; border-radius: 2px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMenu { background-color: %(bg_panel)s; border: 1px solid %(border)s; }
QMenu::item { padding: 6px 22px; color: %(text)s; }
QMenu::item:selected { background-color: %(accent)s; color: %(black)s; }
QMenu::separator { height: 1px; background: %(border_soft)s; margin: 4px 8px; }
QMessageBox, QDialog, QInputDialog { background-color: %(bg_panel)s; }
QProgressDialog { background-color: %(bg_panel)s; }
QProgressBar { background-color: %(bg_input)s; border: 1px solid %(border)s; border-radius: 0;
    text-align: center; color: %(text)s; }
QProgressBar::chunk { background-color: %(accent)s; }
QTableWidget { background-color: %(bg_input)s; gridline-color: %(border)s; border: 1px solid %(border)s;
    alternate-background-color: %(bg_panel)s; }
QHeaderView::section { background-color: %(bg_card)s; color: %(text_dim)s; border: none; padding: 4px; }
QCheckBox { color: %(text_dim)s; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid %(border)s; border-radius: 0;
    background: %(bg_input)s; }
QCheckBox::indicator:checked { background-color: %(accent)s; border-color: %(accent)s; }
QToolTip { background-color: %(bg_deep)s; color: %(text)s; border: 1px solid %(border_soft)s; }
QSplitter::handle { background-color: %(bg_deep)s; }
QStatusBar { background-color: %(black)s; color: %(text_dim)s; border-top: 1px solid %(border)s; }
QTabBar::tab { background: %(bg_card)s; color: %(text_dim)s; padding: 6px 14px; border: 1px solid %(border)s; }
QTabBar::tab:selected { color: %(text_hi)s; border-bottom: 2px solid %(accent)s; }
"""


def build_qss(palette):
    return _QSS % palette


def apply_theme(app, palette):
    app.setStyleSheet(build_qss(palette))
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(palette['bg']))
    pal.setColor(QPalette.WindowText, QColor(palette['text']))
    pal.setColor(QPalette.Base, QColor(palette['bg_input']))
    pal.setColor(QPalette.AlternateBase, QColor(palette['bg_panel']))
    pal.setColor(QPalette.Text, QColor(palette['text']))
    pal.setColor(QPalette.Button, QColor(palette['bg_card']))
    pal.setColor(QPalette.ButtonText, QColor(palette['text']))
    pal.setColor(QPalette.Highlight, QColor(palette['accent']))
    pal.setColor(QPalette.HighlightedText, QColor(palette['black']))
    pal.setColor(QPalette.ToolTipBase, QColor(palette['bg_deep']))
    pal.setColor(QPalette.ToolTipText, QColor(palette['text']))
    pal.setColor(QPalette.Link, QColor(palette['white']))
    app.setPalette(pal)