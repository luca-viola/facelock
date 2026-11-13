"""Small AppKit helpers for a menu bar app, which is never frontmost."""

import subprocess

from AppKit import NSAlert, NSApplication, NSImage, NSOpenPanel


def alert(message, info="", buttons=("OK",)):
    """Shows a modal alert in front of other windows. Returns the index of the button pressed."""
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    box = NSAlert.alloc().init()
    box.setMessageText_(message)
    box.setInformativeText_(info)
    for button in buttons:
        box.addButtonWithTitle_(button)
    return box.runModal() - 1000  # NSAlertFirstButtonReturn


def choose_image():
    """Asks for an image file. Returns its path, or None."""
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    panel = NSOpenPanel.openPanel()
    panel.setMessage_("Choose a photo with only your face in it")
    panel.setAllowedFileTypes_(["jpg", "jpeg", "png", "heic", "tiff", "bmp"])
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(False)
    if panel.runModal() != 1:  # NSModalResponseOK
        return None
    return panel.URL().path()


def symbol(name, description):
    """An SF Symbol as a template image for the menu bar, or None before macOS 11."""
    if not hasattr(NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
        return None
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, description)
    if image is not None:
        image.setTemplate_(True)
    return image


def notify(title, message):
    """A notification. Without an app bundle, rumps can't send one, so this asks the system."""
    import rumps

    try:
        rumps.notification("Face Guard", title, message)
    except RuntimeError:
        script = f'display notification {_quote(message)} with title {_quote(title)}'
        subprocess.run(["/usr/bin/osascript", "-e", script], check=False)


def _quote(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
