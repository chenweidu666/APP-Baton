# Security Policy

## 支持范围

只维护 `master` 上的最新提交；本项目没有长期支持分支。

## 报告漏洞

**请不要开公开 issue。** 走 GitHub 的私密漏洞上报（只有维护者可见）：

<https://github.com/chenweidu666/APP-Baton/security/advisories/new>

或邮件 `chenweidu666@users.noreply.github.com`。

请尽量附上：影响版本 / 复现步骤 / 影响面 / 你设想的修法。我们会在 **72 小时内**回执。

## 这个项目碰哪些敏感面

它在本机运行，并且要接触下面这些高权限部件 —— 报告时请说清命中哪一块：

| 面 | 说明 |
|---|---|
| **按键注入** | `scripts/ydotool` 垫片 + `scripts/mi-remote-uinputd`（uinput 虚拟设备）：会向系统注入伪造键盘事件 |
| **蓝牙** | BLE 链路 + HID 覆盖（`--grab-hid`）；`/etc/polkit-1/rules.d/49-baton-bluetooth.rules` 放开了「本地活动用户免密码重启 `bluetooth.service`」 |
| **udev 规则** | `/etc/udev/rules.d/70-mi-remote-linux.rules`（按键节点权限） |
| **云端密钥** | 云端 ASR 与第二层整理都要用 API key，且都会发往外部接口 |
| **本机补丁** | `system/patch/apply-patch.sh` 会**改写 venv 里的 `mapping_engine.py`**（不是仓库文件） |

## 密钥约定（重要）

- `system/cloud-asr.json` 与 `.env` 都含云端 API key，**都已写进 `.gitignore`**；仓库里只提交
  `system/cloud-asr.json.example`（占位 key）。
- **绝不**把 key 写进源代码、文档、issue、截图或日志。
- 一旦怀疑泄漏：**先在 Token Plan 后台轮换 key**，再去清理 git 历史 —— 只删文件不够，
  历史提交里仍然能翻出来。

## 披露节奏

确认修复并发布后，我们会在此仓库的 Release 说明里给出致谢（除非你要求匿名）。
