---
name: Bug report
about: Something is broken (keys, voice, injection, tray)
title: "[Bug] "
labels: bug
assignees: ""
---

## 环境

- 发行版 / 桌面（GNOME Wayland?）:
- 遥控器型号（13 键 / 10 键）:
- 安装方式（`install.sh` / 官方安装器）:
- `mi-remote doctor` 输出（贴全）:

## 现象

<!-- 期望 vs 实际，越具体越好 -->

## 复现步骤

1.
2.
3.

## 日志

```bash
journalctl --user -u mi-remote.service -n 100 --no-pager
```

<!-- 如果和语音有关，把 ~/.local/state/mi-remote/audio-debug/ 里对应的 capture-*.wav 也附上 -->

## 其它

<!-- 试过重启服务 / 重连蓝牙吗？结果如何 -->
