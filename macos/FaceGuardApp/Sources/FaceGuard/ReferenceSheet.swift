import SwiftUI

/// Previews the camera until the reference photo is taken.
struct ReferenceSheet: View {
    @ObservedObject var controller: Controller

    var body: some View {
        VStack(spacing: 14) {
            Text("Take a Reference Photo").font(.headline)
            ZStack {
                Rectangle().fill(.black)
                if let image = controller.previewImage {
                    Image(nsImage: image).resizable().scaledToFit()
                } else {
                    ProgressView()
                }
            }
            .frame(width: 560, height: 315)
            Text(message).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel") { controller.cancelCapture() }
                    .keyboardShortcut(.cancelAction)
                Button("Take Photo") { controller.snap() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(controller.captureState != .ready)
            }
        }
        .padding(20)
    }

    private var message: String {
        switch controller.captureState {
        case .idle, .starting: return "Starting the camera…"
        case .ready: return "Look at the camera, alone in the frame, then take the photo."
        case .checking: return "Checking the photo…"
        }
    }
}
