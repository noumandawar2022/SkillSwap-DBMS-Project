from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class NotificationRecord:
    notification_id: int
    notification_type: str
    content: str
    created_at: object
    is_read: int


class NotificationsRepository:
    """Oracle operations for user notifications."""

    def fetch_notifications(self, user_id: int) -> list[NotificationRecord]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT
                        NOTIFICATION_ID,
                        NOTIFICATION_TYPE,
                        CONTENT,
                        CREATED_AT,
                        IS_READ
                    FROM NOTIFICATIONS
                    WHERE TO_USER_ID = :user_id
                    ORDER BY CREATED_AT DESC, NOTIFICATION_ID DESC
                    """,
                    {"user_id": user_id},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            NotificationRecord(
                notification_id=int(row[0]),
                notification_type=str(row[1]),
                content=str(row[2]),
                created_at=row[3],
                is_read=int(row[4]),
            )
            for row in rows
        ]

    def mark_as_read(self, notification_id: int, user_id: int) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE NOTIFICATIONS
                    SET IS_READ = :is_read
                    WHERE NOTIFICATION_ID = :notification_id
                      AND TO_USER_ID = :user_id
                    """,
                    {
                        "is_read": 1,
                        "notification_id": notification_id,
                        "user_id": user_id,
                    },
                )
                if cursor.rowcount != 1:
                    raise ValueError("Notification not found.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()


class NotificationsPage(ctk.CTkFrame):
    """Notifications screen."""

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = NotificationsRepository()
        self.message_var = ctk.StringVar(value="")

        self._build_layout(on_navigate, on_logout)
        self.after(100, self.refresh)

    def _build_layout(
        self,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        Sidebar(
            self,
            user=self.user,
            active_key="notifications",
            on_select=on_navigate,
            on_logout=on_logout,
        ).grid(row=0, column=0, sticky="nsew")

        self.content = ctk.CTkScrollableFrame(
            self,
            fg_color="#0b1018",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_message_banner()
        self._build_list_panel()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Notifications",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Recent updates",
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

    def _build_message_banner(self) -> None:
        self.message_banner = ctk.CTkLabel(
            self.content,
            textvariable=self.message_var,
            fg_color="#0f172a",
            text_color="#cbd5e1",
            corner_radius=8,
            height=38,
            font=ctk.CTkFont(size=13),
            wraplength=780,
            justify="left",
        )
        self.message_banner.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 16))
        self.message_banner.grid_remove()

    def _build_list_panel(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 28))
        panel.grid_columnconfigure(0, weight=1)

        self.rows_container = ctk.CTkFrame(panel, fg_color="transparent")
        self.rows_container.grid(row=0, column=0, sticky="ew", padx=18, pady=18)
        self.rows_container.grid_columnconfigure(0, weight=1)

    def refresh(self) -> None:
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.message_banner.grid_remove()
        self.update_idletasks()

        try:
            rows = self.repository.fetch_notifications(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Notifications query failed: {exc}", "error")
        else:
            self._render_rows(rows)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def mark_as_read(self, notification: NotificationRecord) -> None:
        try:
            self.repository.mark_as_read(
                notification.notification_id,
                int(self.user["user_id"]),
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Mark as read failed: {exc}", "error")
        else:
            self.refresh()
            self._show_message("Notification marked as read.", "success")

    def _render_rows(self, rows: list[NotificationRecord]) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()

        if not rows:
            ctk.CTkLabel(
                self.rows_container,
                text="No notifications found",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, notification in enumerate(rows):
            row = ctk.CTkFrame(self.rows_container, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=3)
            row.grid_columnconfigure(2, weight=1)
            row.grid_columnconfigure(3, weight=1)

            values = (
                notification.notification_type,
                notification.content,
                self._format_date(notification.created_at),
                "Read" if notification.is_read else "Unread",
            )
            for column, value in enumerate(values):
                ctk.CTkLabel(
                    row,
                    text=value,
                    font=ctk.CTkFont(size=13, weight="bold" if column == 0 else "normal"),
                    text_color="#e2e8f0" if column in (0, 1) else "#94a3b8",
                    anchor="w",
                    wraplength=420 if column == 1 else 150,
                    justify="left",
                ).grid(row=0, column=column, sticky="ew", padx=12, pady=12)

            ctk.CTkButton(
                row,
                text="Mark Read",
                command=lambda current=notification: self.mark_as_read(current),
                width=92,
                height=30,
                corner_radius=8,
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#e2e8f0",
                state="disabled" if notification.is_read else "normal",
            ).grid(row=0, column=4, sticky="e", padx=12, pady=10)

    def _show_message(self, message: str, kind: str) -> None:
        colors = {
            "success": ("#064e3b", "#bbf7d0"),
            "error": ("#451a1a", "#fecaca"),
        }
        fg_color, text_color = colors.get(kind, ("#0f172a", "#cbd5e1"))
        self.message_banner.configure(fg_color=fg_color, text_color=text_color)
        self.message_var.set(message)
        self.message_banner.grid()

    @staticmethod
    def _format_date(value: object) -> str:
        if isinstance(value, datetime | date):
            return value.strftime("%Y-%m-%d")
        return str(value or "")
