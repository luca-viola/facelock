"""The error that ends the daemon, and the exit codes the extension acts on."""

EXIT_RETRYABLE = 3  # camera or model trouble that may clear up by itself
EXIT_FATAL = 4  # needs the user to change something, so don't restart


class GuardError(Exception):
    def __init__(self, code, message, retryable):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
