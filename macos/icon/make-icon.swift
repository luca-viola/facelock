// Draws the Face Guard icon at every size macOS wants and builds FaceGuard.icns.
// Usage: swift make-icon.swift        (needs iconutil, which comes with macOS)
import AppKit

func color(_ hex: UInt32, _ alpha: CGFloat = 1) -> CGColor {
    CGColor(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: alpha)
}

func gradient(_ top: UInt32, _ bottom: UInt32) -> CGGradient {
    CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: [color(top), color(bottom)] as CFArray,
               locations: [0, 1])!
}

/// Everything is drawn on a 1024 point canvas with y pointing up, then scaled to the wanted size.
func draw(_ ctx: CGContext, pixels: Int) {
    ctx.scaleBy(x: CGFloat(pixels) / 1024, y: CGFloat(pixels) / 1024)

    // The rounded square, on macOS's icon grid: 824 points inside a 1024 canvas.
    let body = CGRect(x: 100, y: 100, width: 824, height: 824)
    let square = CGPath(roundedRect: body, cornerWidth: 186, cornerHeight: 186, transform: nil)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -14), blur: 28, color: color(0x000000, 0.35))
    ctx.addPath(square)
    ctx.setFillColor(color(0x0B1F4B))
    ctx.fillPath()
    ctx.restoreGState()
    ctx.saveGState()
    ctx.addPath(square)
    ctx.clip()
    ctx.drawLinearGradient(gradient(0x3B82F6, 0x0B2A6B), start: CGPoint(x: 512, y: 924), end: CGPoint(x: 512, y: 100),
                           options: [])
    // A soft light from the top.
    ctx.drawRadialGradient(
        CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                   colors: [color(0xFFFFFF, 0.22), color(0xFFFFFF, 0)] as CFArray, locations: [0, 1])!,
        startCenter: CGPoint(x: 512, y: 960), startRadius: 0, endCenter: CGPoint(x: 512, y: 960), endRadius: 620,
        options: [])
    ctx.restoreGState()

    // The shield (y up, so the point is at the bottom).
    let shield = CGMutablePath()
    shield.move(to: CGPoint(x: 512, y: 810))
    shield.addCurve(to: CGPoint(x: 752, y: 735), control1: CGPoint(x: 590, y: 755), control2: CGPoint(x: 680, y: 735))
    shield.addLine(to: CGPoint(x: 752, y: 555))
    shield.addCurve(to: CGPoint(x: 512, y: 220), control1: CGPoint(x: 752, y: 385), control2: CGPoint(x: 640, y: 285))
    shield.addCurve(to: CGPoint(x: 272, y: 555), control1: CGPoint(x: 384, y: 285), control2: CGPoint(x: 272, y: 385))
    shield.addLine(to: CGPoint(x: 272, y: 735))
    shield.addCurve(to: CGPoint(x: 512, y: 810), control1: CGPoint(x: 344, y: 735), control2: CGPoint(x: 434, y: 755))
    shield.closeSubpath()

    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -10), blur: 22, color: color(0x021030, 0.45))
    ctx.addPath(shield)
    ctx.setFillColor(color(0xFFFFFF))
    ctx.fillPath()
    ctx.restoreGState()
    ctx.saveGState()
    ctx.addPath(shield)
    ctx.clip()
    ctx.drawLinearGradient(gradient(0xFFFFFF, 0xCFE0FF), start: CGPoint(x: 512, y: 810), end: CGPoint(x: 512, y: 220),
                           options: [])
    ctx.restoreGState()

    // The eye, a little above the middle of the shield.
    let cx: CGFloat = 512, cy: CGFloat = 520
    let eye = CGMutablePath()
    eye.move(to: CGPoint(x: cx - 165, y: cy))
    eye.addCurve(to: CGPoint(x: cx + 165, y: cy), control1: CGPoint(x: cx - 95, y: cy + 112),
                 control2: CGPoint(x: cx + 95, y: cy + 112))
    eye.addCurve(to: CGPoint(x: cx - 165, y: cy), control1: CGPoint(x: cx + 95, y: cy - 112),
                 control2: CGPoint(x: cx - 95, y: cy - 112))
    eye.closeSubpath()
    ctx.addPath(eye)
    ctx.setFillColor(color(0x0B2A6B))
    ctx.fillPath()

    ctx.saveGState()
    ctx.addPath(eye)
    ctx.clip()
    let iris = CGRect(x: cx - 74, y: cy - 74, width: 148, height: 148)
    ctx.addEllipse(in: iris)
    ctx.clip()
    ctx.drawLinearGradient(gradient(0x93C5FD, 0x2563EB), start: CGPoint(x: cx, y: cy + 74), end: CGPoint(x: cx, y: cy - 74),
                           options: [])
    ctx.restoreGState()
    ctx.setFillColor(color(0x041033))
    ctx.fillEllipse(in: CGRect(x: cx - 34, y: cy - 34, width: 68, height: 68))
    ctx.setFillColor(color(0xFFFFFF, 0.95))
    ctx.fillEllipse(in: CGRect(x: cx + 10, y: cy + 12, width: 24, height: 24))
}

func render(pixels: Int) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    let context = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    draw(context.cgContext, pixels: pixels)
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

let here = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent()
let iconset = here.appendingPathComponent("FaceGuard.iconset")
try? FileManager.default.removeItem(at: iconset)
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)
for (name, pixels) in [("16x16", 16), ("16x16@2x", 32), ("32x32", 32), ("32x32@2x", 64), ("128x128", 128),
                       ("128x128@2x", 256), ("256x256", 256), ("256x256@2x", 512), ("512x512", 512),
                       ("512x512@2x", 1024)] {
    try render(pixels: pixels).write(to: iconset.appendingPathComponent("icon_\(name).png"))
}
let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
process.arguments = ["-c", "icns", iconset.path, "-o", here.appendingPathComponent("FaceGuard.icns").path]
try process.run()
process.waitUntilExit()
try? FileManager.default.removeItem(at: iconset)
print("Wrote FaceGuard.icns")
