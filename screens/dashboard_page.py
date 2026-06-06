from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class DashboardData:
    summary: dict[str, int]
    most_requested_skills: list[tuple[str, int]]
    most_offered_skills: list[tuple[str, int]]
    active_departments: list[tuple[str, int]]
    top_rated_offerers: list[tuple[str, str]]


class DashboardRepository:
    """Read-only dashboard queries for the current Oracle schema."""

    def fetch_dashboard_data(self, user_id: int) -> DashboardData:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                summary = {
                    "active_users": self._scalar(
                        cursor,
                        "SELECT COUNT(*) FROM USERS WHERE STATUS = :status",
                        {"status": "ACTIVE"},
                    ),
                    "skills": self._scalar(cursor, "SELECT COUNT(*) FROM SKILLS"),
                    "offers": self._scalar(cursor, "SELECT COUNT(*) FROM OFFERS"),
                    "pending_requests": self._scalar(
                        cursor,
                        "SELECT COUNT(*) FROM REQUESTS WHERE STATUS = :status",
                        {"status": "PENDING"},
                    ),
                    "scheduled_sessions": self._scalar(
                        cursor,
                        "SELECT COUNT(*) FROM SESSIONS WHERE STATUS = :status",
                        {"status": "SCHEDULED"},
                    ),
                    "unread_notifications": self._scalar(
                        cursor,
                        """
                        SELECT COUNT(*)
                        FROM NOTIFICATIONS
                        WHERE TO_USER_ID = :user_id
                          AND IS_READ = :is_read
                        """,
                        {"user_id": user_id, "is_read": 0},
                    ),
                    "my_offers": self._scalar(
                        cursor,
                        "SELECT COUNT(*) FROM OFFERS WHERE USER_ID = :user_id",
                        {"user_id": user_id},
                    ),
                    "my_requests": self._scalar(
                        cursor,
                        "SELECT COUNT(*) FROM REQUESTS WHERE USER_ID = :user_id",
                        {"user_id": user_id},
                    ),
                }

                most_requested_skills = self._pairs(
                    cursor,
                    """
                    SELECT SKILL_NAME, REQUEST_COUNT
                    FROM VW_MOST_REQUESTED_SKILLS
                    ORDER BY REQUEST_COUNT DESC, SKILL_NAME
                    FETCH FIRST 5 ROWS ONLY
                    """,
                )
                most_offered_skills = self._pairs(
                    cursor,
                    """
                    SELECT SKILL_NAME, OFFER_COUNT
                    FROM VW_MOST_OFFERED_SKILLS
                    ORDER BY OFFER_COUNT DESC, SKILL_NAME
                    FETCH FIRST 5 ROWS ONLY
                    """,
                )
                active_departments = self._pairs(
                    cursor,
                    """
                    SELECT DEPARTMENT_NAME, ACTIVE_USERS
                    FROM VW_ACTIVE_DEPARTMENTS
                    ORDER BY ACTIVE_USERS DESC, DEPARTMENT_NAME
                    FETCH FIRST 5 ROWS ONLY
                    """,
                )
                top_rated_offerers = self._top_offerers(cursor)
            finally:
                cursor.close()

        return DashboardData(
            summary=summary,
            most_requested_skills=most_requested_skills,
            most_offered_skills=most_offered_skills,
            active_departments=active_departments,
            top_rated_offerers=top_rated_offerers,
        )

    @staticmethod
    def _scalar(cursor, sql: str, params: dict | None = None) -> int:
        cursor.execute(sql, params or {})
        row = cursor.fetchone()
        return int(row[0] or 0) if row else 0

    @staticmethod
    def _pairs(cursor, sql: str, params: dict | None = None) -> list[tuple[str, int]]:
        cursor.execute(sql, params or {})
        return [(str(row[0]), int(row[1] or 0)) for row in cursor.fetchall()]

    @staticmethod
    def _top_offerers(cursor) -> list[tuple[str, str]]:
        cursor.execute(
            """
            SELECT OFFERER_NAME, AVG_SCORE
            FROM VW_TOP_RATED_OFFERERS
            ORDER BY AVG_SCORE DESC, OFFERER_NAME
            FETCH FIRST 5 ROWS ONLY
            """
        )
        return [(str(row[0]), f"{float(row[1]):.2f}") for row in cursor.fetchall()]


class DashboardPage(ctk.CTkFrame):
    """Authenticated dashboard shell with read-only Oracle statistics."""

    METRICS = (
        ("active_users", "Active Users", "#14b8a6"),
        ("skills", "Skills", "#38bdf8"),
        ("offers", "Offers", "#a78bfa"),
        ("pending_requests", "Pending Requests", "#f59e0b"),
        ("scheduled_sessions", "Scheduled Sessions", "#22c55e"),
        ("unread_notifications", "Unread Notifications", "#f43f5e"),
        ("my_offers", "My Offers", "#06b6d4"),
        ("my_requests", "My Requests", "#eab308"),
    )

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = DashboardRepository()
        self.metric_value_labels: dict[str, ctk.CTkLabel] = {}
        self.list_bodies: dict[str, ctk.CTkFrame] = {}
        self.error_var = ctk.StringVar(value="")

        self._build_layout(on_logout)
        self.after(100, self.refresh)

    def _build_layout(self, on_logout: Callable[[], None]) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        sidebar = Sidebar(
            self,
            user=self.user,
            items=(("dashboard", "Dashboard"),),
            active_key="dashboard",
            on_select=self._handle_navigation,
            on_logout=on_logout,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")

        self.content = ctk.CTkScrollableFrame(
            self,
            fg_color="#0b1018",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_error_banner()
        self._build_metrics()
        self._build_lists()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=f"Welcome, {self.user.get('name', 'User')}",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        detail = (
            f"{self.user.get('role', '').title()} · "
            f"{self.user.get('department_name', 'Department')} · "
            f"Batch {self.user.get('batch', '')}"
        )
        ctk.CTkLabel(
            header,
            text=detail,
            font=ctk.CTkFont(size=14),
            text_color="#94a3b8",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.refresh_button = ctk.CTkButton(
            header,
            text="Refresh",
            command=self.refresh,
            width=116,
            height=38,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_error_banner(self) -> None:
        self.error_banner = ctk.CTkLabel(
            self.content,
            textvariable=self.error_var,
            fg_color="#451a1a",
            text_color="#fecaca",
            corner_radius=8,
            height=38,
            font=ctk.CTkFont(size=13),
            wraplength=780,
            justify="left",
        )
        self.error_banner.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 16))
        self.error_banner.grid_remove()

    def _build_metrics(self) -> None:
        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))

        for column in range(4):
            grid.grid_columnconfigure(column, weight=1, uniform="metric")

        for index, (key, title, color) in enumerate(self.METRICS):
            row = index // 4
            column = index % 4
            card = ctk.CTkFrame(grid, fg_color="#111827", corner_radius=8)
            card.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkFrame(
                card,
                fg_color=color,
                width=36,
                height=4,
                corner_radius=2,
            ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 12))

            value = ctk.CTkLabel(
                card,
                text="--",
                font=ctk.CTkFont(size=28, weight="bold"),
                text_color="#f8fafc",
            )
            value.grid(row=1, column=0, sticky="w", padx=18)

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#94a3b8",
                wraplength=130,
                justify="left",
            ).grid(row=2, column=0, sticky="w", padx=18, pady=(4, 18))

            self.metric_value_labels[key] = value

    def _build_lists(self) -> None:
        lists = ctk.CTkFrame(self.content, fg_color="transparent")
        lists.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 28))
        lists.grid_columnconfigure(0, weight=1, uniform="list")
        lists.grid_columnconfigure(1, weight=1, uniform="list")

        panels = (
            ("most_requested_skills", "Most Requested Skills", "Requests"),
            ("most_offered_skills", "Most Offered Skills", "Offers"),
            ("active_departments", "Active Departments", "Users"),
            ("top_rated_offerers", "Top Rated Offerers", "Avg"),
        )

        for index, (key, title, value_label) in enumerate(panels):
            panel = self._create_list_panel(lists, title, value_label)
            panel.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=6,
                pady=6,
            )
            self.list_bodies[key] = panel.body

    def _create_list_panel(
        self,
        parent: ctk.CTkFrame,
        title: str,
        value_label: str,
    ) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=8)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=value_label,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#64748b",
        ).grid(row=0, column=1, sticky="e")

        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        panel.body = body
        return panel

    def refresh(self) -> None:
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.error_var.set("")
        self.error_banner.grid_remove()
        self.update_idletasks()

        try:
            data = self.repository.fetch_dashboard_data(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_error(str(exc))
        except Exception as exc:
            self._show_error(f"Dashboard query failed: {exc}")
        else:
            self._render_dashboard(data)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def _render_dashboard(self, data: DashboardData) -> None:
        for key, label in self.metric_value_labels.items():
            label.configure(text=self._format_number(data.summary.get(key, 0)))

        self._render_rows("most_requested_skills", data.most_requested_skills)
        self._render_rows("most_offered_skills", data.most_offered_skills)
        self._render_rows("active_departments", data.active_departments)
        self._render_rows("top_rated_offerers", data.top_rated_offerers)

    def _render_rows(self, key: str, rows: Iterable[tuple[str, int | str]]) -> None:
        body = self.list_bodies[key]
        for child in body.winfo_children():
            child.destroy()

        row_list = list(rows)
        if not row_list:
            ctk.CTkLabel(
                body,
                text="No records yet",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, (name, value) in enumerate(row_list):
            row = ctk.CTkFrame(body, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                row,
                text=name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#e2e8f0",
                anchor="w",
                wraplength=280,
                justify="left",
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=10)

            ctk.CTkLabel(
                row,
                text=str(value),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#14b8a6",
                width=56,
                anchor="e",
            ).grid(row=0, column=1, sticky="e", padx=12, pady=10)

    def _show_error(self, message: str) -> None:
        self.error_var.set(message)
        self.error_banner.grid()

    def _handle_navigation(self, key: str) -> None:
        if key == "dashboard":
            self.refresh()

    @staticmethod
    def _format_number(value: int) -> str:
        return f"{int(value):,}"
