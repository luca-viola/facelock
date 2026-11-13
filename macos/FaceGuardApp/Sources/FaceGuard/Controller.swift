import AppKit
import AVFoundation
import Combine

enum Phase { case off, starting, owner, absent, intruder, error }
enum CaptureState { case idle, starting, ready, checking }

struct CameraInfo: Identifiable, Hashable {
    let id: String  // the unique ID the daemon stores
    let name: String
    let virtual: Bool
}

struct ModelInfo: Identifiable, Hashable {
    let id: String
    let label: String
    let downloaded: Bool
    let gpu: Bool  // whether it can use the GPU here
    let defaultMatch: Double
    let usesDetection: Bool  // whether the detection threshold means anything to it (dlib's detectors have none)
}

struct AlertInfo: Identifiable {
    let id = UUID()
    let title: String
    let message: String
}

/// Keeps the daemon running to match the settings, and carries out what it reports.
@MainActor
final class Controller: ObservableObject {
    let store = SettingsStore()

    @Published private(set) var phase: Phase = .off
    @Published private(set) var statusText = "Not watching"
    @Published private(set) var detailText = ""
    @Published private(set) var cameras: [CameraInfo] = []
    @Published private(set) var models: [ModelInfo] = []
    @Published private(set) var gpuName: String?
    @Published private(set) var captureState: CaptureState = .idle
    @Published private(set) var previewImage: NSImage?
    @Published private(set) var referenceExists = false
    @Published private(set) var referenceImage: NSImage?  // nil when there's none, or it can't be read
    @Published var alert: AlertInfo?

    private static let backoffMin = 2.0, backoffMax = 60.0, restartDebounce = 0.8

    private var daemon: DaemonClient?
    private var capture: DaemonClient?
    private var actions: Actions!
    private var pausedFor = Set<String>()
    private var running = ""
    private var lastError: String?
    private var gpuWarned = false
    private var backoff = Controller.backoffMin
    private var enrolling = false
    private var restartTask: Task<Void, Never>?
    private var debounceTask: Task<Void, Never>?
    private var previous: SettingsData
    private var cancellables = Set<AnyCancellable>()
    private var observers: [(NotificationCenter, NSObjectProtocol)] = []
    private let logFile: FileHandle?

    init() {
        previous = store.data
        FileManager.default.createFile(atPath: Paths.log.path, contents: nil, attributes: nil)
        logFile = try? FileHandle(forWritingTo: Paths.log)
        _ = try? logFile?.seekToEnd()
        actions = Actions(store: store) { [weak self] on in self?.daemon?.send(on ? "track" : "untrack") }
        refreshReference()

        store.$data.dropFirst().sink { [weak self] new in
            DispatchQueue.main.async { self?.settingsChanged(to: new) }
        }.store(in: &cancellables)
        watchSystem()
        Notifier.requestPermission()
        Task { @MainActor in
            loadCameras()
            loadModels()
            sync()
        }
    }

    var iconName: String {
        switch phase {
        case .off: return "eye.slash"
        case .starting: return "eye"
        case .owner: return "checkmark.shield"
        case .absent: return "exclamationmark.shield"
        case .intruder: return "person.2"
        case .error: return "exclamationmark.triangle"
        }
    }

    func refreshReference() {
        referenceExists = FileManager.default.fileExists(atPath: Paths.reference.path)
        referenceImage = referenceExists ? NSImage(contentsOf: Paths.reference) : nil
    }

    var referenceStatus: String {
        if !referenceExists { return "No reference image yet" }
        return referenceImage == nil ? "The reference image can't be read. Set a new one." : "Reference image is set"
    }

    func shutdown() {
        restartTask?.cancel()
        debounceTask?.cancel()
        stopDaemon()
        capture?.stop()
        actions.destroy()
    }

    // MARK: Settings and system events

    private func settingsChanged(to new: SettingsData) {
        let old = previous
        previous = new
        if old.enabled != new.enabled {
            backoff = Self.backoffMin
            sync()
        } else if new.needsRestart(from: old) {
            debounceTask?.cancel()
            debounceTask = Task { @MainActor in
                try? await Task.sleep(for: .seconds(Self.restartDebounce))
                guard !Task.isCancelled else { return }
                backoff = Self.backoffMin
                sync()
            }
        }
    }

    /// The camera is off for as long as the screen is locked or asleep.
    private func watchSystem() {
        func watch(_ center: NotificationCenter, _ name: Notification.Name, _ reason: String, _ paused: Bool) {
            let token = center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.setPaused(reason, paused) }
            }
            observers.append((center, token))
        }
        let distributed: NotificationCenter = DistributedNotificationCenter.default()
        let workspace = NSWorkspace.shared.notificationCenter
        watch(distributed, Notification.Name("com.apple.screenIsLocked"), "locked", true)
        watch(distributed, Notification.Name("com.apple.screenIsUnlocked"), "locked", false)
        watch(workspace, NSWorkspace.screensDidSleepNotification, "display asleep", true)
        watch(workspace, NSWorkspace.screensDidWakeNotification, "display asleep", false)
        watch(workspace, NSWorkspace.willSleepNotification, "system asleep", true)
        watch(workspace, NSWorkspace.didWakeNotification, "system asleep", false)
    }

    private func setPaused(_ reason: String, _ paused: Bool) {
        if paused { pausedFor.insert(reason) } else { pausedFor.remove(reason) }
        backoff = Self.backoffMin
        sync()
    }

    // MARK: The daemon

    private func pythonPath() -> String {
        if !store.data.pythonPath.isEmpty { return store.data.pythonPath }
        if let path = ProcessInfo.processInfo.environment["FACEGUARD_PYTHON"], !path.isEmpty { return path }
        // The Python inside the app, with everything the daemon needs (see build-python-env.sh).
        if let url = Bundle.main.url(forResource: "python/bin/python3.12", withExtension: nil),
           FileManager.default.isExecutableFile(atPath: url.path) {
            return url.path
        }
        // build-app.sh records the interpreter of the virtual environment it was built beside.
        if let url = Bundle.main.url(forResource: "python-path", withExtension: "txt"),
           let text = try? String(contentsOf: url, encoding: .utf8) {
            let path = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !path.isEmpty { return path }
        }
        return "/usr/bin/python3"
    }

    private func daemonScript() -> String {
        if let url = Bundle.main.url(forResource: "daemon/faceguard_daemon", withExtension: "py") { return url.path }
        // Running from the source tree: the daemon is shared with the GNOME extension.
        return URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("extension/daemon/faceguard_daemon.py").path
    }

    private func daemonCommand(_ arguments: String...) -> [String] {
        [pythonPath(), daemonScript()] + arguments
    }

    private func modelArguments() -> [String] {
        let s = store.data
        return ["--model", s.model, "--compute", s.useGpu ? "gpu" : "cpu",
                "--detection-threshold", String(s.detectionThreshold)]
    }

    private func daemonArgv() -> [String] {
        let s = store.data
        var argv = daemonCommand(
            "--reference", Paths.reference.path, "--device", s.cameraDevice,
            "--interval-ms", String(s.intervalMs), "--min-face-px", String(s.minFacePx),
            "--absence-grace", String(s.absenceGraceS), "--intruder-grace", String(s.intruderGraceS))
        argv += modelArguments()
        // Without one set for this model, the daemon uses the model's own default.
        if let threshold = s.matchThresholds[s.model] { argv += ["--match-threshold", String(threshold)] }
        return argv
    }

    /// Starts or stops the daemon to match the settings, and shows why if it's off.
    func sync() {
        restartTask?.cancel()
        stopDaemon()
        guard store.data.enabled else { return setStatus(.off, "Not watching") }
        if enrolling { return setStatus(.off, "Paused while taking a reference photo") }
        if let reason = pausedFor.sorted().first { return setStatus(.off, "Paused: \(reason)") }
        guard FileManager.default.fileExists(atPath: Paths.reference.path) else {
            return showError("Set a reference image first")
        }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .denied, .restricted:
            return showError("Camera access is off. Allow Face Guard in System Settings, Privacy & Security, Camera.")
        case .notDetermined:
            setStatus(.starting, "Waiting for camera permission…")
            AVCaptureDevice.requestAccess(for: .video) { [weak self] _ in
                Task { @MainActor in self?.sync() }
            }
            return
        default:
            break
        }
        setStatus(.starting, "Starting…")
        do {
            daemon = try DaemonClient(
                argv: daemonArgv(), log: logFile,
                onEvent: { [weak self] in self?.onEvent($0) },
                onExit: { [weak self] in self?.onExit($0) })
        } catch {
            showError("Can't start the daemon: \(error.localizedDescription)")
        }
    }

    private func stopDaemon() {
        // Also closes the eyes, because a stopped daemon can't say the face has gone.
        actions.closeEyes()
        daemon?.stop()
        daemon = nil
    }

    private func onEvent(_ message: DaemonMessage) {
        switch message["event"] as? String {
        case "loading":
            setStatus(.starting, message["detail"] as? String ?? "Loading…")
        case "ready":
            lastError = nil
            backoff = Self.backoffMin
            let compute = (message["compute"] as? String ?? "cpu").uppercased()
            running = "\(message["model"] as? String ?? "") on the \(compute)"
            setStatus(.starting, "Watching with \(running)")
            if message["requested"] as? String == "gpu", message["compute"] as? String == "cpu", !gpuWarned {
                gpuWarned = true
                Notifier.post("Face Guard is running on the CPU", "Use GPU is on, but the GPU couldn't be used.")
            }
        case "status":
            showStatus(message)
        case "intruder_at":
            if let x = message["x"] as? Double, let y = message["y"] as? Double { actions.moveIntruder(x: x, y: y) }
        case "trigger":
            switch message["kind"] as? String {
            case "absent": actions.lock()
            case "intruder": actions.intruder(otherFaces: message["others"] as? Int ?? 1)
            case "clear": actions.clear()
            default: break
            }
        case "error":
            showError(message["message"] as? String ?? "The daemon reported an error")
        default:
            break
        }
    }

    private func showStatus(_ message: DaemonMessage) {
        let others = message["others"] as? Int ?? 0
        let match = (message["score"] as? Double).map { String(format: "match %.2f", $0) } ?? "no face seen"
        let rate = message["snap_rate"] as? Double ?? 0, fps = message["camera_fps"] as? Double ?? 0
        let speed = String(format: "%.1f snaps/s, camera %.0f fps", rate, fps) + " · \(running)"
        let state = message["state"] as? String
        let summary: String, phase: Phase
        switch state {
        case "intruder": (summary, phase) = ("You and \(others) other\(others > 1 ? "s" : "")", .intruder)
        case "absent": (summary, phase) = ("You're not recognized", .absent)
        default: (summary, phase) = ("You're here", .owner)
        }
        setStatus(phase, "\(summary) · \(match)\n\(speed)")
    }

    private func onExit(_ status: Int32) {
        daemon = nil
        actions.closeEyes()
        if status == DaemonClient.exitFatal { return }
        // While this is retrying nothing is being watched, so showError has already told the
        // user. Keep trying in case the camera comes back.
        setStatus(.error, "\(lastError ?? "The daemon stopped"). Retrying…")
        let delay = backoff
        backoff = min(backoff * 2, Self.backoffMax)
        restartTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(delay))
            guard !Task.isCancelled else { return }
            sync()
        }
    }

    private func setStatus(_ phase: Phase, _ text: String) {
        self.phase = phase
        let parts = text.split(separator: "\n", maxSplits: 1).map(String.init)
        statusText = parts.first ?? ""
        detailText = parts.count > 1 ? parts[1] : ""
    }

    /// Notifies once per distinct problem, because a menu bar icon is easy to miss.
    private func showError(_ text: String) {
        setStatus(.error, text)
        if text != lastError { Notifier.post("Face Guard isn't watching", text) }
        lastError = text
    }

    // MARK: Cameras and models, which only the daemon's Python can list

    func loadCameras() {
        DaemonClient.runOnce(argv: daemonCommand("--list-cameras")) { [weak self] message in
            guard message["event"] as? String == "cameras",
                  let list = message["cameras"] as? [[String: Any]] else { return }
            self?.cameras = list.compactMap { item in
                guard let path = item["path"] as? String, let name = item["name"] as? String else { return nil }
                return CameraInfo(id: path, name: name, virtual: item["virtual"] as? Bool ?? false)
            }
        }
    }

    func loadModels() {
        DaemonClient.runOnce(argv: daemonCommand("--list-models")) { [weak self] message in
            guard message["event"] as? String == "models", let list = message["models"] as? [[String: Any]] else { return }
            self?.gpuName = message["gpu"] as? String
            self?.models = list.compactMap { item in
                guard item["installed"] as? Bool == true, let id = item["id"] as? String,
                      let label = item["label"] as? String else { return nil }
                return ModelInfo(id: id, label: label, downloaded: item["downloaded"] as? Bool ?? false,
                                 gpu: item["gpu"] as? Bool ?? false,
                                 defaultMatch: item["default_match_threshold"] as? Double ?? 0.4,
                                 usesDetection: item["uses_detection_threshold"] as? Bool ?? true)
            }
        }
    }

    // MARK: The reference photo

    func chooseReference() {
        let panel = NSOpenPanel()
        panel.message = "Choose a photo with only your face in it"
        panel.allowedContentTypes = [.image]
        panel.allowsMultipleSelection = false
        NSApp.activate(ignoringOtherApps: true)
        if panel.runModal() == .OK, let url = panel.url { enroll(path: url.path, deleteAfter: false) }
    }

    func takeReference() {
        guard !enrolling else { return }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .denied, .restricted:
            alert = AlertInfo(title: "Camera access is off",
                              message: "Allow Face Guard in System Settings, Privacy & Security, Camera.")
            return
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                Task { @MainActor in if granted { self?.takeReference() } }
            }
            return
        default:
            break
        }
        enrolling = true
        captureState = .starting
        previewImage = nil
        sync()  // the camera has one user at a time
        do {
            capture = try DaemonClient(
                argv: daemonCommand("--capture", "--device", store.data.cameraDevice), log: logFile,
                onEvent: { [weak self] in self?.onCaptureEvent($0) },
                onExit: { [weak self] _ in self?.captureFailed("The camera stopped.") })
        } catch {
            captureFailed("Can't start the daemon: \(error.localizedDescription)")
        }
    }

    func snap() { capture?.send("snap") }

    func cancelCapture() {
        capture?.stop()
        capture = nil
        captureState = .idle
        enrolling = false
        sync()
    }

    private func onCaptureEvent(_ message: DaemonMessage) {
        switch message["event"] as? String {
        case "ready":
            captureState = .ready
        case "frame":
            if let path = message["path"] as? String { previewImage = NSImage(contentsOfFile: path) ?? previewImage }
        case "captured":
            guard let path = message["path"] as? String else { return }
            captureState = .checking
            capture?.stop()
            capture = nil
            enroll(path: path, deleteAfter: true)
        case "error":
            captureFailed(message["message"] as? String ?? "The camera failed.")
        default:
            break
        }
    }

    private func captureFailed(_ text: String) {
        capture?.stop()
        capture = nil
        captureState = .idle
        enrolling = false
        alert = AlertInfo(title: "Couldn't take the photo", message: text)
        sync()
    }

    private func enroll(path: String, deleteAfter: Bool) {
        enrolling = true
        sync()
        var outcome: DaemonMessage = [:]
        DaemonClient.runOnce(
            argv: daemonCommand("--enroll", path, "--reference", Paths.reference.path) + modelArguments(),
            onMessage: { outcome = $0 },
            onDone: { [weak self] _ in
                guard let self else { return }
                if deleteAfter { try? FileManager.default.removeItem(atPath: path) }
                captureState = .idle
                enrolling = false
                refreshReference()
                if outcome["event"] as? String == "enrolled" {
                    Notifier.post("Reference photo saved", "Face Guard will recognize you from this photo.")
                } else {
                    alert = AlertInfo(title: "Couldn't use that photo",
                                      message: outcome["message"] as? String ?? "The daemon stopped without a reason.")
                }
                sync()
            })
    }
}
