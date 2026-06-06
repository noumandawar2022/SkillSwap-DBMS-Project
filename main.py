from __future__ import annotations

import customtkinter as ctk

from screens.dashboard_page import DashboardPage
from screens.login_page import LoginPage


class SkillSwapApp(ctk.CTk):
    """Main desktop shell for the SkillSwap application."""

    WINDOW_SIZE = "1180x760"
    MIN_WIDTH = 980
    MIN_HEIGHT = 640

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("SkillSwap")
        self.geometry(self.WINDOW_SIZE)
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.configure(fg_color="#0b1018")

        self.current_user: dict | None = None
        self._active_page: ctk.CTkFrame | None = None

        self.show_login()

    def _mount_page(self, page: ctk.CTkFrame) -> None:
        if self._active_page is not None:
            self._active_page.destroy()

        self._active_page = page
        self._active_page.pack(fill="both", expand=True)

    def show_login(self) -> None:
        self.current_user = None
        self._mount_page(LoginPage(self, on_login_success=self.handle_login_success))

    def handle_login_success(self, user: dict) -> None:
        self.current_user = user
        self.show_dashboard()

    def show_dashboard(self) -> None:
        if self.current_user is None:
            self.show_login()
            return

        self._mount_page(
            DashboardPage(
                self,
                user=self.current_user,
                on_logout=self.handle_logout,
            )
        )

    def handle_logout(self) -> None:
        self.show_login()


if __name__ == "__main__":
    app = SkillSwapApp()
    app.mainloop()
