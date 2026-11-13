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
            SwitchRow(title: "Watch camera", isOn: $store.data.enabled)
            SwitchRow(
                title: "Allow collaboration",
                subtitle: controller.collaboration
                    ? "Extra face actions are off. It still locks if you leave."
                    : "Control-Option-C",
                isOn: Binding(get: { controller.collaboration }, set: { controller.setCollaboration($0) }))
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

/// A label on the left and its switch on the right, like the GNOME panel menu's switch items.
/// Clicking the label flips the switch too.
struct SwitchRow: View {
    let title: String
    var subtitle: String?
    @Binding var isOn: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .onTapGesture { isOn.toggle() }
            Toggle("", isOn: $isOn)
                .labelsHidden()
                .toggleStyle(.switch)
        }
    }
}
