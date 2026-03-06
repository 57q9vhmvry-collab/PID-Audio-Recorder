# PID Audio Recorder (Windows)

纯 Python 的 Windows 进程定向录音工具，支持：

- 按 PID 录制特定进程输出音频
- PySide6 GUI（轻拟真 Mac 风格）
- 开始/停止、暂停/继续、计时、实时电平显示
- 自动检测目标进程退出并停止
- WAV 自动转 MP3（内置 `imageio-ffmpeg` 调用）
- GitHub Releases 版本检查与安装包更新

## 环境要求

- Windows 10 2004+ 或 Windows 11
- Python 3.11+

## 安装

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 运行

```powershell
python src/app.py
```

## 测试

```powershell
pytest -q
```

## 打包

```powershell
python scripts/build_release.py
```

## 发布

- 版本号统一定义在 `src/core/version.py`
- 创建正式版本时，推送 tag：`v1.0.0`
- GitHub Actions 会自动构建安装包并上传到 GitHub Releases
