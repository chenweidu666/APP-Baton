# FAQ / 排障速查

> 只列「最常撞到、且能自查」的问题。更深的原因与原理见 [指南.md](指南.md)（第 1.10 节、第 2.6 节踩坑）。

## 一、先看日志

```bash
journalctl --user -u mi-remote.service -n 80 --no-pager
journalctl --user -u baton-bt-watchdog.service -n 40 --no-pager
systemctl --user status mi-remote.service
```

---

## 二、按键 / 语音类

### Q：遥控器按了没反应
1. 蓝牙连着吗？`bluetoothctl info F0:2B:18:87:37:B7 | grep -i connected`
2. HID 节点在吗？`ls /sys/devices/virtual/misc/uhid/`
   - 没有 → 重启后 HID-over-GATT 通道没挂上，用托盘「重连蓝牙（自愈）」或 `~/.local/bin/baton-bt-recover`（坑 12）
3. 换过电视用？遥控器**同一时间只能连一个主机**，回电脑要按「菜单 + HOME」重新配对

### Q：语音识别**乱码**、而且**越用越糟**
真因是**音频通知重复订阅**（[指南坑 14](指南.md)）。**先重启服务**立刻恢复：

```bash
systemctl --user restart mi-remote
```

之后由常驻守卫 `baton-asr-guard` 自动自愈（它会盯「一次录音是否 >1 次『音频流开始』」，命中就重启）。
别再怀疑「遥控器没电」——这跟电量无关。

### Q：语音上屏**延迟高**（3~6 秒，甚至更久）
第二层整理是额外一次云端调用，**延迟主要来自服务端波动**，本地能做的有限：
- 想快就把 `system/cloud-asr.json` 的 `cleanup.enabled` 改回 `false`（只走 ASR，约 1 秒）；
- 或设 `cleanup.min_chars`，让「继续」这类短句跳过整理。
- 已开的提速项：关闭思考（`thinking`）、用最快速度模型 `mimo-v2.6-flash`。

### Q：终端里语音上屏的文本没粘进去
用 `Ctrl+Shift+V`（Wayland 下粘贴快捷键，服务参数已配）。被占用就手动粘贴——文本仍在剪贴板。

### Q：想知道**有没有**被整理层改过
日志里同时会有 `云端 ASR 转写结果: …` 和 `整理后: …` 两行，一眼可辨。

---

## 三、蓝牙类

### Q：遥控器掉线后连不回来
`~/.local/bin/baton-bt-watchdog` 常驻盯着：先给 20 秒宽限让 `mi-remote` 自己重连；仍掉线就试连 → 报
`Operation already in progress` 就 `disconnect` 清挂起再连（坑 13）。深度休眠（连广播都没）时任何软件都没用，按遥控器任意键唤醒。

### Q：`bluetoothctl` 报 `already in progress`
看门狗会清。也可以手动：`bluetoothctl disconnect <MAC>` 再 `connect`。

---

## 四、怎么改行为

| 想改什么 | 改哪里 |
|---|---|
| 键位 | 编辑 `~/.config/mi-remote-linux/mapping.json` → `mi-remote config validate` → 重启 |
| 第二层整理开关 / 术语表 / 超时 | `system/cloud-asr.json` 的 `cleanup` 段（改完重启 `mi-remote`） |
| 云端 ASR 挂掉时是否通知 | `mimo_asr.notify_asr_down`，桌面通知带 60 秒冷却 |
| 查看当前生效配置 | `mi-remote config validate` / `mi-remote doctor` |

> ⚠️ **本机补丁**：`system/patch/apply-patch.sh --mapping` 改的是 **venv 里的 `mapping_engine.py`**，不是仓库文件。
> **重装/升级 mi-remote 后必须重跑**，否则「长按返回」会退回"只删一个"。
