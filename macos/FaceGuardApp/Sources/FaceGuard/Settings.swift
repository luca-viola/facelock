import Combine
import Foundation

enum Paths {
    static let home = FileManager.default.homeDirectoryForCurrentUser
    static let dataDir = home.appendingPathComponent("Library/Application Support/faceguard")
    static let settings = dataDir.appendingPathComponent("settings.json")
    static let reference = dataDir.appendingPathComponent("reference.jpg")
    static let log = home.appendingPathComponent("Library/Logs/FaceGuard.log")
}

/// The same keys and defaults as the GNOME schema and the Python menu bar app's settings.json,
/// so either app can read what the other saved.
struct SettingsData: Codable, Equatable {
    var enabled = false
    var cameraDevice = "auto"
    var intervalMs = 1000
    var model = "buffalo_l"
    var useGpu = false
    var matchThresholds: [String: Double] = [:]  // per model; the model's own default if absent
    var detectionThreshold = 0.5
    var minFacePx = 40
    var absenceGraceS = 10.0
    var intruderGraceS = 1.0
    var intruderAction = "lock"  // lock, eyes, notify or command
    var intruderCommand = ""
    var minimizeApps: [String] = []  // bundle identifiers of the apps to hide
    var minimizeAll = false
    var minimizeRestore = true
    var pythonPath = ""

    static let actions = ["lock", "eyes", "notify", "command"]

    enum CodingKeys: String, CodingKey {
        case enabled
        case cameraDevice = "camera-device"
        case intervalMs = "interval-ms"
        case model
        case useGpu = "use-gpu"
        case matchThresholds = "match-thresholds"
        case detectionThreshold = "detection-threshold"
        case minFacePx = "min-face-px"
        case absenceGraceS = "absence-grace-s"
        case intruderGraceS = "intruder-grace-s"
        case intruderAction = "intruder-action"
        case intruderCommand = "intruder-command"
        case minimizeApps = "minimize-apps"
        case minimizeAll = "minimize-all"
        case minimizeRestore = "minimize-restore"
        case pythonPath = "python-path"
    }

    init() {}

    /// Ignores missing keys and values of the wrong type, keeping the default for those.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func get<T: Decodable>(_ key: CodingKeys, _ fallback: T) -> T {
            (try? c.decodeIfPresent(T.self, forKey: key)) ?? fallback
        }
        enabled = get(.enabled, enabled)
        cameraDevice = get(.cameraDevice, cameraDevice)
        intervalMs = get(.intervalMs, intervalMs)
        model = get(.model, model)
        useGpu = get(.useGpu, useGpu)
        matchThresholds = get(.matchThresholds, matchThresholds)
        detectionThreshold = get(.detectionThreshold, detectionThreshold)
        minFacePx = get(.minFacePx, minFacePx)
        absenceGraceS = get(.absenceGraceS, absenceGraceS)
        intruderGraceS = get(.intruderGraceS, intruderGraceS)
        intruderAction = get(.intruderAction, intruderAction)
        intruderCommand = get(.intruderCommand, intruderCommand)
        minimizeApps = get(.minimizeApps, minimizeApps)
        minimizeAll = get(.minimizeAll, minimizeAll)
        minimizeRestore = get(.minimizeRestore, minimizeRestore)
        pythonPath = get(.pythonPath, pythonPath)
        if !Self.actions.contains(intruderAction) { intruderAction = "lock" }
    }

    /// Whether going from `old` to this needs the daemon to restart.
    func needsRestart(from old: SettingsData) -> Bool {
        cameraDevice != old.cameraDevice || intervalMs != old.intervalMs || model != old.model
            || useGpu != old.useGpu || matchThresholds != old.matchThresholds
            || detectionThreshold != old.detectionThreshold || minFacePx != old.minFacePx
            || absenceGraceS != old.absenceGraceS || intruderGraceS != old.intruderGraceS
            || pythonPath != old.pythonPath
    }
}

@MainActor
final class SettingsStore: ObservableObject {
    @Published var data: SettingsData {
        didSet { if data != oldValue { save() } }
    }

    init() {
        if let bytes = try? Data(contentsOf: Paths.settings),
           let stored = try? JSONDecoder().decode(SettingsData.self, from: bytes) {
            data = stored
        } else {
            data = SettingsData()
        }
    }

    private func save() {
        do {
            try FileManager.default.createDirectory(
                at: Paths.dataDir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(data).write(to: Paths.settings, options: .atomic)
        } catch {
            NSLog("Face Guard: can't save settings: \(error)")
        }
    }
}
