# 贡献指南（Contributing）

感谢愿意帮忙改进 Baton Mi！这是一个**面向单款遥控器**（小米蓝牙语音遥控器，VID:PID `2717:32b8`）的小项目，
所以改动通常集中在"键位映射 / 启动器 / 托盘状态判断 / 文档"这几块。

## 提 Issue 前先看一眼

- 先跑一遍自检，把输出贴上来：
  ```bash
  mi-remote doctor
  systemctl --user is-active mi-remote mi-remote-uinputd
  journalctl --user -u mi-remote -n 50 --no-pager
  ```
- 说明你的环境：发行版 / 桌面（GNOME + Wayland？）/ 遥控器型号与 `bluetoothctl info <MAC>` 的 `Modalias`
- 键位相关问题请附上 `mi-remote keys watch` 按出来的真实码值

## 开发

```bash
git clone https://github.com/chenweidu666/APP-Baton.git
cd Baton
./install.sh              # 幂等；已就绪的部分会自动跳过
cd app && ./run.sh        # 开发托盘应用（构建 + 重启）
```

- 脚本类改动：改 `scripts/`，然后 `./install.sh` 会同步到 `~/.local/bin`
- 键位改动：改 `system/mapping.json`，用 `mi-remote config validate` 校验，再 `./install.sh` 或重启服务
- 托盘应用：改 `app/lib/main.dart`，`cd app && ./run.sh`

## 提交改动

1. 先自查：
   ```bash
   mi-remote config validate system/mapping.json      # 键位配置
   cd app && flutter analyze                          # 托盘应用
   bash tests/test_double.py 2>/dev/null || true      # 行为仿真（需 mi-remote 的 venv python）
   ```
2. **同步文档**：改了键位就更新 `docs/指南.md` 第 1 章（使用与键位）与开头的键位图（`python3 tools/gen-keymap-image.py`），两份 README 里的表格也要跟着改（本项目的硬性要求）
3. **双语 README**：改动涉及 README 时，请同步 `README.md`（英文）与 `README.zh-CN.md`（中文）
3. **提交信息**：一律用**英文**，遵循 Conventional Commits（见下方「提交信息规范」）
4. 开 PR 时说明：**现象 / 原因 / 怎么验证的**（最好附上仿真或真机证据）

## 提交信息规范（Commit messages）

**所有提交信息一律用英文**（仓库历史已按此规范重写），格式遵循
[Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>

<body: why it changed>

<footer: BREAKING CHANGE: … / Closes #12>
```

| 部分 | 要求 |
|---|---|
| `type` | **必填**：`feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore` `style` `revert` |
| `scope` | 可选：`keymap` `tray` `inject` `udev` `systemd` `launcher` `window` `install` `docs` `tools` `branding` |
| `subject` | 英文祈使句、首字母小写、**结尾不加句号**、**≤ 72 字符** |
| `body` | 可选：解释"**为什么**改"（每行 ≤ 72 字符），不要复述 diff |
| `footer` | 可选：`BREAKING CHANGE: …`、`Closes #12`、`Refs #34` |

破坏性改动写成 `feat(keymap)!: …`，并在 footer 里加 `BREAKING CHANGE: …`。

```text
feat(keymap): map power hold to Alt+F4
fix(udev): match the renamed BLE device name (MI RC)
refactor(tools): move maintenance scripts out of scripts/
docs: merge the three Chinese docs into docs/guide
test(inject): cover multi-tap behaviour of the back key
```

本地校验（推荐，提交不合规会被拦下）：

```bash
git config core.hooksPath .githooks      # 启用 commit-msg 钩子（英文 + Conventional Commits + ≤72 字符）
git config commit.template .gitmessage   # 提交时带出模板
```

## 代码风格

- 脚本：`bash` + `set -euo pipefail`，幂等优先，危险操作要能回滚
- Dart：跟随 `flutter analyze`（0 issue），纯托盘不引入窗口
- 文档：中文为主，命令用代码块，表格能省字就省字

## 不适合的改动

- 不针对其它型号遥控器做适配（本项目只保证这一款；但欢迎把通用化的部分抽出来另开项目）
- 不引入需要 root 常驻的服务（当前只有 udev 规则需要 sudo，且是一次性的）
