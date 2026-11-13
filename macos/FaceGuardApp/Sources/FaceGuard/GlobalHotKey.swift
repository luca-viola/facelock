import Carbon.HIToolbox

/// A keyboard shortcut that works in every app. Unlike watching key presses, registering one this
/// way needs no Accessibility or Input Monitoring permission.
final class GlobalHotKey {
    private static var actions: [UInt32: () -> Void] = [:]
    private static var handlerInstalled = false

    private var reference: EventHotKeyRef?

    /// Returns nil if another app already has the shortcut. `keyCode` is a virtual key code and
    /// `modifiers` are Carbon's flags (controlKey, optionKey, cmdKey, shiftKey).
    init?(keyCode: Int, modifiers: Int, id: UInt32, action: @escaping () -> Void) {
        Self.actions[id] = action
        Self.installHandler()
        let hotKeyID = EventHotKeyID(signature: OSType(0x46474B59), id: id)  // 'FGKY'
        let status = RegisterEventHotKey(UInt32(keyCode), UInt32(modifiers), hotKeyID,
                                         GetApplicationEventTarget(), 0, &reference)
        if status != noErr { return nil }
    }

    deinit {
        if let reference { UnregisterEventHotKey(reference) }
    }

    private static func installHandler() {
        guard !handlerInstalled else { return }
        handlerInstalled = true
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ -> OSStatus in
            var hotKeyID = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                              nil, MemoryLayout<EventHotKeyID>.size, nil, &hotKeyID)
            DispatchQueue.main.async { GlobalHotKey.actions[hotKeyID.id]?() }
            return noErr
        }, 1, &spec, nil, nil)
    }
}
