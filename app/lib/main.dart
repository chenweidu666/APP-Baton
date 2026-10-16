// Baton Mi —— 小米蓝牙语音遥控器状态托盘（纯托盘，无窗口）
//
// 托盘图标：绿=全部正常 / 黄=按键可用但语音未连 / 红=服务或按键异常
// 点图标 → 小菜单：状态三层 + 键位速查（子菜单，直接读 mapping.json）+ 常用操作
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:tray_manager/tray_manager.dart';

/// 这一款遥控器（VID:PID 2717:32b8）；设备名会变，所以按 VID/PID 识别
const String kRemoteVendor = '2717';
const String kRemoteProduct = '32b8';
const String kRemoteMac = 'F0:2B:18:87:37:B7';
const String kService = 'mi-remote.service';
const String kInjectorService = 'mi-remote-uinputd.service';

final String kHome = Platform.environment['HOME'] ?? '/home/chenwei';
final String kRuntimeDir =
    Platform.environment['XDG_RUNTIME_DIR'] ?? '/run/user/1000';
final String kRepoPath =
    Platform.environment['BATON_REPO'] ?? '$kHome/Linux-App/05-Baton';
final String kConfigPath = '$kHome/.config/mi-remote-linux/mapping.json';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const _TrayOnlyApp());
}

// ---------------------------------------------------------------- 状态模型

class RemoteStatus {
  const RemoteStatus({
    required this.bluetooth,
    required this.hid,
    required this.service,
    required this.injector,
    this.voice,
    this.hidNode,
    this.battery,
  });

  final bool bluetooth;
  final bool hid;
  final bool service;
  final bool injector;

  /// 语音链路是否真的可用（看 mi-remote 最近一条链路事件，见 [_voiceReady]）；
  /// null = 还没读到。蓝牙连上 ≠ 语音能用。
  final bool? voice;
  final String? hidNode;

  /// 遥控器电量百分比（0–100）；未连接或固件未上报时为 null
  final int? battery;

  // voice 未知时不当成故障：刚起进程还没读到日志，不该先闪一下黄。
  bool get allGood => bluetooth && voice != false && hid && service && injector;

  String get headline {
    if (allGood) return '遥控器已连接，一切正常';
    if (!service) return '遥控服务未运行';
    if (!hid) return '找不到按键节点';
    if (voice == false) return '按键可用 · 语音链路未连接';
    if (!bluetooth) return '按键可用 · 蓝牙语音未连接';
    return '部分异常';
  }

  String get iconAsset {
    if (allGood) return 'assets/tray_ok.png';
    if (hid && service && injector) return 'assets/tray_warn.png';
    return 'assets/tray_off.png';
  }

  /// 只用来判断"显示内容变没变"，避免每 5 秒无条件重写托盘（见 _refresh）
  String get signature =>
      '$bluetooth|$hid|$service|$injector|$voice|$hidNode|$battery';
}

// ---------------------------------------------------------------- 探测逻辑

Future<String> _run(String exe, List<String> args) async {
  try {
    final r = await Process.run(exe, args);
    return '${r.stdout}${r.stderr}'.trim();
  } catch (_) {
    return '';
  }
}

/// 一次 bluetoothctl info 同时取回连接状态与电量
/// （电量走遥控器的 Battery Service 0x180F，行形如 `Battery Percentage: 0x54 (84)`）
Future<(bool, int?)> _bluetoothInfo() async {
  final out = await _run('bluetoothctl', ['info', kRemoteMac]);
  final connected = out.contains('Connected: yes');
  final match =
      RegExp(r'Battery Percentage:\s*0x[0-9a-fA-F]+\s*\((\d+)\)').firstMatch(out);
  return (connected, match == null ? null : int.tryParse(match.group(1)!));
}

/// 语音链路（ATVV / 按键之外的那条）是否真的可用。
///
/// 上面的 `Connected: yes` 只说明 ACL 在。2026-10-16 那次故障里 bluetoothctl
/// 整整 9 分钟都报已连接、按键也一直能用，mi-remote 却连不上 ATVV、口述发不出去 ——
/// 托盘三态里没有一个能表达这件事，用户只看到"消息发不出去了"。
/// 所以直接看 mi-remote 自己的链路事件：最后一条是"连上了"还是"连不上/断了"。
/// 只读最后 80 行，实测约 10 ms。
Future<bool?> _voiceReady() async {
  final out = await _run('journalctl',
      ['--user', '-u', kService, '-n', '80', '-o', 'cat', '--no-pager']);
  if (out.isEmpty) return null;
  bool? ready;
  for (final line in out.split('\n')) {
    if (line.contains('✅ 已连接遥控器')) {
      ready = true;
    } else if (line.contains('ble_client: 连接失败') ||
        line.contains('ble_client: BLE 连接断开')) {
      ready = false;
    }
  }
  return ready;
}

Future<(bool, String?)> _hidNode() async {
  try {
    for (final dir in Directory('/sys/class/input').listSync()) {
      final name = dir.path.split('/').last;
      if (!name.startsWith('event')) continue;
      try {
        final v = File('${dir.path}/device/id/vendor').readAsStringSync().trim();
        final p = File('${dir.path}/device/id/product').readAsStringSync().trim();
        if (v.toLowerCase() == kRemoteVendor && p.toLowerCase() == kRemoteProduct) {
          return (true, '/dev/input/$name');
        }
      } catch (_) {}
    }
  } catch (_) {}
  return (false, null);
}

/// 通知图标用项目 logo（品牌徽章），而不是托盘的状态图标 ——
/// 一条「已连接」的通知配红色禁止图标会很怪。两个路径都不在时就不带图标。
String? _brandIcon() {
  for (final p in [
    '$kRepoPath/docs/images/logo.png',
    '${Platform.environment['HOME']}/.local/share/icons/hicolor/512x512/apps/baton.png',
  ]) {
    if (File(p).existsSync()) return p;
  }
  return null;
}

/// 桌面通知（走 notify-send）。失败静默，不影响主流程。
Future<void> _notify(String title, String body, {bool urgent = false}) async {
  final icon = _brandIcon();
  final args = <String>[
    '-a', 'Baton Mi',
    if (icon != null) ...['-i', icon],
    if (urgent) ...['-u', 'critical'],
    title,
    body,
  ];
  stderr.writeln('[notify] $title — $body'); // 落到 /tmp/baton.log，便于验证
  await _run('notify-send', args);
}

Future<bool> _unitActive(String unit) async =>
    (await _run('systemctl', ['--user', 'is-active', unit])).split('\n').first.trim() ==
    'active';

Future<RemoteStatus> _probe() async {
  final (bt, battery) = await _bluetoothInfo();
  final (hid, node) = await _hidNode();
  return RemoteStatus(
    bluetooth: bt,
    hid: hid,
    service: await _unitActive(kService),
    injector: await _unitActive(kInjectorService),
    voice: await _voiceReady(),
    hidNode: node,
    battery: battery,
  );
}

// ------------------------------------------------- 键位速查（读 mapping.json）

const Map<String, String> _keyLabels = {
  'voice': '语音',
  'ok': 'OK',
  'up': '上',
  'down': '下',
  'left': '左',
  'right': '右',
  'back': '返回',
  'home': '主页',
  'menu': '菜单',
  'tv': 'TV',
  'vol_up': '音量＋',
  'vol_down': '音量－',
  'power': '电源',
};

String _describe(Map<String, dynamic>? action) {
  if (action == null) return '—';
  final type = action['type'] as String? ?? '';
  switch (type) {
    case 'none':
      return '—';
    case 'voice':
      return '按住口述';
    case 'key_stroke':
      const names = {
        'backspace': '删一个',
        'escape': 'Esc',
        'return': 'Enter',
        'page_up': 'PageUp',
        'page_down': 'PageDown',
        'up_arrow': '↑',
        'down_arrow': '↓',
        'left_arrow': '←',
        'right_arrow': '→',
        'tab': 'Tab',
        'F4': 'F4',
      };
      const mods = {'ctrl': 'Ctrl', 'alt': 'Alt', 'shift': 'Shift', 'super': 'Super'};
      final key = names[action['key']] ?? (action['key'] as String? ?? '?');
      final ms = ((action['mods'] as List?) ?? const [])
          .map((m) => mods[m] ?? m)
          .join('+');
      return ms.isEmpty ? key : '$ms+$key';
    case 'command':
      final argv = (action['argv'] as List?)?.cast<String>() ?? const [];
      final name = argv.isEmpty ? '' : argv.first.split('/').last;
      switch (name) {
        case 'window-switcher':
          return '窗口切换器';
        case 'open-workspace-opencode':
          return '打开 OpenCode';
        case 'open-workspace-cursor':
          return '打开 Cursor';
        case 'open-workspace-terminal':
          return '打开终端';
        case 'open-workspace-files':
          return '文件管理器';
        case 'ydotool':
          return 'Super（活动概览）';
        case 'backspace-burst':
          return '连续删';
        default:
          return name.isEmpty ? '命令' : name;
      }
    case 'system':
      const sys = {
        'display_sleep': '关显示器',
        'volume_up': '音量＋',
        'volume_down': '音量－',
        'mute': '静音',
        'play_pause': '播放/暂停',
        'show_desktop': '显示桌面',
        'mission_control': '任务视图',
      };
      return sys[action['value']] ?? (action['value'] as String? ?? '');
    case 'layer_toggle':
      return '切换层${action['value']}';
    case 'macro':
      return '宏';
    default:
      return type;
  }
}


/// 读 mapping.json → 生成"返回：短按 删一个 · 长按 — · 双击 Esc"这样的子菜单项
List<MenuItem> _keymapItems() {
  try {
    final raw = File(kConfigPath).readAsStringSync();
    final data = jsonDecode(raw) as Map<String, dynamic>;
    final bindings = (data['bindings'] as Map).cast<String, dynamic>();
    final items = <MenuItem>[];
    for (final entry in _keyLabels.entries) {
      final b = (bindings[entry.key] as Map?)?.cast<String, dynamic>();
      if (b == null) continue;
      final tap = _describe((b['tap'] as Map?)?.cast<String, dynamic>());
      final hold = _describe((b['hold'] as Map?)?.cast<String, dynamic>());
      final dbl = _describe((b['double'] as Map?)?.cast<String, dynamic>());
      final parts = <String>[
        if (tap != '—') '短按 $tap',
        if (hold != '—') '长按 $hold',
        if (dbl != '—') '双击 $dbl',
      ];
      items.add(MenuItem(
        key: 'key_${entry.key}',
        label: '${entry.value}：${parts.isEmpty ? "无功能" : parts.join(" · ")}',
        disabled: true,
      ));
    }
    if (items.isEmpty) {
      items.add(MenuItem(key: 'key_none', label: '（读不到键位配置）', disabled: true));
    }
    return items;
  } catch (_) {
    return [MenuItem(key: 'key_err', label: '（mapping.json 解析失败）', disabled: true)];
  }
}

// ---------------------------------------------------------------- 托盘主体

class _TrayOnlyApp extends StatelessWidget {
  const _TrayOnlyApp();

  @override
  Widget build(BuildContext context) =>
      const MaterialApp(debugShowCheckedModeBanner: false, home: _TrayController());
}

class _TrayController extends StatefulWidget {
  const _TrayController();

  @override
  State<_TrayController> createState() => _TrayControllerState();
}

class _TrayControllerState extends State<_TrayController> with TrayListener {
  Timer? _timer;
  bool _busy = false;
  // 上一次的显示内容；只有变了才碰托盘（见 _refresh）
  String? _lastSignature;
  bool _lastBusy = false;
  // 上一次的链路状态（null = 还没探测过，用于跳过首次）
  bool? _lastBluetooth;
  bool? _lastVoice;
  DateTime? _lastNotify;
  // HID 节点抖动去抖用（见 _settleHid）
  int _hidMissStreak = 0;
  String? _lastHidNode;
  // 低电量只提醒一次；电量回到 25% 以上后重新武装
  bool _lowBatteryNotified = false;

  @override
  void initState() {
    super.initState();
    trayManager.addListener(this);
    _initTray();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    trayManager.removeListener(this);
    super.dispose();
  }

  /// Linux 的 appindicator 不支持 tooltip 等能力，统一吞异常
  Future<void> _safe(Future<void> Function() action) async {
    try {
      await action();
    } catch (_) {}
  }

  Future<void> _initTray() async {
    await _safe(() => trayManager.setToolTip('Baton Mi'));
    await _refresh();
  }

  /// 链路断开/恢复时提醒（跳变才提醒；我们自己操作期间不打扰）
  ///
  /// 所有提醒共用同一个冷却窗口：蓝牙抖动时断/连会往复跳变，逐个放行会把通知刷满。
  Future<void> _notifyTransitions(RemoteStatus s) async {
    final wasBluetooth = _lastBluetooth;
    final wasVoice = _lastVoice;
    _lastBluetooth = s.bluetooth;
    _lastVoice = s.voice;
    if (_busy) return;

    final now = DateTime.now();
    final cooled = _lastNotify == null ||
        now.difference(_lastNotify!) > const Duration(minutes: 1);
    if (!cooled) return;

    String? title;
    String? body;
    if (wasBluetooth == true && !s.bluetooth) {
      title = '遥控器已断开';
      body = '可能只是休眠了 · 按遥控器任意键唤醒；或点托盘 → 重连蓝牙';
    } else if (s.voice == false && wasVoice != false) {
      // 2026-10-16 那次故障就是这种：链路还在、按键还能用，口述却发不出去
      title = '语音链路已断开';
      body = '按键仍可用，但口述暂时发不出去 · 点托盘 → 重启遥控服务';
    } else if (wasBluetooth == false && s.bluetooth && s.hid) {
      title = '遥控器已连接';
      body = '按键与语音都恢复了';
    } else if (wasVoice == false && s.voice == true) {
      title = '语音链路已恢复';
      body = '可以继续口述了';
    } else if (wasBluetooth == false && s.bluetooth && !s.hid) {
      title = '蓝牙已连上，但按键节点还没就绪';
      body = '稍等几秒；若一直如此点托盘 → 重连蓝牙';
    }
    if (title == null) return;
    _lastNotify = now;
    await _notify(title, body!);
  }

  /// 低电量提醒：≤20% 提醒一次；回到 >25% 后重新武装
  Future<void> _notifyBattery(RemoteStatus s) async {
    final b = s.battery;
    if (b == null) return;
    if (b <= 20 && !_lowBatteryNotified) {
      _lowBatteryNotified = true;
      await _notify('遥控器电量偏低', '剩余 $b%，记得充电');
    } else if (b > 25) {
      _lowBatteryNotified = false;
    }
  }

  /// 内核在 BLE 重连时会把遥控器的 HID 节点摘掉再挂回来（2026-10-16 那次抖动里
  /// 45 秒内重建了 4 次），单次探测落空就报"找不到按键节点"会让托盘图标红绿闪。
  /// 连续两次落空才认定真的缺失。
  RemoteStatus _settleHid(RemoteStatus s) {
    if (s.hid) {
      _hidMissStreak = 0;
      _lastHidNode = s.hidNode;
      return s;
    }
    if (_hidMissStreak < 1) {
      _hidMissStreak++;
      return RemoteStatus(
        bluetooth: s.bluetooth,
        hid: true,
        service: s.service,
        injector: s.injector,
        voice: s.voice,
        hidNode: _lastHidNode,
        battery: s.battery,
      );
    }
    return s;
  }

  Future<void> _refresh() async {
    final s = _settleHid(await _probe());
    await _notifyTransitions(s);
    await _notifyBattery(s);

    // 内容没变就不碰托盘。以前每 5 秒无条件 setIcon + setContextMenu，而
    // tray_manager 的 Linux 端每次 setContextMenu 都新建一个 GtkMenu（旧的
    // 既不销毁也不复用），宿主跟着重渲染 —— 既漏内存又让图标一直闪。
    if (_lastSignature == s.signature && _lastBusy == _busy) return;
    _lastSignature = s.signature;
    _lastBusy = _busy;

    await _safe(() => trayManager.setIcon(s.iconAsset));
    await _safe(() => trayManager.setToolTip(
        'Baton Mi · ${s.headline}${s.battery != null ? " · 电量 ${s.battery}%" : ""}'));
    await trayManager.setContextMenu(Menu(items: [
      MenuItem(key: 'status', label: '状态：${s.headline}', disabled: true),
      MenuItem.separator(),
      MenuItem(
        key: 'bt',
        label: '蓝牙：${s.bluetooth ? "已连接" : "未连接"}',
        disabled: true,
      ),
      MenuItem(
        key: 'hid',
        label: '按键节点：${s.hid ? (s.hidNode ?? "存在") : "缺失"}',
        disabled: true,
      ),
      MenuItem(
        key: 'voice',
        label: '语音：${s.voice == null ? "未知" : (s.voice! ? "可用" : "未连接")}',
        disabled: true,
      ),
      MenuItem(
        key: 'svc',
        label: '服务：${s.service ? "运行中" : "已停止"}'
            ' ／ 注入：${s.injector ? "运行中" : "已停止"}',
        disabled: true,
      ),
      MenuItem(
        key: 'battery',
        label: '电量：${s.battery != null ? "${s.battery}%" : "未知"}'
            '${s.battery != null && s.battery! <= 20 ? "  ⚠️ 偏低" : ""}',
        disabled: true,
      ),
      MenuItem.separator(),
      MenuItem.submenu(
        key: 'keymap',
        label: '键位速查',
        submenu: Menu(items: _keymapItems()),
      ),
      MenuItem.separator(),
      MenuItem(key: 'recheck', label: _busy ? '处理中…' : '重新检测'),
      MenuItem(key: 'restart', label: '重启遥控服务'),
      MenuItem(key: 'bluetooth', label: _busy ? '处理中…' : '重连蓝牙（自愈）'),
      MenuItem.separator(),
      MenuItem(key: 'log', label: '查看服务日志'),
      MenuItem(key: 'doc', label: '打开使用指南'),
      MenuItem.separator(),
      MenuItem(key: 'quit', label: '退出'),
    ]));
  }

  @override
  void onTrayIconMouseDown() => _refresh();

  @override
  void onTrayIconRightMouseDown() => _refresh();

  @override
  void onTrayMenuItemClick(MenuItem menuItem) async {
    switch (menuItem.key) {
      case 'recheck':
        await _refresh();
        break;
      case 'restart':
        _busy = true;
        await _run('systemctl', ['--user', 'restart', kService]);
        await Future.delayed(const Duration(seconds: 3));
        _busy = false;
        await _refresh();
        break;
      case 'bluetooth':
        // 交给自愈脚本：轻量重连 → block/unblock → 必要时重启 bluetooth.service。
        // 仅"断开重连"清不掉 BlueZ 的 HID-over-GATT 卡死（见 docs/指南.md 坑 12）。
        _busy = true;
        await _refresh();
        await _run('$kHome/.local/bin/baton-bt-recover', const []);
        _busy = false;
        await _refresh();
        break;
      case 'log':
        await Process.start('gnome-terminal', [
          '--title=Baton Mi 日志',
          '--',
          'bash',
          '-lc',
          'journalctl --user -u $kService -f',
        ]);
        break;
      case 'doc':
        await _run('xdg-open', ['$kRepoPath/docs/指南.md']);
        break;
      case 'quit':
        await trayManager.destroy();
        exit(0);
    }
  }

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
