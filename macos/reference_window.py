"""The window that previews the camera until you take the reference photo."""

import objc
from AppKit import (NSBackingStoreBuffered, NSButton, NSImage, NSImageView, NSMakeRect, NSObject, NSApplication,
                    NSTextField, NSWindow)

TITLED, CLOSABLE = 1, 2
PREVIEW = (640, 360)
MARGIN = 16


class _Target(NSObject):
    def initWithOnSnap_onClose_(self, on_snap, on_close):
        self = objc.super(_Target, self).init()
        self._on_snap = on_snap
        self._on_close = on_close
        return self

    def snap_(self, _sender):
        self._on_snap()

    def cancel_(self, _sender):
        self._on_close()

    def windowWillClose_(self, _notification):
        self._on_close()


class ReferenceWindow:
    """on_snap() runs when Take Photo is pressed. on_close() runs when the window closes."""

    def __init__(self, on_snap, on_close):
        width = PREVIEW[0] + 2 * MARGIN
        height = PREVIEW[1] + 100
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, width, height), TITLED | CLOSABLE, NSBackingStoreBuffered, False)
        self._window.setTitle_("Take Reference Photo")
        self._window.setReleasedWhenClosed_(False)
        self._target = _Target.alloc().initWithOnSnap_onClose_(on_snap, on_close)
        self._window.setDelegate_(self._target)

        content = self._window.contentView()
        self._image = NSImageView.alloc().initWithFrame_(NSMakeRect(MARGIN, 84, *PREVIEW))
        content.addSubview_(self._image)
        self._label = NSTextField.labelWithString_("Starting the camera…")
        self._label.setFrame_(NSMakeRect(MARGIN, 52, PREVIEW[0], 22))
        content.addSubview_(self._label)
        self._take = self._button("Take Photo", "snap:", width - MARGIN - 110 - 100 - 8)
        self._take.setEnabled_(False)
        self._take.setKeyEquivalent_("\r")
        self._button("Cancel", "cancel:", width - MARGIN - 100)
        self._closed = False

    def _button(self, title, action, x):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, 12, 110 if title == "Take Photo" else 100, 32))
        button.setTitle_(title)
        button.setBezelStyle_(1)
        button.setTarget_(self._target)
        button.setAction_(action)
        self._window.contentView().addSubview_(button)
        return button

    def show(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.center()
        self._window.makeKeyAndOrderFront_(None)

    def ready(self):
        self._take.setEnabled_(True)
        self.message("Look at the camera, alone in the frame, then take the photo.")

    def message(self, text):
        self._label.setStringValue_(text)

    def show_frame(self, path):
        image = NSImage.alloc().initWithContentsOfFile_(path)
        if image is not None:
            self._image.setImage_(image)

    def busy(self, text):
        self._take.setEnabled_(False)
        self.message(text)

    def close(self):
        """Closes the window without calling on_close."""
        if self._closed:
            return
        self._closed = True
        self._window.setDelegate_(None)
        self._window.close()
