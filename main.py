"""Markdown Viewer — entry point with multi-window support."""
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication

from src.ui import MainWindow
from src.utils.file_association import associate_files, disassociate_files


class MarkdownViewerApp:
    """Application controller supporting multiple windows and single-instance mode."""

    SOCKET_NAME = "markdown_viewer_single_instance"

    def __init__(self) -> None:
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Markdown Viewer")
        self.app.setOrganizationName("MarkdownViewer")
        # Use DengXian (等线) as the application-wide default font
        self.app.setFont(QFont("DengXian", 9))
        # Set application window icon from bundled assets
        # Use sys._MEIPASS for PyInstaller-bundled resources; fall back to dev path
        if getattr(sys, "frozen", False):
            icon_path = Path(sys._MEIPASS) / "assets" / "icon.ico"
        else:
            icon_path = Path(__file__).parent / "assets" / "icon.ico"
        if icon_path.exists():
            self.app.setWindowIcon(QIcon(str(icon_path)))
        self.windows: list[MainWindow] = []
        self.server: QLocalServer | None = None

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------
    def _create_window(self, filepath: str | None = None) -> MainWindow:
        """Create a new window, optionally loading a file.

        Wires up the file-open callback so user actions in this window
        check for duplicates before opening.
        """
        win = MainWindow(open_file_callback=self._make_open_file_callback())
        if filepath:
            win._load_file(filepath)
        win.show()
        self.windows.append(win)
        # Remove from tracking list when the window is destroyed
        win.destroyed.connect(lambda: self._remove_window(win))
        return win

    def _make_open_file_callback(self) -> Callable[[str], None]:
        """Return a closure that deduplicates file opens across all windows.

        The closure captures ``self`` so each MainWindow can delegate
        its user-facing file-open paths through the app-level check.
        """
        app = self

        def _open_file(path: str) -> None:
            app._open_file_in_window(path)

        return _open_file

    def _open_file_in_window(self, filepath: str) -> None:
        """Open a file, focusing existing window if already open.

        Unlike ``open_file`` (which always creates a new window for
        unseen files), this method lets the *originating* window load
        the file when it isn't open elsewhere.  The originating window
        is determined by ``QApplication.activeWindow()``.
        """
        normalized = str(Path(filepath).resolve()).lower()
        active = QApplication.activeWindow()
        for win in self.windows:
            if win is active:
                continue
            if hasattr(win, "_filepath") and win._filepath:
                if str(Path(win._filepath).resolve()).lower() == normalized:
                    self._focus_window(win)
                    return
        # Not open elsewhere → load in the originating window
        if active is not None and hasattr(active, "_load_file"):
            active._load_file(filepath)
        else:
            # Fallback (shouldn't happen in practice)
            self._create_window(filepath)

    def _remove_window(self, win: MainWindow) -> None:
        """Remove window from tracking list."""
        try:
            self.windows.remove(win)
        except ValueError:
            pass

    def _find_window_by_file(self, filepath: str) -> MainWindow | None:
        """Find an existing window that has the given file open."""
        normalized = str(Path(filepath).resolve()).lower()
        for win in self.windows:
            if hasattr(win, "_filepath") and win._filepath:
                if str(Path(win._filepath).resolve()).lower() == normalized:
                    return win
        return None

    def _focus_window(self, win: MainWindow) -> None:
        """Bring window to front and activate it."""
        win.raise_()
        win.activateWindow()
        if win.isMinimized():
            win.showNormal()

    def open_file(self, filepath: str) -> None:
        """Open a file in a new window, or focus existing window if already open."""
        normalized = str(Path(filepath).resolve())
        existing = self._find_window_by_file(normalized)
        if existing:
            self._focus_window(existing)
            return
        self._create_window(normalized)

    # ------------------------------------------------------------------
    # Command-line helpers
    # ------------------------------------------------------------------
    def _process_args(self, args: list[str]) -> bool:
        """Process special flags. Returns True if handled (no GUI needed)."""
        if "--associate" in args:
            associate_files()
            return True
        if "--disassociate" in args:
            disassociate_files()
            return True
        return False

    def _handle_file_args(self, args: list[str]) -> None:
        """Handle file path arguments by opening them in windows."""
        for arg in args:
            if arg.startswith("--"):
                continue
            path = Path(arg)
            if path.exists():
                self.open_file(str(path))

    # ------------------------------------------------------------------
    # Single-instance server / client
    # ------------------------------------------------------------------
    def _send_to_server(self, socket: QLocalSocket, args: list[str]) -> None:
        """Send file paths to an existing server instance."""
        paths = [str(Path(arg).resolve()) for arg in args if not arg.startswith("--")]
        if not paths:
            return
        data = "\n".join(paths).encode()
        socket.write(data)
        socket.flush()
        socket.waitForBytesWritten(1000)

    def _on_new_connection(self) -> None:
        """Handle incoming connection from a new instance."""
        socket = self.server.nextPendingConnection()
        if not socket:
            return
        socket.waitForReadyRead(1000)
        data = socket.readAll().data().decode()
        for line in data.split("\n"):
            path = line.strip()
            if path and Path(path).exists():
                self.open_file(path)

    def _start(self) -> None:
        """Try to connect to an existing instance; if not, become the server."""
        # First, try to connect to an already-running instance
        socket = QLocalSocket()
        socket.connectToServer(self.SOCKET_NAME)
        if socket.waitForConnected(1000):
            # Already running: hand off args and exit
            self._send_to_server(socket, sys.argv[1:])
            socket.disconnectFromServer()
            sys.exit(0)

        # No existing instance: become the server
        self.server = QLocalServer()
        if not self.server.listen(self.SOCKET_NAME):
            # Stale socket may exist; remove and retry once
            QLocalServer.removeServer(self.SOCKET_NAME)
            if not self.server.listen(self.SOCKET_NAME):
                # Cannot start server; fall back to local-only mode
                self._handle_file_args(sys.argv[1:])
                if not self.windows:
                    self._create_window()
                sys.exit(self.app.exec())

        self.server.newConnection.connect(self._on_new_connection)

        # Handle command-line files for this first instance
        self._handle_file_args(sys.argv[1:])

        # If no windows were created (no file args), start with an empty window
        if not self.windows:
            self._create_window()

        sys.exit(self.app.exec())

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Start the application."""
        if self._process_args(sys.argv[1:]):
            return
        self._start()


def main() -> None:
    MarkdownViewerApp().run()


if __name__ == "__main__":
    main()
