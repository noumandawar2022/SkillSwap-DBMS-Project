from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class SessionRecord:
    session_id: int
    session_date: object
    meeting_detail: str
    status: str
    requester_confirmed: int
    offerer_confirmed: int
    completed_at: object
    requester_id: int
    offerer_id: int


class SessionsRepository:
    """Oracle operations for sessions involving the logged-in user."""

    def fetch_sessions(self, user_id: int) -> list[SessionRecord]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT
                        S.SESSION_ID,
                        S.SESSION_DATE,
                        S.MEETING_DETAIL,
                        S.STATUS,
                        S.REQUESTER_CONFIRMED,
                        S.OFFERER_CONFIRMED,
                        S.COMPLETED_AT,
                        R.USER_ID,
                        O.USER_ID
                    FROM SESSIONS S
                    JOIN REQUESTS R
                      ON S.REQUEST_ID = R.REQUEST_ID
                    JOIN OFFERS O
                      ON S.OFFER_ID = O.OFFER_ID
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
            SessionRecord(
                session_id=int(row[0]),
                session_date=row[1],
                meeting_detail=str(row[2] or ""),
                status=str(row[3]),
                requester_confirmed=int(row[4]),
                offerer_confirmed=int(row[5]),
                completed_at=row[6],
                requester_id=int(row[7]),
                offerer_id=int(row[8]),
            )
            for row in rows
        ]

    def confirm_session(self, session_id: int, user_id: int) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT R.USER_ID, O.USER_ID
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
                if row is None:
                    raise ValueError("Session not found.")

                requester_id = int(row[0])
                offerer_id = int(row[1])
                set_requester = 1 if requester_id == user_id else 0
                set_offerer = 1 if offerer_id == user_id else 0

                cursor.execute(
                    """
                    UPDATE SESSIONS
                    SET REQUESTER_CONFIRMED =
                            CASE
                                WHEN :set_requester = 1 THEN 1
                                ELSE REQUESTER_CONFIRMED
                            END,
                        OFFERER_CONFIRMED =
                            CASE
                                WHEN :set_offerer = 1 THEN 1
                                ELSE OFFERER_CONFIRMED
                            END
                    WHERE SESSION_ID = :session_id
                    """,
                    {
                        "set_requester": set_requester,
                        "set_offerer": set_offerer,
                        "session_id": session_id,
                    },
                )
                if cursor.rowcount != 1:
                    raise ValueError("Session not found.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()


class SessionsPage(ctk.CTkFrame):
    """Sessions screen."""

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = SessionsRepository()
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
            active_key="sessions",
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
            text="Sessions",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Scheduled learning sessions",
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
            rows = self.repository.fetch_sessions(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Sessions query failed: {exc}", "error")
        else:
            self._render_rows(rows)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def confirm_session(self, session: SessionRecord) -> None:
        try:
            self.repository.confirm_session(
                session.session_id,
                int(self.user["user_id"]),
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Confirm session failed: {exc}", "error")
        else:
            self.refresh()
            self._show_message("Session confirmed successfully.", "success")

    def _render_rows(self, rows: list[SessionRecord]) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()

        if not rows:
            ctk.CTkLabel(
                self.rows_container,
                text="No sessions found",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, session in enumerate(rows):
            row = ctk.CTkFrame(self.rows_container, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            for column in range(8):
                row.grid_columnconfigure(column, weight=1)

            values = (
                str(session.session_id),
                self._format_date(session.session_date),
                session.meeting_detail or "Not provided",
                session.status,
                "Yes" if session.requester_confirmed else "No",
                "Yes" if session.offerer_confirmed else "No",
                self._format_date(session.completed_at) if session.completed_at else "-",
            )
            for column, value in enumerate(values):
                ctk.CTkLabel(
                    row,
                    text=value,
                    font=ctk.CTkFont(size=12, weight="bold" if column == 0 else "normal"),
                    text_color="#e2e8f0" if column in (0, 1) else "#94a3b8",
                    anchor="w",
                    wraplength=170,
                    justify="left",
                ).grid(row=0, column=column, sticky="ew", padx=10, pady=12)

            ctk.CTkButton(
                row,
                text="Confirm",
                command=lambda current=session: self.confirm_session(current),
                width=82,
                height=30,
                corner_radius=8,
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#e2e8f0",
                state="disabled" if self._user_already_confirmed(session) else "normal",
            ).grid(row=0, column=7, sticky="e", padx=10, pady=10)

    def _user_already_confirmed(self, session: SessionRecord) -> bool:
        user_id = int(self.user["user_id"])
        if session.requester_id == user_id:
            return bool(session.requester_confirmed)
        if session.offerer_id == user_id:
            return bool(session.offerer_confirmed)
        return True

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
