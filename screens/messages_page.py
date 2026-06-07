from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class SessionOption:
    label: str
    session_id: int


@dataclass(frozen=True)
class MessageRecord:
    message_id: int
    sender_id: int
    sender_name: str
    content: str
    sent_at: object
    is_read: int


class MessagesRepository:
    """Oracle operations for session messages."""

    def fetch_sessions(self, user_id: int) -> list[SessionOption]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT
                        S.SESSION_ID,
                        SK.SKILL_NAME,
                        S.SESSION_DATE
                    FROM SESSIONS S
                    JOIN REQUESTS R
                      ON S.REQUEST_ID = R.REQUEST_ID
                    JOIN OFFERS O
                      ON S.OFFER_ID = O.OFFER_ID
                    JOIN SKILLS SK
                      ON R.SKILL_ID = SK.SKILL_ID
                    WHERE R.USER_ID = :user_id
                       OR O.USER_ID = :user_id
                    ORDER BY S.SESSION_DATE DESC, S.SESSION_ID DESC
                    """,
                    {"user_id": user_id},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            SessionOption(
                label=f"Session {int(row[0])} - {row[1]} - {self._format_date(row[2])}",
                session_id=int(row[0]),
            )
            for row in rows
        ]

    def fetch_messages(self, session_id: int, user_id: int) -> list[MessageRecord]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                self._ensure_session_access(cursor, session_id, user_id)
                cursor.execute(
                    """
                    SELECT
                        M.MESSAGE_ID,
                        M.SENDER_ID,
                        U.NAME,
                        M.CONTENT,
                        M.SENT_AT,
                        M.IS_READ
                    FROM MESSAGES M
                    JOIN USERS U
                      ON M.SENDER_ID = U.USER_ID
                    WHERE M.SESSION_ID = :session_id
                    ORDER BY M.SENT_AT ASC, M.MESSAGE_ID ASC
                    """,
                    {"session_id": session_id},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            MessageRecord(
                message_id=int(row[0]),
                sender_id=int(row[1]),
                sender_name=str(row[2]),
                content=str(row[3]),
                sent_at=row[4],
                is_read=int(row[5]),
            )
            for row in rows
        ]

    def send_message(self, session_id: int, user_id: int, content: str) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                self._ensure_session_access(cursor, session_id, user_id)
                cursor.execute(
                    """
                    INSERT INTO MESSAGES (
                        SESSION_ID,
                        SENDER_ID,
                        CONTENT
                    )
                    VALUES (
                        :session_id,
                        :sender_id,
                        :content
                    )
                    """,
                    {
                        "session_id": session_id,
                        "sender_id": user_id,
                        "content": content.strip(),
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    def mark_as_read(self, message_id: int, session_id: int, user_id: int) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                self._ensure_session_access(cursor, session_id, user_id)
                cursor.execute(
                    """
                    UPDATE MESSAGES
                    SET IS_READ = :is_read
                    WHERE MESSAGE_ID = :message_id
                      AND SESSION_ID = :session_id
                    """,
                    {
                        "is_read": 1,
                        "message_id": message_id,
                        "session_id": session_id,
                    },
                )
                if cursor.rowcount != 1:
                    raise ValueError("Message not found.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    @staticmethod
    def _ensure_session_access(cursor, session_id: int, user_id: int) -> None:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM SESSIONS S
            JOIN REQUESTS R
              ON S.REQUEST_ID = R.REQUEST_ID
            JOIN OFFERS O
              ON S.OFFER_ID = O.OFFER_ID
            WHERE S.SESSION_ID = :session_id
              AND (R.USER_ID = :user_id OR O.USER_ID = :user_id)
            """,
            {"session_id": session_id, "user_id": user_id},
        )
        row = cursor.fetchone()
        if not row or int(row[0]) == 0:
            raise ValueError("Session not found.")

    @staticmethod
    def _format_date(value: object) -> str:
        if isinstance(value, datetime | date):
            return value.strftime("%Y-%m-%d")
        return str(value or "")


class MessagesPage(ctk.CTkFrame):
    """Session messages screen."""

    NO_SESSIONS = "No sessions available"

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = MessagesRepository()
        self.session_lookup: dict[str, int] = {}

        self.message_var = ctk.StringVar(value="")
        self.session_var = ctk.StringVar(value=self.NO_SESSIONS)
        self.content_var = ctk.StringVar()

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
            active_key="messages",
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
        self._build_controls()
        self._build_rows_panel()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Messages",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Session conversations",
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

    def _build_controls(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        panel.grid_columnconfigure(0, weight=2)
        panel.grid_columnconfigure(1, weight=3)

        self.session_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.session_var,
            values=[self.NO_SESSIONS],
            command=lambda _selected: self.load_messages(),
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.session_menu.grid(row=0, column=0, sticky="ew", padx=(18, 8), pady=18)

        self.content_entry = ctk.CTkEntry(
            panel,
            textvariable=self.content_var,
            placeholder_text="Message content",
            height=42,
            border_width=1,
            border_color="#334155",
            fg_color="#0f172a",
            text_color="#f8fafc",
            placeholder_text_color="#64748b",
            corner_radius=8,
        )
        self.content_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=18)
        self.content_entry.bind("<Return>", self._send_from_event)

        self.send_button = ctk.CTkButton(
            panel,
            text="Send",
            command=self.send_message,
            width=92,
            height=42,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#042f2e",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.send_button.grid(row=0, column=2, sticky="ew", padx=(8, 18), pady=18)

    def _build_rows_panel(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 28))
        panel.grid_columnconfigure(0, weight=1)

        self.rows_container = ctk.CTkFrame(panel, fg_color="transparent")
        self.rows_container.grid(row=0, column=0, sticky="ew", padx=18, pady=18)
        self.rows_container.grid_columnconfigure(0, weight=1)

    def refresh(self) -> None:
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.message_banner.grid_remove()
        self.update_idletasks()

        try:
            sessions = self.repository.fetch_sessions(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Messages query failed: {exc}", "error")
        else:
            self._render_session_options(sessions)
            self.load_messages(show_errors=False)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def load_messages(self, show_errors: bool = True) -> None:
        session_id = self._selected_session_id()
        if session_id is None:
            self._render_rows([])
            return

        try:
            rows = self.repository.fetch_messages(session_id, int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            if show_errors:
                self._show_message(str(exc), "error")
        except Exception as exc:
            if show_errors:
                self._show_message(f"Load messages failed: {exc}", "error")
        else:
            self._render_rows(rows)

    def send_message(self) -> None:
        session_id = self._selected_session_id()
        content = self.content_var.get().strip()

        if session_id is None:
            self._show_message("Select a session before sending a message.", "error")
            return

        if not content:
            self._show_message("Message content is required.", "error")
            return

        if len(content) > 4000:
            self._show_message("Message content cannot exceed 4000 characters.", "error")
            return

        self.send_button.configure(state="disabled", text="Sending...")
        self.update_idletasks()

        try:
            self.repository.send_message(session_id, int(self.user["user_id"]), content)
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Send message failed: {exc}", "error")
        else:
            self.content_var.set("")
            self.load_messages()
            self._show_message("Message sent successfully.", "success")
        finally:
            self.send_button.configure(state="normal", text="Send")

    def mark_as_read(self, message: MessageRecord) -> None:
        session_id = self._selected_session_id()
        if session_id is None:
            return

        try:
            self.repository.mark_as_read(
                message.message_id,
                session_id,
                int(self.user["user_id"]),
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Mark message as read failed: {exc}", "error")
        else:
            self.load_messages()
            self._show_message("Message marked as read.", "success")

    def _render_session_options(self, sessions: list[SessionOption]) -> None:
        if not sessions:
            self.session_lookup = {}
            self.session_var.set(self.NO_SESSIONS)
            self.session_menu.configure(values=[self.NO_SESSIONS], state="disabled")
            self.send_button.configure(state="disabled")
            return

        lookup = {session.label: session.session_id for session in sessions}
        current = self.session_var.get()
        values = list(lookup)
        self.session_lookup = lookup
        self.session_menu.configure(values=values, state="normal")
        self.session_var.set(current if current in lookup else values[0])
        self.send_button.configure(state="normal")

    def _render_rows(self, rows: list[MessageRecord]) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()

        if not rows:
            ctk.CTkLabel(
                self.rows_container,
                text="No messages found",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, message in enumerate(rows):
            row = ctk.CTkFrame(self.rows_container, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=3)
            row.grid_columnconfigure(2, weight=1)
            row.grid_columnconfigure(3, weight=1)

            values = (
                message.sender_name,
                message.content,
                self._format_date(message.sent_at),
                "Read" if message.is_read else "Unread",
            )
            for column, value in enumerate(values):
                ctk.CTkLabel(
                    row,
                    text=value,
                    font=ctk.CTkFont(size=13, weight="bold" if column == 0 else "normal"),
                    text_color="#e2e8f0" if column in (0, 1) else "#94a3b8",
                    anchor="w",
                    wraplength=430 if column == 1 else 150,
                    justify="left",
                ).grid(row=0, column=column, sticky="ew", padx=12, pady=12)

            ctk.CTkButton(
                row,
                text="Mark Read",
                command=lambda current=message: self.mark_as_read(current),
                width=92,
                height=30,
                corner_radius=8,
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#e2e8f0",
                state="disabled" if message.is_read else "normal",
            ).grid(row=0, column=4, sticky="e", padx=12, pady=10)

    def _selected_session_id(self) -> int | None:
        return self.session_lookup.get(self.session_var.get())

    def _send_from_event(self, _event) -> None:
        self.send_message()

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
