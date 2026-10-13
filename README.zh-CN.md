<p align="center"><img src="docs/images/logo.png" width="110" alt="Baton Mi"></p>

# Baton Mi · 小米蓝牙语音遥控器 → Linux 桌面遥控器

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Linux%20%2F%20GNOME%20Wayland-blue)
![Remote](https://img.shields.io/badge/remote-Xiaomi%20BLE%20Voice%20Remote%20(2717%3A32b8)-orange)
![托盘应用](https://img.shields.io/badge/%E6%89%98%E7%9B%98%E5%BA%94%E7%94%A8-Flutter-02569B)

[English](README.md) · **中文说明**

**躺在沙发上 vibe coding。** Baton Mi 把一只便宜的小米蓝牙语音遥控器变成 AI 编程 agent 的免手控制器：
**按住说话**（建议用小米 **MiMo** 做语音识别）、**一按打断**模型、**不碰键盘**就能在 agent / 编辑器 / 浏览器之间切窗口。

> 专为 **GNOME / Wayland** 而写 —— 在它上面，常见的按键注入工具（`wtype`、`xdotool`）根本不可用，
> 所以本项目自带一个约 250 行的 **uinput 注入垫片**（30 ms/次，对比"每次新建虚拟设备"的 2.1 s/次）。

```
遥控器按键 ──BLE HID──► mi-remote（动作引擎）──► uinput 注入垫片 ──► 桌面
遥控器麦克风 ──BLE ATVV──► IMA ADPCM 解码 ──► 小米 MiMo ASR ──► 剪贴板 ──► Ctrl+Shift+V 上屏
```

## AI agent 循环，全在一只遥控器上

写代码时反复做的动作，以及对应的按键：

| 我想 | 按 | 会发生什么 |
|---|---|---|
| 口述下一句 prompt | **按住语音** | 按住说话 → **小米 MiMo**（`mimo-v2.5-asr`）→ 自动粘到焦点窗口。不用切输入法 |
| 让模型立刻停下 | **短按电源** | `Esc`，即时生效：没有双击判定，连按也不会误触 |
| 解开卡住的 agent | **短按 TV** | `Ctrl+B`（OpenCode：把阻塞的工具丢到后台） |
| 在 agent / 编辑器 / 浏览器之间跳 | **长按菜单** → `←`/`→` | 真正的切换器，遍历**所有**窗口（`Alt+Tab` 只能在最近两个之间跳） |
| 打开 agent 或编辑器 | **双击主页** / **双击 TV** | 启动 OpenCode / Cursor，已打开则**拉前台**而不是重复开窗 |
| 改 prompt 里的错字 | **短按返回** | `Backspace`，即时（连按可快速删） |
| 翻看长回答 | **音量 ±** | `PageUp` / `PageDown` |
| 确认它还活着 | 瞄一眼托盘 | 🟢 / 🟡 / 🔴，断连时弹桌面通知 |

手不用离开遥控器；麦克风在遥控器上，所以离电脑多远都能口述，不必守在桌前。

## 特性

- 🎙️ **按住语音键说话**，松手把文字自动上屏。**建议用小米 MiMo**（`mimo-v2.5-asr`）：电视遥控麦是远场小麦，云端识别率比本机 Paraformer 稳；转写大约 0.7–0.9 秒、不占本机几百 MB 内存。按量 **¥0.5 / 音频小时**（一句 5 秒约 ¥0.0007）；Token Plan 按 **30M Credits / 音频小时**。Key 写在本机 `system/cloud-asr.json`。详细换算见 [`docs/指南.md` §1.3.1](docs/指南.md)
- ✍️ **可选：转写后再整理一层**（`cloud-asr.json` 的 `cleanup` 段，**默认关**）。小米 ASR 的提示词在网关注入、改不了，所以「口语 → 书面 prompt」由转写后的第二道对话模型（`mimo-v2.6-flash`）完成：纠错别字、补标点、去口水词，代码 / 路径 / 术语原样保留；**任何失败都回退原文**。默认不开是因为它把上屏从 ~1 秒拉到 ~2 秒（冷启动第一句 ~7 秒）；想用就设 `"cleanup": {"enabled": true}`。
- ⏹️ **一键打断**：电源键 = `Esc`，即时、无双击延迟，连按也安全
- 🚀 **一键启动**：双击主页 → OpenCode；双击 TV → Cursor；已打开则**直接拉前台**（不重复开窗）
- 🪟 **窗口切换器**：长按菜单后 `←/→` 可遍历**所有**窗口（原生 `Alt+Tab` 只能在两个窗口间跳）
- ⌨️ **13 键随手可用**：删除、Enter、方向键、`Esc`、`PageUp/PageDown`、`Ctrl+B`…（见下方键位表）
- 🖥️ **托盘状态**：🟢 正常 / 🟡 按键可用但语音未连 / 🔴 异常；**断连时弹通知**（"按任意键唤醒"）
- 🔌 **开机自启**：遥控器服务 + 注入守护 + 托盘，登录即用
- 🧩 **纯脚本可复现**：`install.sh` 幂等部署；所有踩坑与验证过程都写在 `docs/` 里

## 快速开始

前置条件：

- **GNOME + Wayland**（本项目就是为它写的；X11 下另有更简单的方案）
- 已装 [goodtiger/mi-remote-linux](https://github.com/goodtiger/mi-remote-linux) 并配对好遥控器（见 `docs/指南.md` 步骤 1–5）
- Flutter（仅托盘应用需要，3.2x+）

```bash
git clone https://github.com/chenweidu666/APP-Baton.git
cd Baton
./install.sh          # 部署脚本 / udev 规则 / systemd 服务 / 托盘应用 + 开机自启
mi-remote doctor      # 自检（应为 12 通过 / 1 警告 / 0 失败）
```

> `install.sh` 是**幂等**的：内容已一致的文件会跳过（udev 规则已最新时不需要 sudo）。
> 需要 sudo 但没有终端时：`SUDO_PASS=你的密码 ./install.sh`。

## 键位（默认，可通过 `system/mapping.json` 改）

![默认键位图](docs/images/keymap.png)


| 按键 | 短按 | 长按（≥350ms） | 双击 |
|---|---|---|---|
| 语音 | 按住口述 → 松手上屏 | — | — |
| OK | `Enter` | **`Ctrl+Enter`**（OpenCode 网页版发送） | — |
| 方向键 | 方向键 | — | — |
| 返回 | **删除一个字符**（即时，连按快速删） | — | — |
| 主页 | — | — | 打开 **OpenCode** |
| 菜单 | `Ctrl+P` | **窗口切换器** | — |
| TV | `Ctrl+B`（OpenCode 把阻塞的工具转后台） | — | 打开 **Cursor** |
| 音量 ＋/－ | `PageUp` / `PageDown` | — | — |
| 电源 | **`Esc`**（打断 AI / 关弹窗） | 关闭当前窗口 | — |

完整表 + 每个键的取舍理由 + 工程记录（原理、复现步骤、11 条踩坑）+ 路线图：**[`docs/指南.md`](docs/指南.md)**。

## 托盘应用（`app/`）

Flutter 写的**纯托盘**（无窗口、无弹窗），点图标就是一个小菜单：

```
状态：遥控器已连接，一切正常
────────────────────────────
蓝牙：已连接   按键节点：/dev/input/event12   服务：运行中 ／ 注入：运行中
电量：84%
────────────────────────────
键位速查 ▸        ← 实时读 mapping.json 生成，键位改了它自动跟着变
────────────────────────────
重新检测 / 重启遥控服务 / 重连蓝牙 / 查看服务日志 / 打开文档 / 退出
```

| 图标 | 含义 |
|---|---|
| 🟢 绿 | 蓝牙 + 按键节点 + 服务全部正常 |
| 🟡 黄 | 按键可用，但蓝牙语音未连（语音键用不了） |
| 🔴 红 | 服务未运行 / 找不到按键节点（按键与语音都不会生效） |

断连/恢复会弹桌面通知；托盘随登录自启。开发时：`cd app && ./run.sh`。

## 为什么需要"自写注入垫片"

GNOME（Mutter）**不实现** `wtype` 依赖的虚拟键盘协议，`xdotool` 也只认 X11，而 Ubuntu 的 `ydotool` 包缺守护进程
（上游依赖仓库已失效，编译不通）。所以本项目自带一个约 250 行的 uinput 垫片：

| 方案 | GNOME Wayland | 实测 |
|---|---|---|
| `wtype` | ❌ 合成器不支持 | — |
| `xdotool` | ❌ 拿不到窗口 | — |
| Ubuntu 的 `ydotool` | ⚠️ 缺 `ydotoold` | — |
| **本项目的 uinput 垫片** | ✅ 常驻守护进程 + socket | **30 ms/次**（对比每次新建设备 2.1 s/次） |

## 目录结构

```
├── app/         托盘应用（Flutter，纯托盘）
├── tools/       维护工具（键位图、logo 生成）—— 不安装
├── scripts/     mi-remote 调用的小工具 → 安装到 ~/.local/bin
│                （注入垫片 / 窗口切换器 / 窗口聚焦 / 启动器 / 托盘包装）
├── system/      udev 规则 · systemd 单元 · 键位配置 · 桌面图标 · 本机补丁
├── tests/       行为仿真脚本（灌合成事件，不产生真实按键）
├── docs/        键位表 · 适配流程 · 需求池
└── install.sh   一键部署（幂等）

> 键位图/脚本说明：`tools/gen-keymap-image.py`（由配置生成键位图）、`tools/make-logo.py`（生成 logo）、`scripts/window-switcher`（窗口切换器）等，详见各文件头部注释。
```

## 已知限制

- 只适配这一款遥控器（VID:PID `2717:32b8`）；设备名会变（`小米蓝牙语音遥控器` ↔ `MI RC`）
- BLE 遥控器**同时只能连一个主机**：拿去控电视后，回电脑需要按「菜单 + HOME」重新配对
- 语音识别**建议用小米 MiMo**（`mimo-v2.5-asr`，按量约 ¥0.5 / 音频小时）；本分支不分发、不加载本地模型
- 窗口聚焦/切换器依赖 GNOME 扩展 **`winrects@cua`**（未启用时会退化成"每次都新开窗口"，不影响其它功能）
- 托盘应用在 Wayland 下不能设 `skipTaskbar`（会触发 `libwayland-client` 段错误），因此采用"窗口永不显示"的实现

## 常见问题

| 现象 | 解决 |
|---|---|
| 按遥控器没反应 | 看托盘图标颜色；蓝牙断开时按任意键唤醒，或托盘菜单 →「重连蓝牙（自愈）」 |
| **遥控器睡着后不自动连回**（一直"连接超时"） | 已修：`baton-bt-watchdog.service` 在掉线超过宽限期后自动连回（坑 13）。手动排查 `baton-bt-watchdog --once` |
| **重启后按键和语音全失效**（蓝牙显示已连接、但没有按键节点） | BlueZ 的 HID-over-GATT 没挂上（坑 12）。登录时 `baton-recover.service` 会自动修复；也可手动 `baton-bt-recover`，或托盘 →「重连蓝牙（自愈）」 |
| 按键节点找不到 / 权限不足 | `bash install.sh` 重装 udev 规则（或 `getfacl /dev/input/eventN` 看 ACL） |
| 语音识别结果没上屏 | 终端里粘贴是 `Ctrl+Shift+V`（服务参数已指定）；文本仍在剪贴板 |
| 启动程序时是"新开窗口"不是切前台 | 检查 GNOME 扩展 `winrects@cua` 是否启用 |
| 删着删着把 AI 打断了 | 旧版问题（连按返回被判双击 = `Esc`）；现已去掉返回双击，`Esc` 在**电源短按** |
| 命令 `mi-remote` 找不到 | 官方安装器的 shebang bug，见 `docs/指南.md` 坑 2 |

## 环境说明（重要）

`docs/` 与 `system/` 里保留了作者的真实环境信息，**换机器请自行替换**：

- `/home/chenwei/...` → 你自己的家目录（`install.sh` 会自动替换 `$HOME`）
- `F0:2B:18:87:37:B7` → 你的遥控器 MAC（`bluetoothctl devices` 查看）
- `~/Workspace`、`~/Linux-App/05-Baton` → 示例目录（启动器目标写死在 `system/mapping.json` 里）

## 致谢

- [goodtiger/mi-remote-linux](https://github.com/goodtiger/mi-remote-linux) —— 本项目的底座
  （GATT/ATVV 连接、按键解码、动作引擎、语音管道，MIT）。**本仓库还打包了它的两个产物**：官方安装器、
  以及 `mapping_engine.py` 的原始版与打补丁版（按 MIT 要求注明出处）。
- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx)（Apache-2.0）—— 上游 mi-remote 仍自带；本分支不加载
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[python-evdev](https://github.com/gvalkov/python-evdev)、
  [NumPy](https://numpy.org) —— 备用识别引擎、按键事件读取、音频缓冲
- [Flutter](https://flutter.dev) + [tray_manager](https://pub.dev/packages/tray_manager) + GNOME AppIndicator —— 托盘应用
- `winrects@cua`（CUA 的 GNOME 扩展）—— 用于列出/激活窗口的 DBus 接口
- [playerctl](https://github.com/altdesktop/playerctl)、[libnotify](https://gitlab.gnome.org/GNOME/libnotify)、
  [PipeWire](https://pipewire.org) —— 媒体键、桌面通知、音量
- [cairosvg](https://github.com/Kozea/CairoSVG) —— 把生成的键位图从 SVG 转 PNG

**完整清单（用了什么、为什么、许可证、以及哪些是随仓库分发的）：[`THIRD_PARTY.md`](THIRD_PARTY.md)** —— 一并致谢 🙏

