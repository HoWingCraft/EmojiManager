import sys
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from config import load_settings, anim_enabled
from theme import apply_theme


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName('PRTS · 管理终端')
    app.setStyle('Fusion')

    cfg = load_settings()
    apply_theme(app, cfg['palette'])

    from app import EmojiManagerSystem
    window = EmojiManagerSystem(app, cfg)

    splash = None
    if anim_enabled(cfg, 'splash'):
        from splash import PRTSSplash
        splash = PRTSSplash(cfg['palette'])

        def show_main():
            window.show()
            window.play_entrance()
            if splash is not None:
                splash.close()

        splash.finished.connect(show_main)
        splash.show()
    else:
        window.show()
        window.play_entrance()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()