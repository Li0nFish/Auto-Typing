#!/usr/bin/env python3
"""
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
"""

import argparse
import ctypes
import sys
import time
import os
from ctypes import wintypes

# 修复 Windows 终端 UTF-8 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ============================================================
# 常量
# ============================================================

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# 虚拟键码 (Virtual-Key Codes)
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SPACE = 0x20

# 特殊字符映射: 字符 -> (虚拟键码, 是否需要 Shift)
# 某些符号无法通过 KEYEVENTF_UNICODE 可靠发送，改用虚拟键码
SPECIAL_CHAR_MAP = {
    # 这些字符也可以通过 KEYEVENTF_UNICODE 发送，但保留此映射以备不时之需
}

# ============================================================
# Windows API 结构体定义
# ============================================================


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),        # 虚拟键码
        ("wScan", wintypes.WORD),       # 硬件扫描码 / Unicode 码点
        ("dwFlags", wintypes.DWORD),    # 标志位
        ("time", wintypes.DWORD),       # 时间戳 (0 = 系统默认)
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),  # 附加信息
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class DUMMYUNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", DUMMYUNION),
    ]


# ============================================================
# 键盘输入核心函数
# ============================================================


def _send_input(inputs: list[INPUT]) -> int:
    """调用 SendInput API 发送输入事件。返回成功发送的事件数。"""
    count = len(inputs)
    arr = (INPUT * count)(*inputs)
    return ctypes.windll.user32.SendInput(count, arr, ctypes.sizeof(INPUT))


def send_key_down(vk_code: int, scan_code: int = 0, flags: int = 0):
    """发送按键按下事件。"""
    ki = KEYBDINPUT(
        wVk=vk_code,
        wScan=scan_code,
        dwFlags=flags,
        time=0,
        dwExtraInfo=None,
    )
    inp = INPUT(type=INPUT_KEYBOARD, union=DUMMYUNION(ki=ki))
    _send_input([inp])


def send_key_up(vk_code: int, scan_code: int = 0, flags: int = 0):
    """发送按键释放事件。"""
    ki = KEYBDINPUT(
        wVk=vk_code,
        wScan=scan_code,
        dwFlags=flags | KEYEVENTF_KEYUP,
        time=0,
        dwExtraInfo=None,
    )
    inp = INPUT(type=INPUT_KEYBOARD, union=DUMMYUNION(ki=ki))
    _send_input([inp])


def send_vk_press(vk_code: int):
    """按下并释放一个虚拟键（如 Enter、Tab、Backspace）。"""
    send_key_down(vk_code)
    time.sleep(0.005)  # 极短间隔，确保操作系统处理
    send_key_up(vk_code)


def send_unicode_char(ch: str):
    """
    使用 KEYEVENTF_UNICODE 发送一个 Unicode 字符。
    支持所有 BMP 字符（包括中文、日文、韩文等）。
    对于代理对（如 Emoji > U+FFFF），会尝试逐码点发送。
    """
    code_point = ord(ch)

    # Key down (带 KEYEVENTF_UNICODE 标志)
    ki_down = KEYBDINPUT(
        wVk=0,                       # wVk 必须为 0
        wScan=code_point,            # wScan 存放 Unicode 码点
        dwFlags=KEYEVENTF_UNICODE,   # 标记为 Unicode 输入
        time=0,
        dwExtraInfo=None,
    )
    inp_down = INPUT(type=INPUT_KEYBOARD, union=DUMMYUNION(ki=ki_down))

    # Key up
    ki_up = KEYBDINPUT(
        wVk=0,
        wScan=code_point,
        dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
        time=0,
        dwExtraInfo=None,
    )
    inp_up = INPUT(type=INPUT_KEYBOARD, union=DUMMYUNION(ki=ki_up))

    _send_input([inp_down, inp_up])


def type_character(ch: str):
    """
    根据字符类型选择合适的发送方式:
    - 换行 (\n)     → Enter 键
    - 回车 (\r)     → Enter 键
    - 制表 (\t)     → Tab 键
    - 退格 (\b)     → Backspace 键
    - 其他字符      → Unicode 输入
    """
    if ch == '\n' or ch == '\r':
        send_vk_press(VK_RETURN)
    elif ch == '\t':
        send_vk_press(VK_TAB)
    elif ch == '\b':
        send_vk_press(VK_BACK)
    else:
        send_unicode_char(ch)


# ============================================================
# 剪贴板操作 - 修复 64 位 Windows 上 ctypes 返回值截断问题
# ============================================================

# 必须声明 restype，否则 ctypes 默认将返回值当作 32 位 int，
# 在 64 位系统上会截断指针/句柄，导致 access violation。
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE

_kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HANDLE
_kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
_kernel32.GlobalFree.restype = wintypes.HANDLE


def get_clipboard_text() -> str:
    """
    从 Windows 剪贴板获取文本（Unicode 格式）。
    纯 Windows API 实现，无需 pyperclip 等第三方库。
    """
    # 尝试打开剪贴板
    if not _user32.OpenClipboard(0):
        print("⚠ 无法打开剪贴板（可能被其他程序占用）", file=sys.stderr)
        return ""

    try:
        # CF_UNICODETEXT = 13
        handle = _user32.GetClipboardData(13)
        if not handle:
            print("⚠ 剪贴板中没有文本内容", file=sys.stderr)
            return ""

        # 锁定全局内存并读取
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            print("⚠ 无法锁定剪贴板内存", file=sys.stderr)
            return ""

        try:
            # 从宽字符指针读取字符串
            text = ctypes.wstring_at(ptr)
            return text
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


def set_clipboard_text(text: str):
    """将文本写入 Windows 剪贴板。"""
    if not _user32.OpenClipboard(0):
        print("⚠ 无法打开剪贴板", file=sys.stderr)
        return

    try:
        _user32.EmptyClipboard()

        # 分配全局内存
        # GMEM_MOVEABLE = 0x0002, GMEM_ZEROINIT = 0x0040
        size_bytes = (len(text) + 1) * 2  # UTF-16 + null terminator
        handle = _kernel32.GlobalAlloc(0x0042, size_bytes)
        if not handle:
            print("⚠ 无法分配剪贴板内存", file=sys.stderr)
            return

        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            _kernel32.GlobalFree(handle)
            return

        try:
            # 写入宽字符串
            ctypes.memmove(ptr, text, len(text) * 2)
            # null terminator 已由 GMEM_ZEROINIT 提供
        finally:
            _kernel32.GlobalUnlock(handle)

        _user32.SetClipboardData(13, handle)  # CF_UNICODETEXT
        # 注意: SetClipboardData 后不应释放 handle，系统拥有它
    finally:
        _user32.CloseClipboard()


# ============================================================
# 主输入逻辑
# ============================================================


def countdown(seconds: int):
    """倒计时，给用户时间将光标定位到目标输入框。"""
    print(f"\n{'='*50}")
    print(f"⏳ 请将光标定位到目标输入框...")
    print(f"{'='*50}")

    for remaining in range(seconds, 0, -1):
        # 在同一行覆盖输出
        print(f"\r  >> 倒计时: {remaining} 秒 ", end="", flush=True)
        time.sleep(1)

    print(f"\r  >> 开始输入!          ")
    print(f"{'='*50}\n")


def type_text(
    text: str,
    delay: float = 0.03,
    no_newline: bool = False,
    progress: bool = True,
):
    """
    逐字符模拟键盘输入文本。

    参数:
        text:      要输入的文本
        delay:     每个字符之间的延迟（秒）
        no_newline: 是否忽略换行符（转为空格）
        progress:  是否显示进度
    """
    if not text:
        print("⚠ 没有要输入的内容", file=sys.stderr)
        return

    # 预处理文本
    processed = text
    if no_newline:
        # 将换行替换为空格，合并连续空白
        processed = processed.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
        # 合并多个连续空格
        while '  ' in processed:
            processed = processed.replace('  ', ' ')

    # 处理 Windows 风格的 \r\n → 统一为单个 \n
    processed = processed.replace('\r\n', '\n').replace('\r', '\n')

    total = len(processed)
    typed = 0

    print(f"⌨  准备输入 {total} 个字符...")
    if delay > 0:
        print(f"⏱  字符间隔: {delay:.3f} 秒")
    print()

    try:
        for i, ch in enumerate(processed):
            type_character(ch)

            typed += 1

            # 进度显示
            if progress and total > 50 and (i + 1) % 50 == 0:
                pct = (i + 1) / total * 100
                print(f"\r  进度: {i + 1}/{total} ({pct:.1f}%)", end="", flush=True)

            # 字符间延迟
            if delay > 0:
                time.sleep(delay)

    except KeyboardInterrupt:
        print(f"\n\n⚠ 用户中断! 已输入 {typed}/{total} 个字符")
        return

    if progress and total > 50:
        print(f"\r  进度: {total}/{total} (100.0%)")
    print(f"\n✅ 输入完成! 共 {typed} 个字符\n")


# ============================================================
# 命令行接口
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="键盘模拟输入工具 — 将文本通过模拟键盘敲击逐字输入",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                        从剪贴板读取并输入
  %(prog)s -t "Hello World"       输入指定文字
  %(prog)s -f input.txt           输入文件内容
  %(prog)s -d 5                   5秒倒计时后输入剪贴板内容
  %(prog)s -s 0.05 -d 3          0.05秒/字，3秒倒计时
  %(prog)s -t "你好世界" --no-newline  输入但不含换行
  %(prog)s --show-text            先显示内容再确认输入
        """,
    )

    # 输入源（三选一）
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "-t", "--text",
        type=str,
        metavar="TEXT",
        help="直接指定要输入的文字",
    )
    input_group.add_argument(
        "-f", "--file",
        type=str,
        metavar="FILE",
        help="从文件读取要输入的文字",
    )

    # 选项
    parser.add_argument(
        "-d", "--delay-before",
        type=int,
        default=3,
        metavar="SECONDS",
        help="开始输入前的倒计时秒数 (默认: 3)",
    )
    parser.add_argument(
        "-s", "--speed",
        type=float,
        default=0.03,
        metavar="SECONDS",
        help="每个字符之间的延迟秒数 (默认: 0.03, 即约33字/秒)",
    )
    parser.add_argument(
        "--no-newline",
        action="store_true",
        help="忽略换行符（将其替换为空格）",
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="输入前在终端显示将要输入的内容",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="不显示进度信息",
    )
    parser.add_argument(
        "--no-delay",
        action="store_true",
        help="字符间无延迟（最快速度）",
    )

    args = parser.parse_args()

    # ---------- 获取输入文本 ----------
    text = ""

    if args.text:
        text = args.text
        source = "命令行参数"
    elif args.file:
        filepath = args.file
        if not os.path.isfile(filepath):
            print(f"❌ 文件不存在: {filepath}", file=sys.stderr)
            sys.exit(1)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            source = f"文件: {filepath}"
        except Exception as e:
            print(f"❌ 读取文件失败: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 默认从剪贴板读取
        text = get_clipboard_text()
        if not text:
            print("❌ 剪贴板为空或无法读取", file=sys.stderr)
            print("   提示: 先复制文字，或使用 -t / -f 参数指定输入源", file=sys.stderr)
            sys.exit(1)
        source = "剪贴板"

    # ---------- 显示信息 ----------
    print(f"\n{'█'*50}")
    print(f"  键盘模拟输入工具")
    print(f"{'█'*50}")
    print(f"  输入源:   {source}")
    print(f"  字符数:   {len(text)}")
    print(f"  倒计时:   {args.delay_before} 秒")
    if args.no_delay:
        print(f"  打字速度: 最快（无延迟）")
    else:
        print(f"  打字速度: {args.speed:.3f} 秒/字 (~{1/args.speed:.0f} 字/秒)")
    if args.no_newline:
        print(f"  换行处理: 替换为空格")
    print(f"{'█'*50}")

    # 可选：显示文本内容
    if args.show_text:
        print(f"\n📄 将要输入的内容:\n{'-'*40}")
        preview = text[:500]
        if len(text) > 500:
            preview += f"\n... (共 {len(text)} 个字符，仅显示前 500 个)"
        print(preview)
        print(f"{'-'*40}")

        # 确认
        confirm = input("\n❓ 确认输入? [Y/n]: ").strip().lower()
        if confirm and confirm not in ("y", "yes"):
            print("已取消")
            sys.exit(0)

    # ---------- 倒计时 ----------
    if args.delay_before > 0:
        countdown(args.delay_before)

    # ---------- 模拟输入 ----------
    speed = 0 if args.no_delay else args.speed
    type_text(
        text,
        delay=speed,
        no_newline=args.no_newline,
        progress=not args.no_progress,
    )


if __name__ == "__main__":
    main()
