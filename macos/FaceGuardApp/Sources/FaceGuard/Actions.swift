import AppKit

/// Carries out what a trigger from the daemon asks for.
@MainActor
final class Actions {
    private let store: SettingsStore
    private let setTracking: (Bool) -> Void
    private var eyes: Eyes?
    private var intruderAt: (x: Double, y: Double) = (0.5, 0.5)
    private var hidden: [String] = []  // bundle identifiers of the apps hidden by an intruder
    private var finderCollapsed = false

    /// setTracking(true) asks the daemon to snap at full speed, for the eyes to follow.
    init(store: SettingsStore, setTracking: @escaping (Bool) -> Void) {
        self.store = store
        self.setTracking = setTracking
    }

    /// Leaves hidden apps hidden, which is the safe side after a lock.
    func destroy() {
        closeEyes()
        hidden.removeAll()
    }

    func lock() {
        if let symbol = Self.lockSymbol {
            _ = symbol()
            return
        }
        // Falls back to sleeping the display, which locks only if the password is required immediately.
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/pmset")
        process.arguments = ["displaysleepnow"]
        do { try process.run() } catch { Notifier.post("Face Guard", "Can't lock the screen: \(error.localizedDescription)") }
    }

    /// macOS has no public API for locking the screen.
    private static let lockSymbol: (@convention(c) () -> Int32)? = {
        guard let library = dlopen("/System/Library/PrivateFrameworks/login.framework/login", RTLD_NOW),
              let symbol = dlsym(library, "SACLockScreenImmediate") else { return nil }
        return unsafeBitCast(symbol, to: (@convention(c) () -> Int32).self)
    }()

    func intruder(otherFaces: Int) {
        hideApps()
        switch store.data.intruderAction {
        case "lock": lock()
        case "command": runCommand(otherFaces: otherFaces)
        case "notify": Notifier.post("Face Guard", "Someone else is looking at your screen.")
        case "eyes": showEyes()
        default: break
        }
    }

    /// Where the other face is in the camera image, from 0 to 1 on each axis.
    func moveIntruder(x: Double, y: Double) {
        intruderAt = (x, y)
        eyes?.lookAt(x: x, y: y)
    }

    func closeEyes() {
        guard let current = eyes else { return }
        current.destroy()
        eyes = nil
        setTracking(false)
    }

    /// The other face left.
    func clear() {
        closeEyes()
        restoreApps()
    }

    // Dismissing only closes the eyes. They come back because the daemon triggers once per
    // episode, so the next trigger means the face left and returned.
    private func showEyes() {
        guard eyes == nil else { return }
        let new = Eyes { [weak self] in self?.closeEyes() }
        new.lookAt(x: intruderAt.x, y: intruderAt.y)
        eyes = new
        setTracking(true)
    }

    // MARK: Hiding apps

    /// The chosen apps, or every open app with a Dock icon (except this one and Finder, which
    /// can't be hidden) when "all open apps" is on.
    private func appsToHide() -> [String] {
        var chosen = store.data.minimizeApps
        guard store.data.minimizeAll else { return chosen }
        let skip: Set<String> = ["com.apple.finder", Bundle.main.bundleIdentifier ?? ""]
        for app in NSWorkspace.shared.runningApplications where app.activationPolicy == .regular {
            if let id = app.bundleIdentifier, !skip.contains(id), !chosen.contains(id) { chosen.append(id) }
        }
        return chosen
    }

    private func hideApps() {
        for id in appsToHide() {
            for app in NSRunningApplication.runningApplications(withBundleIdentifier: id) where !app.isHidden {
                app.hide()  // returns false even when it works, because it only asks
                if !hidden.contains(id) { hidden.append(id) }
            }
        }
        systemEvents(hidden, visible: false)
        if store.data.minimizeAll { finderWindows(minimize: true) }
    }

    private func restoreApps() {
        let apps = hidden
        hidden = []
        guard store.data.minimizeRestore else {
            finderCollapsed = false
            return
        }
        finderWindows(minimize: false)
        for id in apps {
            for app in NSRunningApplication.runningApplications(withBundleIdentifier: id) where app.isHidden {
                app.unhide()  // not if the user has already brought it back
            }
        }
        systemEvents(apps, visible: true)
    }

    /// Hides or shows every one of these apps through System Events as well, on top of the normal
    /// request. Some apps, such as Edge, ignore hide() and unhide() but obey this, and doing it
    /// for all of them means no app has to be singled out. macOS asks for the Automation permission.
    private func systemEvents(_ ids: [String], visible: Bool) {
        guard !ids.isEmpty else { return }
        let script = """
        on run argv
        set wanted to (item 1 of argv) is "true"
        tell application "System Events"
        repeat with bundleId in (rest of argv)
        try
        set visible of (every process whose bundle identifier is bundleId) to wanted
        end try
        end repeat
        end tell
        end run
        """
        Self.osascript(script, arguments: [visible ? "true" : "false"] + ids)
    }

    /// Finder can't be hidden, so its windows are minimized. Needs the Automation permission for Finder.
    private func finderWindows(minimize: Bool) {
        if minimize {
            let script = """
            tell application "Finder"
            if (count of windows) is 0 then return "none"
            set collapsed of every window to true
            return "done"
            end tell
            """
            Self.osascript(script) { [weak self] output in
                if output == "done" { Task { @MainActor in self?.finderCollapsed = true } }
            }
        } else if finderCollapsed {
            finderCollapsed = false
            Self.osascript("tell application \"Finder\" to set collapsed of every window to false")
        }
    }

    private nonisolated static func osascript(_ script: String, arguments: [String] = [],
                                              done: (@Sendable (String) -> Void)? = nil) {
        DispatchQueue.global().async {
            let process = Process()
            let output = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            process.arguments = ["-e", script] + arguments
            process.standardOutput = output
            process.standardError = FileHandle.nullDevice
            do { try process.run() } catch { return }
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            done?(String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines))
        }
    }

    // MARK: Command

    private func runCommand(otherFaces: Int) {
        let command = store.data.intruderCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !command.isEmpty else {
            Notifier.post("Face Guard", "Another face appeared, but no command is configured.")
            return
        }
        let process = Process()
        let errors = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = ["-c", command]
        process.currentDirectoryURL = Paths.home
        process.environment = ProcessInfo.processInfo.environment.merging(
            ["FACEGUARD_OTHER_FACES": String(otherFaces)]) { _, new in new }
        process.standardError = errors
        process.terminationHandler = { finished in
            guard finished.terminationStatus != 0 else { return }
            let text = String(decoding: errors.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            Notifier.post("Face Guard", "The command failed (\(finished.terminationStatus)): \(String(text.prefix(200)))")
        }
        do { try process.run() } catch {
            Notifier.post("Face Guard", "Can't run the command: \(error.localizedDescription)")
        }
    }
}
