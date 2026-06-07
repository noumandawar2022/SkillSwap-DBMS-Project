from __future__ import annotations

from collections.abc import Callable, Sequence

import customtkinter as ctk


DEFAULT_NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("dashboard", "Dashboard"),
    ("profile", "Profile"),
    ("skills", "Skills"),
    ("offers", "Offers"),
    ("requests", "Requests"),
    ("notifications", "Notifications"),
    ("sessions", "Sessions"),
    ("messages", "Messages"),
    ("feedback", "Feedback"),
)


class Sidebar(ctk.CTkFrame):
    """Reusable left navigation for authenticated screens."""

    def __init__(
        self,
        master,
        user: dict,
        active_key: str,
        on_select: Callable[[str], None],
        on_logout: Callable[[], None],
        items: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(master, width=252, fg_color="#111827", corner_radius=0)
        self.grid_propagate(False)

        self.user = user
        self.items = tuple(items or DEFAULT_NAV_ITEMS)
        self.active_key = active_key
        self.on_select = on_select
        self.on_logout = on_logout
        self.buttons: dict[str, ctk.CTkButton] = {}

        self._build_layout()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self,
            text="SkillSwap",
            font=ctk.CTkFont(size=23, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(26, 20))

        self._build_user_block().grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 22))
        self._build_navigation().grid(row=2, column=0, sticky="ew", padx=12)

        ctk.CTkButton(
            self,
            text="Logout",
            command=self.on_logout,
            height=40,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#f8fafc",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", padx=16, pady=(16, 22))

    def _build_user_block(self) -> ctk.CTkFrame:
        block = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=8)
        block.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            block,
            text=self._initials(self.user.get("name", "User")),
            width=44,
            height=44,
            fg_color="#14b8a6",
            corner_radius=8,
            text_color="#042f2e",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, rowspan=2, padx=12, pady=14)

        ctk.CTkLabel(
            block,
            text=self.user.get("name", "User"),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#e2e8f0",
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(14, 2))

        ctk.CTkLabel(
            block,
            text=self.user.get("role", "STUDENT").title(),
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
            anchor="w",
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 14))

        return block

    def _build_navigation(self) -> ctk.CTkFrame:
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid_columnconfigure(0, weight=1)

        for row, (key, label) in enumerate(self.items):
            button = ctk.CTkButton(
                nav,
                text=label,
                command=lambda selected=key: self.select(selected),
                height=42,
                corner_radius=8,
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w",
            )
            button.grid(row=row, column=0, sticky="ew", pady=4)
            self.buttons[key] = button

        self._sync_button_styles()
        return nav

    def select(self, key: str) -> None:
        self.active_key = key
        self._sync_button_styles()
        self.on_select(key)

    def _sync_button_styles(self) -> None:
        for key, button in self.buttons.items():
            if key == self.active_key:
                button.configure(
                    fg_color="#14b8a6",
                    hover_color="#0f766e",
                    text_color="#042f2e",
                )
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color="#1e293b",
                    text_color="#cbd5e1",
                )

    @staticmethod
    def _initials(name: str) -> str:
        parts = [part for part in name.strip().split() if part]
        if not parts:
            return "U"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return f"{parts[0][0]}{parts[-1][0]}".upper()
