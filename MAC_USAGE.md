# macOS 开发运行

当前桌面入口可以在 Apple 芯片 Mac 上使用 pywebview 的 Cocoa 后端启动。Mac 只需要安装项目依赖和 Python 3.12；不复用 Windows 的 `node_modules`、虚拟环境或构建缓存。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python desktop.py
```

Mac 依赖 `pyobjc` 提供 Cocoa 提示框。如果系统没有安装该依赖，启动错误仍会写入应用日志，提示框会退回日志记录。Mac 当前不增加跨进程单实例锁；Windows 的互斥锁、EdgeChromium 后端和原有启动流程保持不变。

先运行自动检查：

```bash
.venv/bin/python -m unittest -v
```

首次运行时，系统可能要求允许文件夹访问；选择炉次目录后再执行真实样本验收。Mac 窗口、文件夹选择器、CSV 导出和 Office 文件打开需要在实际设备上逐项确认。当前项目仍以 Windows x64 发布配置为准，未提供 macOS 签名或安装包配置。
