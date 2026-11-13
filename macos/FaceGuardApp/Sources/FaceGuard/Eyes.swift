import AppKit

/// Where the eyes' pupils point. Pure math, ported from the GNOME extension's gaze.js.
enum Gaze {
    /// How far in front of the screen the other person is assumed to be, in screen widths.
    static let depthWidths = 0.5
    /// Stretches positions past the screen edges, so that a face at the side of the camera
    /// image turns every eye that way, even the eyes already on that side of the screen.
    static let spread = 2.0

    /// A position in the camera image (0 to 1) as screen coordinates, y down. The camera faces
    /// the user, so someone on the left of its image is on the right of the screen.
    static func cameraToScreen(x: Double, y: Double, width: Double, height: Double) -> CGPoint {
        CGPoint(x: width / 2 + (0.5 - x) * spread * width, y: (y - 0.5) * spread * height)
    }

    static func pupilOffset(eye: CGPoint, target: CGPoint, rangeX: Double, rangeY: Double,
                            width: Double) -> CGPoint {
        let dx = target.x - eye.x, dy = target.y - eye.y
        let distance = (dx * dx + dy * dy + pow(width * depthWidths, 2)).squareRoot()
        return CGPoint(x: dx / distance * rangeX, y: dy / distance * rangeY)
    }
}

private struct Pupil {
    var x: Double, y: Double  // where it is
    var targetX: Double, targetY: Double  // where it's going
    let radius: Double
}

private final class EyesWindow: NSWindow {
    var onDismiss: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { onDismiss?() } else { super.keyDown(with: event) }
    }
}

private final class EyesView: NSView {
    var eyes: [CGRect] = []  // in view coordinates, y down
    var pupils: [Pupil] = []
    var onDismiss: (() -> Void)?
    static let outline = 0.09  // relative to an eye's width

    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    @objc func dismiss(_ sender: Any?) { onDismiss?() }

    override func mouseDown(with event: NSEvent) {
        guard event.clickCount == 2 else { return }
        let point = convert(event.locationInWindow, from: nil)
        for eye in eyes {
            let nx = (point.x - eye.midX) / (eye.width / 2), ny = (point.y - eye.midY) / (eye.height / 2)
            if nx * nx + ny * ny <= 1 { onDismiss?(); return }
        }
    }

    override func draw(_ dirtyRect: NSRect) {
        for (eye, pupil) in zip(eyes, pupils) {
            let outline = eye.width * Self.outline
            NSColor.black.set()
            NSBezierPath(ovalIn: eye).fill()
            NSColor.white.set()
            NSBezierPath(ovalIn: eye.insetBy(dx: outline, dy: outline)).fill()
            NSColor.black.set()
            NSBezierPath(ovalIn: CGRect(x: pupil.x - pupil.radius, y: pupil.y - pupil.radius,
                                        width: pupil.radius * 2, height: pupil.radius * 2)).fill()
        }
    }

    /// Moves each pupil toward its target.
    func step() {
        var moved = false
        for index in pupils.indices {
            let dx = pupils[index].targetX - pupils[index].x, dy = pupils[index].targetY - pupils[index].y
            if abs(dx) < 0.5 && abs(dy) < 0.5 { continue }
            pupils[index].x += dx * 0.3
            pupils[index].y += dy * 0.3
            moved = true
        }
        if moved { needsDisplay = true }
    }

    func jump() {
        for index in pupils.indices {
            pupils[index].x = pupils[index].targetX
            pupils[index].y = pupils[index].targetY
        }
        needsDisplay = true
    }
}

/// A pair of giant eyes in the middle of the main screen, looking at someone in the camera image.
/// The window is only as big as the eyes and the Dismiss button, so the rest of the screen stays
/// usable. Double-clicking an eye, the button and Esc all dismiss them.
@MainActor
final class Eyes {
    private static let eyeHeight = 0.55  // share of the screen's height
    private static let eyeAspect = 0.7  // width over height
    private static let gap = 0.08  // between the eyes, relative to an eye's width
    private static let pupilSize = 0.3  // pupil diameter, relative to an eye's width
    private static let pupilTravel = 0.9  // keeps a pupil from touching the outline
    private static let buttonGap = 24.0
    private static let buttonSize = CGSize(width: 150, height: 40)

    private let window: EyesWindow
    private let view = EyesView()
    private var timer: Timer?
    private let screenSize: CGSize
    private let origin: CGPoint
    private var ranges: [(x: Double, y: Double)] = []
    private var gaze = (x: 0.5, y: 0.5)

    init(onDismiss: @escaping () -> Void) {
        let screen = NSScreen.screens[0]  // the one with the menu bar
        let frame = screen.frame
        screenSize = frame.size
        let height = frame.height * Self.eyeHeight
        let width = height * Self.eyeAspect
        let gap = width * Self.gap
        let totalWidth = 2 * width + gap
        let totalHeight = height + Self.buttonGap + Self.buttonSize.height
        origin = CGPoint(x: (frame.width - totalWidth) / 2, y: (frame.height - totalHeight) / 2)

        let radius = width * Self.pupilSize / 2
        let centers = [CGPoint(x: width / 2, y: height / 2), CGPoint(x: width * 1.5 + gap, y: height / 2)]
        view.eyes = centers.map { CGRect(x: $0.x - width / 2, y: $0.y - height / 2, width: width, height: height) }
        view.pupils = centers.map { Pupil(x: $0.x, y: $0.y, targetX: $0.x, targetY: $0.y, radius: radius) }
        let inset = width * EyesView.outline + radius
        ranges = centers.map { _ in ((width / 2 - inset) * Self.pupilTravel, (height / 2 - inset) * Self.pupilTravel) }
        view.frame = NSRect(x: 0, y: 0, width: totalWidth, height: totalHeight)
        view.onDismiss = onDismiss

        let button = NSButton(title: "Dismiss", target: view, action: #selector(EyesView.dismiss(_:)))
        button.bezelStyle = .rounded
        button.frame = NSRect(x: (totalWidth - Self.buttonSize.width) / 2, y: height + Self.buttonGap,
                              width: Self.buttonSize.width, height: Self.buttonSize.height)
        view.addSubview(button)

        window = EyesWindow(
            contentRect: NSRect(x: frame.minX + origin.x, y: frame.minY + frame.height - origin.y - totalHeight,
                                width: totalWidth, height: totalHeight),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.onDismiss = onDismiss
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .screenSaver
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isReleasedWhenClosed = false
        window.contentView = view

        aim(instant: true)
        window.orderFrontRegardless()
        window.makeKey()
        let timer = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak view] _ in view?.step() }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    func lookAt(x: Double, y: Double) {
        gaze = (x, y)
        aim(instant: false)
    }

    private func aim(instant: Bool) {
        let target = Gaze.cameraToScreen(x: gaze.x, y: gaze.y, width: screenSize.width, height: screenSize.height)
        for index in view.pupils.indices {
            let eye = view.eyes[index]
            let offset = Gaze.pupilOffset(
                eye: CGPoint(x: origin.x + eye.midX, y: origin.y + eye.midY), target: target,
                rangeX: ranges[index].x, rangeY: ranges[index].y, width: screenSize.width)
            view.pupils[index].targetX = eye.midX + offset.x
            view.pupils[index].targetY = eye.midY + offset.y
        }
        if instant { view.jump() }
    }

    func destroy() {
        timer?.invalidate()
        window.orderOut(nil)
        window.close()
    }
}
