#!/usr/bin/env python3
"""Offline-first scoped build patch for the PUBLIC LocationSpoofer main source.

This is not a modification of any commercial release or account verification.
Anchors are checked to fail clearly on incompatible upstream revisions.
"""
import argparse
from pathlib import Path

ROOT = Path.cwd()

def replace_one(s, old, new, label):
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source anchor, got {count}")
    return s.replace(old, new, 1)

def edit(path, fn):
    p = ROOT / path
    if not p.is_file():
        raise RuntimeError(f"Missing upstream file: {p}")
    original = p.read_text(encoding="utf-8")
    if "OFFLINE_SCOPED_PATCH" in original:
        print(f"Already patched: {path}")
        return
    changed = fn(original)
    if changed == original:
        raise RuntimeError(f"No changes made: {path}")
    p.write_text(changed, encoding="utf-8")
    print(f"Patched: {path}")

def scaffold(s):
    s = replace_one(
        s,
        '    var mapController by remember { mutableStateOf<AppMapController?>(null) }',
        '    var mapController by remember { mutableStateOf<AppMapController?>(null) }\n'
        '    // OFFLINE_SCOPED_PATCH: Map SDK is opt-in; avoid map tile calls at startup.\n'
        '    var onlineMapEnabled by remember { mutableStateOf(false) }',
        "offline map state")
    s = replace_one(
        s,
        '    LaunchedEffect(Unit) {\n        updateViewModel.fetchReleases()\n    }',
        '    // OFFLINE_SCOPED_PATCH: no automatic release request at startup.',
        "startup update")
    start = '                    AppMapView(\n'
    marker = '\n\n                    // 定位选点十字准心'
    if s.count(start) != 1 or s.count(marker) != 1:
        raise RuntimeError("Map view anchors mismatch")
    st = s.index(start)
    end = s.index(marker, st)
    original = s[st:end]
    if not original.rstrip().endswith(')'):
        raise RuntimeError("Unexpected AppMapView closing; refusing unsafe edit")
    replacement = '''                    if (onlineMapEnabled) {
''' + original + '''
                    } else {
                        Column(
                            modifier = Modifier.align(Alignment.Center).padding(24.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Text("离线优先模式", style = MaterialTheme.typography.titleMedium)
                            Text(
                                "定位页可直接输入经纬度；路线页可手动添加路径点。",
                                style = MaterialTheme.typography.bodySmall
                            )
                            androidx.compose.material3.Button(onClick = { onlineMapEnabled = true }) {
                                Text("加载在线地图（可能联网）")
                            }
                        }
                    }'''
    s = s[:st] + replacement + s[end:]
    return replace_one(s, 'visible = selectedTab == 0,',
                       'visible = selectedTab == 0 && onlineMapEnabled,',
                       "offline crosshair")

def static_spoof(s):
    return replace_one(
        s,
        '''        if (state.mockWifi && !hasLocalWifiWithin50m(lat, lng)) {
            fetchWifiFromWigleSync(lat, lng)
        }
        if (state.mockCell && !hasLocalCellsWithin50m(lat, lng)) {
            fetchCellFromOpenCellIdSync(lat, lng)
        }
''',
        '        // OFFLINE_SCOPED_PATCH: use local radio records; no automatic cloud queries.\n',
        "start cloud lookup")

def route_vm(s):
    s = replace_one(
        s,
        '''            if (state.mockWifi && !hasLocalWifiWithin50m(lat, lng) && !isDragging) {
                fetchWifiFromWigleSync(lat, lng)
            }
            if (state.mockCell && !hasLocalCellsWithin50m(lat, lng) && !isDragging) {
                fetchCellFromOpenCellIdSync(lat, lng)
            }
''',
        '            // OFFLINE_SCOPED_PATCH: do not auto-fetch WiGLE/OpenCellID on map moves.\n',
        "move cloud lookup")
    return replace_one(
        s,
        '''    if (state.useRealRoute) {
        _uiState.update { it.copy(isFetchingRoute = true) }
        fetchRealRouteAndStart(state.routePoints, state)
    } else {
        startSimulationWithPoints(state.routePoints, state)
    }
''',
        '    // OFFLINE_SCOPED_PATCH: straight waypoint interpolation, no online route planning.\n'
        '    startSimulationWithPoints(state.routePoints, state)\n',
        "route network call")

def config(s):
    return replace_one(
        s, '        refreshGeocodeIfMoved(lat, lng)\n',
        '        // OFFLINE_SCOPED_PATCH: no reverse geocoder network request.\n',
        "reverse geocoding")

def route_ui(s):
    s = replace_one(
        s,
        '    var searchQuery by remember { mutableStateOf("") }',
        '    // OFFLINE_SCOPED_PATCH: add manual waypoint entry without map tiles.\n'
        '    var offlineLat by remember { mutableStateOf("") }\n'
        '    var offlineLng by remember { mutableStateOf("") }\n'
        '    var searchQuery by remember { mutableStateOf("") }',
        "manual waypoint variables")
    marker = '                // 中心瞄准十字准心（选点阶段显示，搜索激活时隐藏）'
    if s.count(marker) != 1:
        raise RuntimeError("Route crosshair anchor mismatch")
    block = '''                // OFFLINE_SCOPED_PATCH: allow offline waypoint entry instead of map tapping.
                if (mapController == null && !searchActive && stage == RoutePlanStage.SELECTING) {
                    Surface(
                        modifier = Modifier.align(Alignment.Center).padding(horizontal = 20.dp),
                        shape = RoundedCornerShape(18.dp),
                        tonalElevation = 4.dp
                    ) {
                        Column(
                            modifier = Modifier.widthIn(max = 320.dp).padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text("离线路线点", style = MaterialTheme.typography.titleSmall)
                            OutlinedTextField(
                                value = offlineLat,
                                onValueChange = { offlineLat = it },
                                label = { Text("纬度 -90 ~ 90") },
                                singleLine = true
                            )
                            OutlinedTextField(
                                value = offlineLng,
                                onValueChange = { offlineLng = it },
                                label = { Text("经度 -180 ~ 180") },
                                singleLine = true
                            )
                            Button(onClick = {
                                val lat = offlineLat.toDoubleOrNull()
                                val lng = offlineLng.toDoubleOrNull()
                                if (lat != null && lng != null && lat in -90.0..90.0 && lng in -180.0..180.0) {
                                    viewModel.addRoutePoint(lat, lng)
                                } else {
                                    Toast.makeText(context, "请输入有效的经纬度", Toast.LENGTH_SHORT).show()
                                }
                            }) { Text("添加路线点") }
                            Text("至少添加两个点，然后在下方面板完成选点并开始。",
                                 style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }

'''
    s = s.replace(marker, block + marker, 1)
    s = replace_one(
        s,
        'if ((stage == RoutePlanStage.SELECTING || stage == RoutePlanStage.IDLE) && !searchActive) {',
        'if ((stage == RoutePlanStage.SELECTING || stage == RoutePlanStage.IDLE) && !searchActive && mapController != null) {',
        "route crosshair")
    return replace_one(
        s,
        'onUseRealRouteChange = viewModel::setUseRealRoute,',
        'onUseRealRouteChange = { viewModel.setUseRealRoute(false) },',
        "route toggle")

def defaults(s):
    return replace_one(
        s,
        '            mockWifi = settingsRepository.mockWifi,\n'
        '            mockCell = settingsRepository.mockCell,\n'
        '            mockBluetooth = settingsRepository.mockBluetooth,',
        '            // OFFLINE_SCOPED_PATCH: GPS-only by default; locally saved radio fingerprints remain available.\n'
        '            mockWifi = false,\n'
        '            mockCell = false,\n'
        '            mockBluetooth = false,',
        "offline defaults")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    global ROOT
    ROOT = Path(args.root).resolve()
    ui = "app-ui/src/main/java/com/vincenthzr/locationspoofer/"
    edit(ui + "ui/screen/MainScaffoldScreen.kt", scaffold)
    edit(ui + "viewmodel/MainViewModelSpoofing.kt", static_spoof)
    edit(ui + "viewmodel/MainViewModelRoute.kt", route_vm)
    edit("core-data/src/main/java/com/vincenthzr/locationspoofer/utils/ConfigManager.kt", config)
    edit(ui + "ui/screen/tabs/RouteTab.kt", route_ui)
    edit(ui + "viewmodel/MainViewModel.kt", defaults)
    print("Ready to build: ./gradlew :app:assembleScopedDebug")

if __name__ == "__main__":
    main()
