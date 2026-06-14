键盘模拟输入工具 (Keyboard Typer)
===================================
将文本通过模拟键盘敲击的方式逐字输入到当前焦点窗口，
用于规避部分网站/应用不允许直接粘贴（Ctrl+V）的限制。

特性:
  - 使用 Windows SendInput API，纯 Python 实现，零外部依赖
  - 完整支持 Unicode 字符（中文、日文、Emoji 等）
  - 正确处理换行→回车、制表符→Tab、退格等特殊键
  - 可配置打字速度、倒计时、每次击键间隔
  - 支持剪贴板 / 命令行参数 / 文件 三种输入源

用法:
  python keyboard_typer.py                  # 输入剪贴板中的文本
  python keyboard_typer.py -t "要输入的文字"  # 输入指定文字
  python keyboard_typer.py -f 文件.txt       # 输入文件内容
  python keyboard_typer.py -d 5             # 5 秒倒计时
  python keyboard_typer.py -s 0.03          # 每个字符间隔 0.03 秒 (默认)
  python keyboard_typer.py --show-text      # 开始前显示将要输入的内容
  python keyboard_typer.py -d 3 -t "你好世界" --no-newline
