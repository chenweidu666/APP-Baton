#!/bin/bash
# 升级/重装 mi-remote 后重新打补丁。
# 默认：小米云端 ASR（mimo-asr）。长按返回可配置仍需 --mapping。
# 用法: bash apply-patch.sh [版本号，默认 0.4.1] [--mapping]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V="0.4.1"
DO_MAPPING=0
for arg in "$@"; do
  case "$arg" in
    --mapping) DO_MAPPING=1 ;;
    *) V="$arg" ;;
  esac
done

python3 "$HERE/apply-mimo-asr.py" "$V"
python3 "$HERE/apply-ble-teardown.py" "$V"

if [ "$DO_MAPPING" = 1 ]; then
  F="$HOME/.local/share/mi-remote-linux/versions/$V/lib/python3.12/site-packages/mi_remote_linux/mapping_engine.py"
  [ -f "$F" ] || { echo "找不到 $F"; exit 1; }
  if grep -q 'self._binding(key).hold is None' "$F"; then
    echo "mapping 补丁已存在，无需处理"
  else
    sed -i 's/if key == "back" and self.effective_layer == 0:/if key == "back" and self.effective_layer == 0 and self._binding(key).hold is None:/' "$F"
    grep -q 'self._binding(key).hold is None' "$F" && echo "✅ mapping 补丁已应用: $F" || { echo "❌ mapping 补丁失败"; exit 1; }
  fi
fi
echo "接着执行: systemctl --user restart mi-remote"
