import SwiftUI

/// The popup under the menu bar icon, laid out like the GNOME panel menu.
struct MenuView: View {
    @ObservedObject var controller: Controller
    @ObservedObject private var store: SettingsStore
    @Environment(\.openWindow) private var openWindow

    init(controller: Controller) {
        self.controller = controller
        store = controller.store
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(controller.statusText)
                if !controller.detailText.isEmpty { Text(controller.detailText) }
            }
            .font(.callout)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

            Divider()
            Toggle("Watch camera", isOn: $store.data.enabled)
                .toggleStyle(.switch)
            Toggle(isOn: Binding(get: { controller.collaboration }, set: { controller.setCollaboration($0) })) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Allow collaboration")
                    Text(controller.collaboration
                         ? "Extra face actions are off. It still locks if you leave."
                         : "Control-Option-C")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .toggleStyle(.switch)
            Divider()
            Button("Settings") {
                NSApp.activate(ignoringOtherApps: true)
                openWindow(id: "settings")
            }
            .buttonStyle(.plain)
            Button("Quit Face Guard") {
                controller.shutdown()
                NSApp.terminate(nil)
            }
            .buttonStyle(.plain)
        }
        .padding(14)
        .frame(width: 340, alignment: .leading)
    }
}
