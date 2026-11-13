import SwiftUI

/// The Settings window: one page of grouped rows, like the GNOME preferences.
struct SettingsView: View {
    @ObservedObject var controller: Controller
    @ObservedObject private var store: SettingsStore
    @State private var addingApp = false

    init(controller: Controller) {
        self.controller = controller
        store = controller.store
    }

    private var data: Binding<SettingsData> { $store.data }
    private var model: ModelInfo? { controller.models.first { $0.id == store.data.model } }

    var body: some View {
        Form {
            yourFace
            camera
            recognition
            someoneElse
            minimizeApps
            advanced
        }
        .formStyle(.grouped)
        .frame(minWidth: 560, minHeight: 520)
        .sheet(isPresented: Binding(get: { controller.captureState != .idle }, set: { _ in })) {
            ReferenceSheet(controller: controller)
        }
        .sheet(isPresented: $addingApp) { AppPicker(chosen: data.minimizeApps) }
        .alert(item: $controller.alert) { Alert(title: Text($0.title), message: Text($0.message)) }
        .onAppear {
            controller.loadCameras()
            controller.loadModels()
            controller.refreshReference()
        }
    }

    // MARK: Groups

    private var yourFace: some View {
        Section {
            HStack {
                Text(controller.referenceStatus)
                Spacer()
                Button("Take Photo") { controller.takeReference() }
                Button("Choose File") { controller.chooseReference() }
            }
            Toggle("Watch camera", isOn: data.enabled)
            if let image = controller.referenceImage {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(height: 200)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .frame(maxWidth: .infinity)
                    .accessibilityLabel("Your reference image")
            }
        } header: {
            header("Your face", "The image every camera snap is compared to. It must show only your face.")
        }
    }

    private var camera: some View {
        Section {
            Picker("Device", selection: data.cameraDevice) {
                Text("Automatic").tag("auto")
                ForEach(controller.cameras) { camera in
                    Text(camera.name + (camera.virtual ? " (virtual)" : "")).tag(camera.id)
                }
                // Keeps a camera that is unplugged right now from being silently dropped.
                if store.data.cameraDevice != "auto",
                   !controller.cameras.contains(where: { $0.id == store.data.cameraDevice }) {
                    Text("Unavailable camera").tag(store.data.cameraDevice)
                }
            }
            NumberRow(title: "Snap interval",
                      subtitle: "Milliseconds between snaps. Can't go faster than the camera delivers frames.",
                      value: Binding(get: { Double(store.data.intervalMs) },
                                     set: { store.data.intervalMs = Int($0) }),
                      range: 1...60000, step: 100, format: "%.0f")
        } header: {
            header("Camera")
        }
    }

    private var recognition: some View {
        Section {
            Picker(selection: data.model) {
                ForEach(controller.models) { model in
                    Text(model.label + (model.downloaded ? "" : " (downloads when first used)")).tag(model.id)
                }
                if !controller.models.contains(where: { $0.id == store.data.model }) {
                    Text(store.data.model).tag(store.data.model)
                }
            } label: {
                RowLabel(title: "Model",
                         subtitle: "Smaller models are faster and use less memory, but tell faces apart less reliably.")
            }
            // Shown off for a model that can't use it, without changing what was saved for the others.
            Toggle(isOn: Binding(get: { (model?.gpu ?? false) && store.data.useGpu },
                                 set: { store.data.useGpu = $0 })) {
                RowLabel(title: "Use GPU",
                         subtitle: gpuSubtitle)
            }
            .disabled(!(model?.gpu ?? false))
            NumberRow(title: "Match threshold",
                      subtitle: "How closely a face must match yours. Higher is stricter. Kept separately for each model.",
                      value: Binding(
                        get: { store.data.matchThresholds[store.data.model] ?? model?.defaultMatch ?? 0.4 },
                        set: { store.data.matchThresholds[store.data.model] = $0 }),
                      range: 0...1, step: 0.05, format: "%.2f")
            if model?.usesDetection ?? true {
                NumberRow(title: "Detection threshold",
                          subtitle: "How confident the detector must be that something is a face.",
                          value: data.detectionThreshold, range: 0.05...1, step: 0.05, format: "%.2f")
            }
            NumberRow(title: "Smallest face",
                      subtitle: "Ignore faces smaller than this many pixels, such as people far away.",
                      value: Binding(get: { Double(store.data.minFacePx) },
                                     set: { store.data.minFacePx = Int($0) }),
                      range: 0...500, step: 5, format: "%.0f")
            NumberRow(title: "Lock after absence",
                      subtitle: "Seconds your face can be missing before the screen locks.",
                      value: data.absenceGraceS, range: 0...600, step: 1, format: "%.1f")
        } header: {
            header("Recognition", "The panel menu shows the live match score, to help you tune these.")
        }
    }

    private var gpuSubtitle: String {
        guard let name = controller.gpuName else { return "No usable GPU was found." }
        guard let model else { return "Checking for a GPU…" }
        return model.gpu ? "\(name): faster, but uses more memory." : "\(model.label) can't use \(name)."
    }

    private var someoneElse: some View {
        Section {
            NumberRow(title: "Delay", subtitle: "Seconds the other face must stay in view first.",
                      value: data.intruderGraceS, range: 0...60, step: 0.5, format: "%.1f")
            Picker("Action", selection: data.intruderAction) {
                Text("Lock the screen").tag("lock")
                Text("Show giant eyes").tag("eyes")
                Text("Notify me").tag("notify")
                Text("Run a command").tag("command")
            }
            if store.data.intruderAction == "command" {
                TextField("Command (run with sh -c)", text: data.intruderCommand)
                    .textFieldStyle(.roundedBorder)
            }
        } header: {
            header("When someone else appears", "Runs when another face is in view alongside yours.")
        }
    }

    private var minimizeApps: some View {
        Section {
            Toggle("All open apps", isOn: data.minimizeAll)
            Toggle("Restore once they've gone", isOn: data.minimizeRestore)
            ForEach(store.data.minimizeApps, id: \.self) { id in
                HStack {
                    AppLabel(bundleID: id)
                    Spacer()
                    Button {
                        store.data.minimizeApps.removeAll { $0 == id }
                    } label: { Image(systemName: "trash") }
                    .buttonStyle(.borderless)
                    .help("Stop hiding this app")
                }
            }
        } header: {
            HStack(alignment: .top) {
                header("Hide apps",
                       "Also hides these apps when someone else appears, whatever the action above.")
                Spacer()
                Button { addingApp = true } label: { Image(systemName: "plus") }
                    .buttonStyle(.borderless)
                    .help("Add an app")
            }
        }
    }

    private var advanced: some View {
        Section {
            TextField("Python with insightface installed", text: data.pythonPath,
                      prompt: Text("Detected automatically"))
        } header: {
            header("Advanced")
        }
    }

    private func header(_ title: String, _ description: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.headline).foregroundStyle(.primary)
            if let description {
                Text(description).font(.callout).foregroundStyle(.secondary)
                    .textCase(nil)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .textCase(nil)
    }
}

/// A row label with a smaller explanation under it.
struct RowLabel: View {
    let title: String
    var subtitle: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
            if let subtitle {
                Text(subtitle).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// A number with a minus and a plus, like the GNOME spin rows.
struct NumberRow: View {
    let title: String
    var subtitle: String?
    @Binding var value: Double
    let range: ClosedRange<Double>
    let step: Double
    let format: String

    var body: some View {
        HStack {
            RowLabel(title: title, subtitle: subtitle)
            Spacer()
            Text(String(format: format, value)).monospacedDigit()
            Stepper("", value: $value, in: range, step: step).labelsHidden()
        }
    }
}

/// An app's icon and name, from its bundle identifier.
struct AppLabel: View {
    let bundleID: String

    var body: some View {
        let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleID)
        HStack(spacing: 10) {
            Image(nsImage: url.map { NSWorkspace.shared.icon(forFile: $0.path) } ?? NSImage(named: NSImage.applicationIconName)!)
                .resizable().frame(width: 28, height: 28)
            VStack(alignment: .leading) {
                Text(url.map { FileManager.default.displayName(atPath: $0.path).replacingOccurrences(of: ".app", with: "") } ?? bundleID)
                if url == nil { Text("Not installed").font(.caption).foregroundStyle(.secondary) }
            }
        }
    }
}
