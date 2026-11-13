// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "FaceGuard",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "FaceGuard",
            path: "Sources/FaceGuard",
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
