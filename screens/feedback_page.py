from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class FeedbackSessionOption:
    label: str
    session_id: int


@dataclass(frozen=True)
class FeedbackRecord:
    score: int
    feedback_text: str
    given_at: object


class FeedbackRepository:
    """Oracle operations for feedback."""

    def fetch_feedback_sessions(self, user_id: int) -> list[FeedbackSessionOption]:
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
                    WHERE (R.USER_ID = :user_id OR O.USER_ID = :user_id)
                      AND S.STATUS = :completed_status
                      AND NOT EXISTS (
                          SELECT 1
                          FROM FEEDBACK F
                          WHERE F.SESSION_ID = S.SESSION_ID
                      )
                    ORDER BY S.SESSION_DATE DESC, S.SESSION_ID DESC
                    """,
                    {"user_id": user_id, "completed_status": "COMPLETED"},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            FeedbackSessionOption(
                label=f"Session {int(row[0])} - {row[1]} - {self._format_date(row[2])}",
                session_id=int(row[0]),
            )
            for row in rows
        ]

    def fetch_history(self, user_id: int) -> list[FeedbackRecord]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT
                        F.SCORE,
                        F.FEEDBACK_TEXT,
                        F.GIVEN_AT
                    FROM FEEDBACK F
                    JOIN SESSIONS S
                      ON F.SESSION_ID = S.SESSION_ID
                    JOIN REQUESTS R
                      ON S.REQUEST_ID = R.REQUEST_ID
                    JOIN OFFERS O
                      ON S.OFFER_ID = O.OFFER_ID
                    WHERE R.USER_ID = :user_id
                       OR O.USER_ID = :user_id
                    ORDER BY F.GIVEN_AT DESC, F.FEEDBACK_ID DESC
                    """,
                    {"user_id": user_id},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            FeedbackRecord(
                score=int(row[0]),
                feedback_text=str(row[1] or ""),
                given_at=row[2],
            )
            for row in rows
        ]

    def submit_feedback(
        self,
        session_id: int,
        user_id: int,
        score: int,
        feedback_text: str,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                self._ensure_completed_session_access(cursor, session_id, user_id)
                cursor.execute(
                    """
                    INSERT INTO FEEDBACK (
                        SESSION_ID,
                        SCORE,
                        FEEDBACK_TEXT
                    )
                    VALUES (
                        :session_id,
                        :score,
                        :feedback_text
                    )
                    """,
                    {
                        "session_id": session_id,
                        "score": score,
                        "feedback_text": feedback_text.strip() or None,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    @staticmethod
    def _ensure_completed_session_access(cursor, session_id: int, user_id: int) -> None:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM SESSIONS S
            JOIN REQUESTS R
              ON S.REQUEST_ID = R.REQUEST_ID
            JOIN OFFERS O
              ON S.OFFER_ID = O.OFFER_ID
            WHERE S.SESSION_ID = :session_id
              AND S.STATUS = :completed_status
              AND (R.USER_ID = :user_id OR O.USER_ID = :user_id)
            """,
            {
                "session_id": session_id,
                "completed_status": "COMPLETED",
                "user_id": user_id,
            },
        )
        row = cursor.fetchone()
        if not row or int(row[0]) == 0:
            raise ValueError("Completed session not found.")

    @staticmethod
    def _format_date(value: object) -> str:
        if isinstance(value, datetime | date):
            return value.strftime("%Y-%m-%d")
        return str(value or "")


class FeedbackPage(ctk.CTkFrame):
    """Feedback submission and history screen."""

    NO_SESSIONS = "No completed sessions"
    SCORES = ("1", "2", "3", "4", "5")

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = FeedbackRepository()
        self.session_lookup: dict[str, int] = {}

        self.message_var = ctk.StringVar(value="")
        self.session_var = ctk.StringVar(value=self.NO_SESSIONS)
        self.score_var = ctk.StringVar(value=self.SCORES[-1])
        self.feedback_var = ctk.StringVar()

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
            active_key="feedback",
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
        self._build_submit_panel()
        self._build_history_panel()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Feedback",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Session ratings and feedback history",
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

    def _build_submit_panel(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        panel.grid_columnconfigure(0, weight=2)
        panel.grid_columnconfigure(2, weight=3)

        ctk.CTkLabel(
            panel,
            text="Submit Feedback",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=18, pady=(18, 12))

        self.session_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.session_var,
            values=[self.NO_SESSIONS],
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.session_menu.grid(row=1, column=0, sticky="ew", padx=(18, 8), pady=(0, 18))

        self.score_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.score_var,
            values=list(self.SCORES),
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.score_menu.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 18))

        self.feedback_entry = ctk.CTkEntry(
            panel,
            textvariable=self.feedback_var,
            placeholder_text="Feedback text",
            height=42,
            border_width=1,
            border_color="#334155",
            fg_color="#0f172a",
            text_color="#f8fafc",
            placeholder_text_color="#64748b",
            corner_radius=8,
        )
        self.feedback_entry.grid(row=1, column=2, sticky="ew", padx=8, pady=(0, 18))
        self.feedback_entry.bind("<Return>", self._submit_from_event)

        self.submit_button = ctk.CTkButton(
            panel,
            text="Submit",
            command=self.submit_feedback,
            height=42,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#042f2e",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.submit_button.grid(row=1, column=3, sticky="ew", padx=(8, 18), pady=(0, 18))

    def _build_history_panel(self) -> None:
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
            sessions = self.repository.fetch_feedback_sessions(int(self.user["user_id"]))
            history = self.repository.fetch_history(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Feedback query failed: {exc}", "error")
        else:
            self._render_session_options(sessions)
            self._render_rows(history)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def submit_feedback(self) -> None:
        session_id = self.session_lookup.get(self.session_var.get())
        feedback_text = self.feedback_var.get()

        if session_id is None:
            self._show_message("Select a completed session before submitting feedback.", "error")
            return

        if len(feedback_text) > 1000:
            self._show_message("Feedback text cannot exceed 1000 characters.", "error")
            return

        self.submit_button.configure(state="disabled", text="Submitting...")
        self.update_idletasks()

        try:
            self.repository.submit_feedback(
                session_id=session_id,
                user_id=int(self.user["user_id"]),
                score=int(self.score_var.get()),
                feedback_text=feedback_text,
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Submit feedback failed: {exc}", "error")
        else:
            self.feedback_var.set("")
            self.refresh()
            self._show_message("Feedback submitted successfully.", "success")
        finally:
            self.submit_button.configure(state="normal", text="Submit")

    def _render_session_options(self, sessions: list[FeedbackSessionOption]) -> None:
        if not sessions:
            self.session_lookup = {}
            self.session_var.set(self.NO_SESSIONS)
            self.session_menu.configure(values=[self.NO_SESSIONS], state="disabled")
            self.submit_button.configure(state="disabled")
            return

        lookup = {session.label: session.session_id for session in sessions}
        current = self.session_var.get()
        values = list(lookup)
        self.session_lookup = lookup
        self.session_menu.configure(values=values, state="normal")
        self.session_var.set(current if current in lookup else values[0])
        self.submit_button.configure(state="normal")

    def _render_rows(self, rows: list[FeedbackRecord]) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()

        if not rows:
            ctk.CTkLabel(
                self.rows_container,
                text="No feedback found",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, feedback in enumerate(rows):
            row = ctk.CTkFrame(self.rows_container, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=4)
            row.grid_columnconfigure(2, weight=1)

            values = (
                str(feedback.score),
                feedback.feedback_text or "No text",
                self._format_date(feedback.given_at),
            )
            for column, value in enumerate(values):
                ctk.CTkLabel(
                    row,
                    text=value,
                    font=ctk.CTkFont(size=13, weight="bold" if column == 0 else "normal"),
                    text_color="#e2e8f0" if column in (0, 1) else "#94a3b8",
                    anchor="w",
                    wraplength=520 if column == 1 else 150,
                    justify="left",
                ).grid(row=0, column=column, sticky="ew", padx=12, pady=12)

    def _submit_from_event(self, _event) -> None:
        self.submit_feedback()

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
