import SwiftUI
import AppKit

struct InstalledApp: Identifiable, Hashable {
    let id: String  // bundle identifier
    let name: String
    let path: String
}

/// The apps in the usual places, to pick the ones to hide.
struct AppPicker: View {
    @Environment(\.dismiss) private var dismiss
    let chosen: Binding<[String]>
    @State private var apps: [InstalledApp] = []
    @State private var search = ""

    init(chosen: Binding<[String]>) { self.chosen = chosen }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Add App").font(.headline)
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            .padding(16)
            TextField("Search", text: $search).textFieldStyle(.roundedBorder).padding(.horizontal, 16)
            List(filtered) { app in
                Button {
                    if !chosen.wrappedValue.contains(app.id) { chosen.wrappedValue.append(app.id) }
                    dismiss()
                } label: {
                    HStack(spacing: 10) {
                        Image(nsImage: NSWorkspace.shared.icon(forFile: app.path)).resizable().frame(width: 28, height: 28)
                        Text(app.name)
                        Spacer()
                        if chosen.wrappedValue.contains(app.id) { Image(systemName: "checkmark").foregroundStyle(.secondary) }
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .frame(width: 420, height: 560)
        .task { apps = await Task.detached { Self.scan() }.value }
    }

    private var filtered: [InstalledApp] {
        search.isEmpty ? apps : apps.filter { $0.name.localizedCaseInsensitiveContains(search) }
    }

    private nonisolated static func scan() -> [InstalledApp] {
        let folders = ["/Applications", "/Applications/Utilities", "/System/Applications",
                       "/System/Applications/Utilities", NSHomeDirectory() + "/Applications"]
        var found: [String: InstalledApp] = [:]
        for folder in folders {
            for name in (try? FileManager.default.contentsOfDirectory(atPath: folder)) ?? [] where name.hasSuffix(".app") {
                let path = folder + "/" + name
                guard let id = Bundle(path: path)?.bundleIdentifier, id != "com.apple.finder" else { continue }
                found[id] = InstalledApp(id: id, name: String(name.dropLast(4)), path: path)
            }
        }
        return found.values.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }
}
