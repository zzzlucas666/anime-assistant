"""Compatibility entry point for the PySide6 desktop application."""

from anime_assistant.ui.main_window import MainWindow, main


__all__ = ["MainWindow", "main"]


if __name__ == "__main__":
    main()
