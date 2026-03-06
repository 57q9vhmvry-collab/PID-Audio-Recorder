from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


COLORS = {
    "canvas": "#e9edf3",
    "window": "#f6f7fb",
    "surface": "#ffffff",
    "surface_soft": "#f7f9fc",
    "line": "#d7ddea",
    "line_soft": "#e5e9f2",
    "text": "#1f2430",
    "muted": "#6b7485",
    "accent": "#1677ff",
    "accent_hover": "#0f67df",
    "accent_soft": "#e7f0ff",
    "danger": "#ff5f57",
    "warn": "#ffbd2e",
    "ok": "#28c840",
}


def create_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["canvas"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["surface_soft"]))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    return palette


def build_stylesheet(font_family: str | None = None) -> str:
    preferred_font = (font_family or "SF Pro Text").replace('"', '\\"')
    return f"""
    QMainWindow {{
        background: transparent;
    }}

    QWidget {{
        font-family: "{preferred_font}", "PingFang SC", "Helvetica Neue", sans-serif;
        color: {COLORS["text"]};
        background: {COLORS["canvas"]};
    }}

    #OuterShell {{
        background: transparent;
    }}

    QLabel {{
        background: transparent;
    }}

    #RootContainer {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 {COLORS["window"]},
            stop: 1 #edf2f8
        );
        border: none;
        border-radius: 20px;
    }}

    #TitleBar {{
        background: rgba(248, 249, 253, 0.94);
        border-bottom: 1px solid {COLORS["line_soft"]};
        border-top-left-radius: 20px;
        border-top-right-radius: 20px;
    }}

    #TitleBox {{
        background: transparent;
    }}

    #TitleLabel {{
        color: {COLORS["text"]};
        font-size: 13px;
        font-weight: 600;
    }}

    #SubtitleLabel {{
        color: {COLORS["muted"]};
        font-size: 11px;
    }}

    #PanelCard {{
        background: {COLORS["surface"]};
        border: 1px solid {COLORS["line_soft"]};
        border-radius: 14px;
    }}

    #SectionTitle {{
        font-size: 15px;
        font-weight: 650;
    }}

    #StatusLabel {{
        padding: 11px 16px;
        border-top: 1px solid {COLORS["line_soft"]};
        color: {COLORS["muted"]};
        background: rgba(248, 250, 253, 0.9);
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
    }}

    #StatusChip {{
        background: {COLORS["accent_soft"]};
        color: {COLORS["accent_hover"]};
        border: 1px solid #c8dbff;
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
    }}

    QPushButton#TitleActionButton {{
        min-height: 28px;
        max-height: 28px;
        padding: 4px 12px;
        border-radius: 9px;
        border: 1px solid #d8e2f0;
        background: rgba(255, 255, 255, 0.85);
        color: #425067;
        font-size: 12px;
        font-weight: 600;
    }}

    QPushButton#TitleActionButton:hover {{
        background: #f4f8ff;
        border-color: #bfd1ee;
    }}

    QPushButton#TitleActionButton:pressed {{
        background: #e8f0ff;
    }}

    QPushButton#TitleActionButton:disabled {{
        color: #9aa3b3;
        background: #f1f4f9;
        border-color: #d8e0ea;
    }}

    QLabel#SettingLabel {{
        font-size: 12px;
        color: #687488;
        font-weight: 600;
        letter-spacing: 0.2px;
    }}

    QLineEdit, QTableWidget, QProgressBar {{
        background: {COLORS["surface"]};
        border: 1px solid {COLORS["line"]};
        border-radius: 9px;
        padding: 6px 9px;
        selection-background-color: #dbe9ff;
    }}

    QComboBox#FormatCombo,
    QComboBox#SaveModeCombo {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 #fbfdff,
            stop: 1 #f3f7ff
        );
        border: 1px solid #cfd7e6;
        border-radius: 9px;
        padding: 3px 10px;
        padding-right: 30px;
        min-height: 30px;
        max-height: 30px;
        font-size: 14px;
        font-weight: 620;
        color: {COLORS["text"]};
    }}

    QComboBox#SaveModeCombo {{
        font-size: 13px;
        font-weight: 580;
        color: #253044;
    }}

    QComboBox#FormatCombo:hover,
    QComboBox#SaveModeCombo:hover {{
        border: 1px solid #b6c3d8;
        background: #fafdff;
    }}

    QComboBox#FormatCombo:focus,
    QComboBox#SaveModeCombo:focus {{
        border: 1px solid #8fb6fd;
        background: #ffffff;
    }}

    QComboBox#FormatCombo:disabled,
    QComboBox#SaveModeCombo:disabled {{
        color: #8a95a8;
        border: 1px solid #d5deec;
        background: #eff3fa;
    }}

    QComboBox#FormatCombo:on,
    QComboBox#SaveModeCombo:on {{
        border: 1px solid #8fb6fd;
        background: #ffffff;
    }}

    QComboBox#FormatCombo::drop-down,
    QComboBox#SaveModeCombo::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 26px;
        border-left: 1px solid #dce4f1;
        border-top-right-radius: 9px;
        border-bottom-right-radius: 9px;
        background: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 #f8fbff,
            stop: 1 #edf3fc
        );
    }}

    QListView#SettingComboPopup {{
        border: 1px solid #c5d4ea;
        border-radius: 10px;
        background: #ffffff;
        padding: 6px;
        color: {COLORS["text"]};
        outline: 0;
        show-decoration-selected: 1;
    }}

    QListView#SettingComboPopup::item {{
        min-height: 24px;
        border-radius: 6px;
        padding: 3px 10px;
        margin: 1px 0;
    }}

    QListView#SettingComboPopup::item:hover {{
        background: #f1f6ff;
    }}

    QListView#SettingComboPopup::item:selected {{
        background: #e4efff;
        color: {COLORS["text"]};
    }}

    QLineEdit:focus {{
        border: 1px solid #97bdfd;
        background: #fbfdff;
    }}

    QTableWidget {{
        gridline-color: #f0f2f7;
        outline: 0;
    }}

    QHeaderView::section {{
        background: #f5f7fb;
        border: none;
        border-bottom: 1px solid {COLORS["line_soft"]};
        padding: 8px 6px;
        color: #6d7687;
        font-size: 11px;
        font-weight: 600;
    }}

    QTableWidget::item {{
        border: none;
        padding: 5px 4px;
    }}

    QTableWidget::item:selected {{
        color: {COLORS["text"]};
        background: #e4efff;
    }}

    QPushButton {{
        background: #fdfdff;
        border: 1px solid {COLORS["line"]};
        border-radius: 9px;
        padding: 7px 14px;
    }}

    QPushButton:hover {{
        background: #f3f7ff;
        border-color: #bdc7d8;
    }}

    QPushButton:pressed {{
        background: #eaf1ff;
    }}

    QPushButton:disabled {{
        color: #9aa3b3;
        background: #f1f3f7;
    }}

    QPushButton#PrimaryButton {{
        color: white;
        border: none;
        border-radius: 10px;
        padding: 8px 18px;
        min-height: 36px;
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 {COLORS["accent"]},
            stop: 1 #0b61d6
        );
        font-weight: 600;
    }}

    QPushButton#PrimaryButton:hover {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 #338cff,
            stop: 1 {COLORS["accent_hover"]}
        );
    }}

    QPushButton#PrimaryButton:pressed {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 #0f67df,
            stop: 1 #0a56be
        );
    }}

    QPushButton#PrimaryButton:disabled {{
        color: #dfe9ff;
        background: #8ab8fa;
    }}

    QPushButton#PauseButton {{
        min-height: 36px;
        padding: 8px 16px;
        font-weight: 600;
        color: #9f7e24;
        border: 1px solid #f0cd7a;
        background: #fff5de;
    }}

    QPushButton#PauseButton:hover {{
        background: #ffefcb;
        border-color: #e7bf65;
    }}

    QPushButton#PauseButton:pressed {{
        background: #ffe4a6;
    }}

    QPushButton#PauseButton[paused="true"] {{
        color: #1f7a3c;
        border: 1px solid #90d6a5;
        background: #e6f7ec;
    }}

    QPushButton#PauseButton[paused="true"]:hover {{
        background: #d8f2e2;
        border-color: #79c88f;
    }}

    QPushButton#PauseButton:disabled {{
        color: #9aa3b3;
        border: 1px solid #d5dbe6;
        background: #f4f6fa;
    }}

    QPushButton#StopButton {{
        min-height: 36px;
        padding: 8px 16px;
        font-weight: 600;
        color: #b03a35;
        border: 1px solid #efb2ae;
        background: #ffeceb;
    }}

    QPushButton#StopButton:hover {{
        background: #ffdfdd;
        border-color: #e99893;
    }}

    QPushButton#StopButton:pressed {{
        background: #ffcfc9;
    }}

    QPushButton#StopButton:disabled {{
        color: #9aa3b3;
        border: 1px solid #d5dbe6;
        background: #f4f6fa;
    }}

    QProgressBar {{
        min-height: 13px;
        max-height: 13px;
        border-radius: 6px;
        text-align: center;
        background: #edf1f7;
    }}

    QProgressBar::chunk {{
        border-radius: 6px;
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #30c66f,
            stop: 1 #1d84ff
        );
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical {{
        background: #cfd6e3;
        min-height: 26px;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #b8c2d3;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
        height: 0;
    }}
    """
