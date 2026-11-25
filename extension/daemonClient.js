import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

// Runs the Python daemon and reports its JSON-line events.
export class DaemonClient {
    constructor(argv, onEvent, onExit) {
        this._onEvent = onEvent;
        this._onExit = onExit;
        this._cancellable = new Gio.Cancellable();
        this._process = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE);
        this._stdout = new Gio.DataInputStream({
            base_stream: this._process.get_stdout_pipe(),
        });
        this._readLine();
        this._process.wait_async(this._cancellable, (process, result) => {
            try {
                process.wait_finish(result);
            } catch {
                return; // Cancelled by stop(), so nobody is waiting for this.
            }
            if (!this._cancellable.is_cancelled())
                this._onExit(process.get_exit_status());
        });
    }

    _readLine() {
        this._stdout.read_line_async(GLib.PRIORITY_DEFAULT, this._cancellable, (stream, result) => {
            let line;
            try {
                [line] = stream.read_line_finish_utf8(result);
            } catch {
                return; // Cancelled, or the pipe closed along with the process.
            }
            if (line === null || this._cancellable.is_cancelled())
                return;
            this._dispatch(line);
            if (!this._cancellable.is_cancelled())
                this._readLine();
        });
    }

    _dispatch(line) {
        let message;
        try {
            message = JSON.parse(line);
        } catch {
            console.warn(`Facelock: ignoring bad daemon output: ${line}`);
            return;
        }
        this._onEvent(message);
    }

    // Sends one command line to the daemon. It may have just exited, which is fine.
    send(line) {
        try {
            this._process.get_stdin_pipe().write_bytes(new GLib.Bytes(`${line}\n`), null);
        } catch (error) {
            console.warn(`Facelock: can't send "${line}" to the daemon: ${error.message}`);
        }
    }

    stop() {
        this._cancellable.cancel();
        this._process.force_exit();
    }
}
