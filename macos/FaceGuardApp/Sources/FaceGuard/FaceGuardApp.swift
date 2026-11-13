import SwiftUI

@main
struct FaceGuardApp: App {
    @StateObject private var controller = Controller()

    init() {
        // Writing to a daemon that has just exited must not kill the app.
        signal(SIGPIPE, SIG_IGN)
    }

    var body: some Scene {
        MenuBarExtra {
            MenuView(controller: controller)
        } label: {
            Image(nsImage: controller.statusImage)
        }
        .menuBarExtraStyle(.window)

        Window("Face Guard", id: "settings") {
            SettingsView(controller: controller)
        }
        .defaultSize(width: 620, height: 1000)
        .windowResizability(.contentMinSize)
    }
}
