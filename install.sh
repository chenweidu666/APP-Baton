#!/bin/bash
# 一键安装 / 更新：把本仓库的内容部署到系统对应位置
#
# 用法: ./install.sh [--no-service] [--no-udev]
#   --no-service  不动 systemd 服务（只装脚本）
#   --no-udev     不动 udev 规则（不需要 sudo）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
CFG="$HOME/.config/mi-remote-linux"
UDEV=/etc/udev/rules.d/70-mi-remote-linux.rules
UNITS="$HOME/.config/systemd/user"
APPS="$HOME/.local/share/applications"
STAMP="$(date +%Y%m%d-%H%M%S)"

DO_UDEV=1; DO_SERVICE=1; DO_PATCH=0

# sudo 包装：无终端时可用 SUDO_PASS=密码 ./install.sh
sudo_run() {
  if [ -n "${SUDO_PASS:-}" ]; then
    printf '%s\n' "$SUDO_PASS" | sudo -S "$@"
  else
    sudo "$@"
  fi
}
for arg in "$@"; do
  case "$arg" in
    --no-udev) DO_UDEV=0 ;;
    --no-service) DO_SERVICE=0 ;;
    --with-patch) DO_PATCH=1 ;;
    *) echo "未知参数: $arg"; exit 2 ;;
  esac
done

echo "== 1/6 安装脚本到 $BIN =="
mkdir -p "$BIN"
for f in "$ROOT"/scripts/*; do
  name="$(basename "$f")"
  install -m 755 "$f" "$BIN/$name"
  echo "   $name"
done

echo "== 2/6 部署键位配置到 $CFG =="
mkdir -p "$CFG"
if [ -f "$CFG/mapping.json" ]; then
  cp "$CFG/mapping.json" "$CFG/mapping.json.bak-$STAMP"
  echo "   已备份原配置 → mapping.json.bak-$STAMP"
fi
install -m 644 "$ROOT/system/mapping.json" "$CFG/mapping.json"

echo "== 3/6 应用 mi-remote 云端 ASR 补丁 =="
if [ ! -f "$ROOT/system/cloud-asr.json" ] && [ -f "$ROOT/system/cloud-asr.json.example" ]; then
  cp "$ROOT/system/cloud-asr.json.example" "$ROOT/system/cloud-asr.json"
  chmod 600 "$ROOT/system/cloud-asr.json"
  echo "   已从 example 生成 system/cloud-asr.json（请填入 api_key，此文件不进 git）"
fi
if python3 "$ROOT/system/patch/apply-mimo-asr.py"; then
  echo "   mimo-asr 已打入本机 mi-remote"
else
  echo "   ⚠️ mimo-asr 补丁跳过（可能尚未安装 mi-remote）"
fi
if [ "$DO_PATCH" = 1 ]; then
  bash "$ROOT/system/patch/apply-patch.sh" --mapping || echo "   ⚠️ mapping 补丁跳过"
fi

echo "== 4/6 桌面图标 =="
if [ -f "$ROOT/system/opencode-workspace.desktop" ]; then
  mkdir -p "$APPS"
  sed "s|/home/chenwei|$HOME|g" "$ROOT/system/opencode-workspace.desktop" > "$APPS/opencode-workspace.desktop"
  echo "   opencode-workspace.desktop"
fi

if [ "$DO_UDEV" = 1 ]; then
  if [ -f "$UDEV" ] && cmp -s "$ROOT/system/70-mi-remote-linux.rules" "$UDEV"; then
    echo "== 5/6 udev 规则已是最新，跳过（无需 sudo）=="
  else
    echo "== 5/6 udev 规则（需要 sudo）=="
    if sudo_run install -m 644 "$ROOT/system/70-mi-remote-linux.rules" "$UDEV" \
       && sudo_run udevadm control --reload-rules \
       && sudo_run udevadm trigger --subsystem-match=input; then
      echo "   已写入 $UDEV"
    else
      echo "   ⚠️ udev 写入失败（无 sudo 权限？可用 SUDO_PASS=密码 重跑，或加 --no-udev 跳过）"
      echo "      现有规则未改动，按键仍可工作"
    fi
    # polkit：让本地活动用户免密码重启 bluetooth.service（看门狗兜底用）
    if sudo_run install -m 644 "$ROOT/system/49-baton-bluetooth.rules" /etc/polkit-1/rules.d/49-baton-bluetooth.rules; then
      echo "   已写入 /etc/polkit-1/rules.d/49-baton-bluetooth.rules（重启蓝牙免密码）"
    else
      echo "   ⚠️ polkit 规则写入失败（看门狗兜底重启蓝牙时仍会弹密码）"
    fi
  fi
else
  echo "== 5/6 跳过 udev（--no-udev）=="
fi

if [ "$DO_SERVICE" = 1 ]; then
  echo "== 6/6 systemd 用户服务 =="
  mkdir -p "$UNITS"
  for unit in mi-remote.service mi-remote-uinputd.service baton-recover.service baton-bt-watchdog.service baton-asr-guard.service; do
    sed -e "s|@BATON_ROOT@|$ROOT|g" -e "s|/home/chenwei|$HOME|g" -e "s|~/.local/bin|$BIN|g" "$ROOT/system/$unit" > "$UNITS/$unit"
    echo "   $unit"
  done
  systemctl --user daemon-reload
  systemctl --user enable --now mi-remote-uinputd.service
  systemctl --user enable --now baton-recover.service
  systemctl --user enable --now baton-bt-watchdog.service
  systemctl --user enable --now baton-asr-guard.service
  systemctl --user restart mi-remote.service || true
  sleep 3
  echo "   服务状态: $(systemctl --user is-active mi-remote.service) / $(systemctl --user is-active mi-remote-uinputd.service)"
  # 提交钩子：让 .githooks/ 生效（幂等；不在 git 仓库里就跳过）
  if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$ROOT" config core.hooksPath .githooks
    echo "   已启用提交钩子 .githooks/（core.hooksPath）"
  fi
else
  echo "== 6/6 跳过 systemd（--no-service）=="
fi

echo
echo "== 7/7 托盘应用（Baton Mi）=="
FLUTTER="$(command -v flutter || echo "$HOME/flutter/bin/flutter")"
if [ -x "$FLUTTER" ]; then
  ( cd "$ROOT/app" && PATH="$(dirname "$FLUTTER"):$PATH" flutter build linux --release >/dev/null 2>&1 ) \
    && echo "   已构建 release" || echo "   ⚠️ 构建失败（可稍后在 app/ 里手动 ./run.sh）"
  APP_DEST="$HOME/.local/share/baton"
  rm -rf "$APP_DEST"; mkdir -p "$APP_DEST"
  cp -r "$ROOT/app/build/linux/x64/release/bundle/." "$APP_DEST/" 2>/dev/null || true
  install -m 755 "$ROOT/scripts/baton" "$BIN/baton"
  # 图标：装进用户图标主题（桌面条目用 Icon=baton 引用）
  ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
  mkdir -p "$ICON_DIR" "$APPS" "$HOME/.config/autostart"
  install -m 644 "$ROOT/docs/images/logo.png" "$ICON_DIR/baton.png"
  command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
  # 桌面条目：开机自启 + 应用列表里可手动启动
  sed "s|/home/chenwei|$HOME|g" "$ROOT/system/baton.desktop" > "$HOME/.config/autostart/baton.desktop"
  sed "s|/home/chenwei|$HOME|g" "$ROOT/system/baton.desktop" > "$APPS/baton.desktop"
  echo "   图标与桌面条目已安装（应用列表搜 Baton Mi）"
  pkill -x baton 2>/dev/null || true
  sleep 1
  nohup "$BIN/baton" >/tmp/baton.log 2>&1 &
  sleep 4
  if pgrep -x baton >/dev/null; then
    echo "   已安装并启动（顶栏可见状态圆点）· 开机自启已写入 ~/.config/autostart/"
  else
    echo "   ⚠️ 启动失败，见 /tmp/baton.log"
  fi
else
  echo "   跳过：未找到 flutter（只装了脚本部分）"
fi

echo
echo "✅ 完成。自检："
echo "   mi-remote doctor"
echo "   systemctl --user is-active mi-remote mi-remote-uinputd"
echo "   顶栏托盘图标：绿色=正常 / 黄色=按键可用但蓝牙语音未连 / 红色=服务或按键异常"
