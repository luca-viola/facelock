import AppKit

/// The menu bar icons. "You're here" and "you're not recognized" are the same shield shapes as
/// the GNOME panel's security-high and security-low icons, drawn here because macOS has no such
/// icons: a filled shield with a thin shield cut into it, and a plain outline. The others use
/// SF Symbols, and "someone else is looking" is two people on both platforms.
enum StatusIcons {
    private static let size = NSSize(width: 18, height: 18)

    static func image(for phase: Phase) -> NSImage {
        switch phase {
        case .owner: return ownerShield
        case .absent: return outlineShield
        case .intruder: return symbol("person.2", "Someone else is looking")
        case .off: return symbol("eye.slash", "Not watching")
        case .starting: return symbol("eye", "Starting")
        case .error: return symbol("exclamationmark.triangle", "Face Guard isn't watching")
        }
    }

    private static func symbol(_ name: String, _ description: String) -> NSImage {
        let image = NSImage(systemSymbolName: name, accessibilityDescription: description) ?? NSImage()
        image.isTemplate = true
        return image
    }

    private static let ownerShield = template("You're here") { bounds in
        NSColor.black.setFill()
        shield(in: bounds.insetBy(dx: 1.8, dy: 0.5)).fill()
        // A thin shield cut out of the fill, so the icon reads at 18 points.
        NSGraphicsContext.current?.compositingOperation = .destinationOut
        let inner = shield(in: bounds.insetBy(dx: 4.6, dy: 3.3))
        inner.lineWidth = 1.1
        inner.lineJoinStyle = .round
        inner.stroke()
    }

    private static let outlineShield = template("You're not recognized") { bounds in
        NSColor.black.setStroke()
        let outline = shield(in: bounds.insetBy(dx: 2.6, dy: 1.25))
        outline.lineWidth = 1.5
        outline.lineJoinStyle = .round
        outline.stroke()
    }

    private static func template(_ description: String, draw: @escaping (NSRect) -> Void) -> NSImage {
        let image = NSImage(size: size, flipped: false) { bounds in
            draw(bounds)
            return true
        }
        image.isTemplate = true
        image.accessibilityDescription = description
        return image
    }

    /// The shield of the app icon, fitted to a rectangle (y up).
    private static func shield(in rect: NSRect) -> NSBezierPath {
        func point(_ x: CGFloat, _ y: CGFloat) -> NSPoint {
            NSPoint(x: rect.minX + (x - 272) / 480 * rect.width, y: rect.minY + (y - 220) / 590 * rect.height)
        }
        let path = NSBezierPath()
        path.move(to: point(512, 810))
        path.curve(to: point(752, 735), controlPoint1: point(590, 755), controlPoint2: point(680, 735))
        path.line(to: point(752, 555))
        path.curve(to: point(512, 220), controlPoint1: point(752, 385), controlPoint2: point(640, 285))
        path.curve(to: point(272, 555), controlPoint1: point(384, 285), controlPoint2: point(272, 385))
        path.line(to: point(272, 735))
        path.curve(to: point(512, 810), controlPoint1: point(344, 735), controlPoint2: point(434, 755))
        path.close()
        return path
    }
}
