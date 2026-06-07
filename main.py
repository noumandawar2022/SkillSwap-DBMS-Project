from __future__ import annotations

import customtkinter as ctk

from screens.dashboard_page import DashboardPage
from screens.feedback_page import FeedbackPage
from screens.login_page import LoginPage
from screens.messages_page import MessagesPage
from screens.notifications_page import NotificationsPage
from screens.offers_page import OffersPage
from screens.profile_page import ProfilePage
from screens.requests_page import RequestsPage
from screens.sessions_page import SessionsPage
from screens.skills_page import SkillsPage


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
        self.show_authenticated_page("dashboard")

    def show_profile(self) -> None:
        self.show_authenticated_page("profile")

    def show_skills(self) -> None:
        self.show_authenticated_page("skills")

    def show_offers(self) -> None:
        self.show_authenticated_page("offers")

    def show_requests(self) -> None:
        self.show_authenticated_page("requests")

    def show_notifications(self) -> None:
        self.show_authenticated_page("notifications")

    def show_sessions(self) -> None:
        self.show_authenticated_page("sessions")

    def show_messages(self) -> None:
        self.show_authenticated_page("messages")

    def show_feedback(self) -> None:
        self.show_authenticated_page("feedback")

    def show_authenticated_page(self, page_key: str) -> None:
        if self.current_user is None:
            self.show_login()
            return

        page_classes = {
            "dashboard": DashboardPage,
            "profile": ProfilePage,
            "skills": SkillsPage,
            "offers": OffersPage,
            "requests": RequestsPage,
            "notifications": NotificationsPage,
            "sessions": SessionsPage,
            "messages": MessagesPage,
            "feedback": FeedbackPage,
        }
        page_class = page_classes.get(page_key, DashboardPage)

        page_kwargs = {
            "user": self.current_user,
            "on_navigate": self.handle_navigation,
            "on_logout": self.handle_logout,
        }
        if page_key == "profile":
            page_kwargs["on_user_updated"] = self.handle_user_updated

        self._mount_page(page_class(self, **page_kwargs))

    def handle_navigation(self, page_key: str) -> None:
        self.show_authenticated_page(page_key)

    def handle_user_updated(self, user: dict) -> None:
        if self.current_user is None:
            self.current_user = user
        else:
            self.current_user.update(user)

    def handle_logout(self) -> None:
        self.show_login()


if __name__ == "__main__":
    app = SkillSwapApp()
    app.mainloop()
