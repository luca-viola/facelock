import Foundation

typealias DaemonMessage = [String: Any]

/// Runs the Python daemon and reports its JSON-line events on the main queue.
final class DaemonClient: @unchecked Sendable {
    static let exitFatal: Int32 = 4  // the daemon's "restarting won't help" exit code

    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()
    private var buffer = Data()
    private var stopped = false
    private let onEvent: (DaemonMessage) -> Void
    private let onExit: (Int32) -> Void

    init(argv: [String], log: FileHandle?,
         onEvent: @escaping (DaemonMessage) -> Void, onExit: @escaping (Int32) -> Void) throws {
        self.onEvent = onEvent
        self.onExit = onExit
        process.executableURL = URL(fileURLWithPath: argv[0])
        process.arguments = Array(argv.dropFirst())
        process.standardInput = input
        process.standardOutput = output
        process.standardError = log ?? FileHandle.nullDevice
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
            } else {
                self?.consume(data)
            }
        }
        process.terminationHandler = { [weak self] finished in
            let status = finished.terminationStatus
            DispatchQueue.main.async {
                guard let self, !self.stopped else { return }
                self.onExit(status)
            }
        }
        try process.run()
    }

    private func consume(_ data: Data) {
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 10) {
            let line = buffer[buffer.startIndex..<newline]
            buffer.removeSubrange(buffer.startIndex...newline)
            guard let message = (try? JSONSerialization.jsonObject(with: line)) as? DaemonMessage else { continue }
            DispatchQueue.main.async { [weak self] in
                guard let self, !self.stopped else { return }
                self.onEvent(message)
            }
        }
    }

    /// Sends one command line. The daemon may have just exited, which is fine.
    func send(_ line: String) {
        try? input.fileHandleForWriting.write(contentsOf: Data((line + "\n").utf8))
    }

    /// Ends the daemon without calling onExit. Closing stdin lets it release the camera first.
    func stop() {
        stopped = true
        try? input.fileHandleForWriting.close()
        let process = self.process
        DispatchQueue.global().async {
            for _ in 0..<30 where process.isRunning { Thread.sleep(forTimeInterval: 0.1) }
            if process.isRunning { process.terminate() }
        }
    }

    /// Runs a one-shot daemon mode in the background, such as --list-cameras. onMessage runs
    /// for every event and onDone after the daemon exits, both on the main queue.
    static func runOnce(argv: [String], onMessage: @escaping (DaemonMessage) -> Void,
                        onDone: ((Int32) -> Void)? = nil) {
        DispatchQueue.global().async {
            let process = Process()
            let output = Pipe()
            process.executableURL = URL(fileURLWithPath: argv[0])
            process.arguments = Array(argv.dropFirst())
            process.standardOutput = output
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
            } catch {
                DispatchQueue.main.async {
                    onMessage(["event": "error", "message": "\(error.localizedDescription)", "retryable": false])
                }
                return
            }
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let status = process.terminationStatus
            let messages = data.split(separator: 10).compactMap {
                (try? JSONSerialization.jsonObject(with: $0)) as? DaemonMessage
            }
            DispatchQueue.main.async {
                messages.forEach(onMessage)
                onDone?(status)
            }
        }
    }
}
