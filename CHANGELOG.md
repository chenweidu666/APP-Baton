# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构；日期为本地时间。
版本号未正式发布前统一记在 `Unreleased` 下。

## Unreleased

### 新增（Added）

- **蓝牙看门狗 `baton-bt-watchdog`**：修复"遥控器睡着后不会自己连回来"。BlueZ 5.72 默认不为 HID 设备重连，且 `mi-remote` 每次连接超时都会在 BlueZ 里留下一个挂起的连接请求（`Operation already in progress`），把后续尝试全挡住。看门狗平时只体检；掉线并超过 20 秒宽限后才出手：试连 → 报"挂起"就 `disconnect` 清掉再连（不暂停 `mi-remote`，也不默认重启蓝牙栈），未连上按 15s→60s 退避。随机自启服务 `baton-bt-watchdog.service`（坑 13）
- **免密码重启蓝牙**（可选兜底）：`system/49-baton-bluetooth.rules` 随 `install.sh` 装到 polkit，只放开本地会话活动用户启停/重启 `bluetooth.service`（不存密码，公开仓库安全）
- **长按 OK = `Ctrl+Enter`**：给 OpenCode 网页版发送消息；短按仍是 `Enter`
- **托盘显示遥控器电量**：读遥控器 Battery Service（`0x180F`，`bluetoothctl info` 的 `Battery Percentage`），在托盘菜单显示 `电量：84%`；≤20% 标 ⚠️ 并弹一次「电量偏低」提醒（回到 >25% 后重新武装）
- **长按返回 = 连续快删**：长按 ≥350ms 触发 `backspace-burst`，借系统按键重复连删约 25 个字符（短按仍是删一个）。脚本从 `extras/` 提回 `scripts/`；需配合本机 mapping 补丁，重装 mi-remote 后重跑 `apply-patch.sh --mapping`
- **小米 MiMo 云端 ASR**：`system/cloud-asr.json` 同时放地址、模型和 api_key（gitignore）；挂掉时桌面通知，可用 `cloud-asr-health` 探测。文档写明建议理由（远场识别率、内存与时延、官方单价 ¥0.5/音频小时 与 Token Plan 30M Credits/小时）
- **转写后整理（可选，默认关）**：`mimo-v2.5-asr` 的提示词由小米网关注入、调用方改不了，所以「口语 → 书面 prompt」改成转写后再走一道对话模型（`mimo-v2.6-flash`）。`cloud-asr.json` 的 `cleanup` 段控制开关/模型/提示词/超时；任何失败（超时、空结果、长度异常、像拒答、像工具调用）都**回退转写原文**，保证不掉字。默认关是因为延迟：只走 ASR 实测约 **1 秒**，加一层约 **2 秒**（重启后第一句约 7.5 秒）
- **仓库结构**：新增 `tools/`（维护工具：键位图生成、logo 生成），运行时脚本仍留在 `scripts/`（会被装进 `~/.local/bin`）
- **项目 logo**：圆形徽章（遥控器 + 信号弧），`docs/images/logo.png`，同时用作桌面图标；托盘栏仍是绿/黄/红三色状态圆点
- **开源化包装**：双语 README（`README.md` 英文 / `README.zh-CN.md` 中文）、`LICENSE`(MIT)、`CHANGELOG.md`、
  `CONTRIBUTING.md`、`THIRD_PARTY.md`（第三方组件与许可证清单）、**键位图**（脚本随配置自动生成）

- **托盘应用 Baton Mi**（Flutter，纯托盘无窗口）
  - 三层连接状态：蓝牙链路 / HID 按键节点 / 服务与注入守护
  - 图标三态：🟢 正常 · 🟡 按键可用但语音未连 · 🔴 服务或按键异常
  - 菜单：状态展示 · **键位速查 ▸**（实时读 `mapping.json` 生成）· 重新检测 · 重启服务 · 重连蓝牙 · 查看日志 · 打开文档 · 退出
  - **断连提醒**：蓝牙断开/恢复时桌面通知（1 分钟冷却，恢复提醒不受冷却限制）
  - 开机自启（`install.sh` 写入 `~/.config/autostart/`）
- **uinput 注入垫片**：GNOME Wayland 下替代不可用的 `wtype`
  - `mi-remote-uinputd`（常驻守护进程 + unix socket）+ `ydotool`（客户端垫片）
  - 实测 30 ms/次（对比"每次新建虚拟设备"的 2.1 s/次）
- **窗口切换器**：长按菜单进入，保持 Alt 后 `←/→` 可遍历**所有**窗口（原生 `Alt+Tab` 只能在两个窗口间跳），闲置 8 秒自动选定、可顺延
- **窗口聚焦**：启动 OpenCode/Cursor 时若目标目录已打开，直接拉到前台
  - 借助 GNOME 扩展 `winrects@cua` 的 DBus 接口（`GetRects`/`Activate`）
- **启动器**：`open-workspace-{opencode,cursor,terminal,files}`（最大化、已开则聚焦、带日志）
- **install.sh**：一键部署/更新（幂等；udev 已最新时跳过、无需 sudo；支持 `SUDO_PASS=`）

### 变更（Changed）

- 对外名称改为 **Baton Mi**（Mi = 小米语音遥控）
- **第二层整理（`cleanup`）改为「懂行」**：提示词写明「用户是程序员、日常做程序开发」，遇近音词优先按开发语境理解；
  新增 `glossary` 术语表**发给大模型**（网关会忽略 ASR 的 `hotwords`，专有词偏置只能走第二层）。
  实测遥控器把 `Vibe Coding` 快读成 `Web God`/`Web Calling`，配术语表后稳定归一到 `Vibe Coding`，表外词原样保留。
  同时写死「语境不足以确定时保持原样，不许凭空补造专有名词」——没有这条时模型会把不认识的词自己编一个

- 文档合并：`docs/键位表.md` + `docs/适配流程.md` + `docs/需求.md` → 单份 [`docs/指南.md`](docs/指南.md)
  （第 1 章键位表 · 第 2 章适配流程与踩坑 · 第 3 章路线图；已回退功能不再写成操作指南）

- 键位反复打磨后的最终形态（详见 `docs/指南.md` 第 1 章）
  - 返回：短按 = 删除（即时）；Esc 从"返回双击"移走（曾因连按被判双击而误打断 AI）
  - 电源：短按 = `Esc`；长按 = 关闭当前窗口（`Alt+F4`）；去掉双击（消除"连按两次误关窗"）
  - 主页：去掉短按/长按，只保留双击启动 OpenCode
  - TV：短按 = `Ctrl+B`（OpenCode 把阻塞的工具转后台）；去掉长按（原 Super 活动概览）
  - 音量：短按 = `PageUp`/`PageDown`（不再调系统音量）
  - 下键：恢复纯 `↓`（菜单导航）
- udev 规则：同时匹配设备名 `小米蓝牙语音遥控器` 与 `MI RC`（实测设备名会变），并加 BLE HID 兜底

### 移除（Removed）

- OpenCode 层（leader 宏那套）；备份见 `system/mapping.json.with-opencode-layer.bak`
- 启动层（短按 TV 进层启动 5 个目标）；备份见 `system/mapping.json.with-launch-layer.bak`
- 鼠标模式（电源键改为 Esc/关窗后无入口；实现仍在，可用 `power.hold = {"type":"mouse_mode"}` 恢复）
- 长按返回"连续快删"（实现留档于 `extras/backspace-burst` 与 `system/patch/`）
- 本分支不再附带本地 Paraformer（`models/paraformer-zh/`）；语音只走小米云端

### 修复（Fixed）

- 语音识别乱码：默认 `--gain 6` 把信号推得更热 → 服务改为 `--gain 0`（**当时以为这是乱码主因，后经坑 14 更正：真因是音频通知重复订阅，与增益无关**；`--gain 0` 仍保留）
- GNOME 下按键注入全线失效：Mutter 不实现 `wtype` 依赖的虚拟键盘协议 → 卸载 wtype + 自写 uinput 垫片
- 官方安装器（v0.4.1）venv shebang 残留临时目录导致装完无法执行 → 批量改写 shebang
- 终端里语音粘贴无效 → 服务参数 `--paste-shortcut ctrl-shift-v`
- 垫片拉起守护进程时解释器无 `evdev` → 自动挑选带 evdev 的解释器（venv python）
- 蓝牙设备名变化导致 udev 规则失效、按键静默失效 → 多重匹配
- **云端 ASR 语种从写死 `zh` 改为 `auto`**：`mimo-v2.5-asr` 支持中英双语与代码混说，官方 `asr_options.language` 默认就是 `auto`；写死 `zh` 会把英文按中文音译（`Cursor → 克鲁兹`）
- **送云端前加 RMS 归一化（AGC）**：把每句话归一到统一目标电平（`normalize` 段，默认 `-16 dBFS`），峰值上限只压尖峰而不整句拉低；实测模型对电平不敏感，故定位为一致性保险
- **重启后遥控器整只失效（按键 + 语音全无反应）**：BlueZ 的 HID-over-GATT 通道偶尔没挂上 —— 蓝牙显示“已连接”、GATT 里也有 HID 服务，但 `/dev/input` 没有节点。仅“断开重连”清不掉。新增自愈脚本 `scripts/baton-bt-recover`（轻量重连 → `block/unblock` → 重启 `bluetooth.service`，逐级复检），托盘「重连蓝牙（自愈）」改调它，并新增 `baton-recover.service` 在登录后自动修复一次（见 `docs/指南.md` 坑 12）
- **语音识别越用越不准（乱码 / 上屏字少，曾被误判为"遥控麦太热"）**：`mi-remote` 每经历一次 BLE 重连，音频 notify 就多出一层订阅，同一帧音频被解码 **N 次**，喂给云端 ASR 的 PCM 被拉长为实际录音的 N 倍（实测进程内从 0.93 一路涨到 4.88 倍）。ADPCM 解码器被喂重复字节后预测器顶轨，波形变成 `峰值 32768` + 大直流偏置 + 低频能量占大头——这正是历史"削波乱码"的真相。新增常驻守卫 `scripts/baton-asr-guard`（判据：一次录音会话里「音频流开始」> 1 次即重启 `mi-remote`；随机自启 `baton-asr-guard.service`）；急用时 `systemctl --user restart mi-remote` 可立即恢复到 1×（见 `docs/指南.md` 坑 14）
