from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class RequestOption:
    label: str
    offer_id: int
    skill_id: int
    availability_id: int


@dataclass(frozen=True)
class RequestRecord:
    request_id: int
    skill_name: str
    urgency: str
    status: str
    requested_at: object
    note: str
    requester_id: int
    offerer_id: int


class RequestsRepository:
    """Oracle operations for SkillSwap requests."""

    def fetch_request_options(self, user_id: int) -> list[RequestOption]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT
                        O.OFFER_ID,
                        SK.SKILL_ID,
                        SK.SKILL_NAME,
                        U.NAME,
                        A.AVAILABILITY_ID,
                        A.DAY_OF_WEEK,
                        A.TIME_SLOT
                    FROM OFFERS O
                    JOIN SKILLS SK
                      ON O.SKILL_ID = SK.SKILL_ID
                    JOIN USERS U
                      ON O.USER_ID = U.USER_ID
                    JOIN AVAILABILITY A
                      ON O.OFFER_ID = A.OFFER_ID
                    WHERE O.USER_ID <> :user_id
                      AND U.STATUS = :active_status
                    ORDER BY SK.SKILL_NAME, U.NAME, A.DAY_OF_WEEK, A.TIME_SLOT
                    """,
                    {"user_id": user_id, "active_status": "ACTIVE"},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        options: list[RequestOption] = []
        for row in rows:
            label = f"{row[2]} with {row[3]} - {row[5]} {row[6]} - Offer {int(row[0])}"
            options.append(
                RequestOption(
                    label=label,
                    offer_id=int(row[0]),
                    skill_id=int(row[1]),
                    availability_id=int(row[4]),
                )
            )
        return options

    def fetch_requests(self, user_id: int) -> list[RequestRecord]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT
                        R.REQUEST_ID,
                        SK.SKILL_NAME,
                        R.URGENCY,
                        R.STATUS,
                        R.REQUESTED_AT,
                        R.NOTE,
                        R.USER_ID,
                        O.USER_ID
                    FROM REQUESTS R
                    JOIN SKILLS SK
                      ON R.SKILL_ID = SK.SKILL_ID
                    JOIN OFFERS O
                      ON R.OFFER_ID = O.OFFER_ID
                    WHERE R.USER_ID = :user_id
                       OR O.USER_ID = :user_id
                    ORDER BY R.REQUESTED_AT DESC, R.REQUEST_ID DESC
                    """,
                    {"user_id": user_id},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            RequestRecord(
                request_id=int(row[0]),
                skill_name=str(row[1]),
                urgency=str(row[2]),
                status=str(row[3]),
                requested_at=row[4],
                note=str(row[5] or ""),
                requester_id=int(row[6]),
                offerer_id=int(row[7]),
            )
            for row in rows
        ]

    def create_request(
        self,
        user_id: int,
        option: RequestOption,
        urgency: str,
        note: str,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO REQUESTS (
                        USER_ID,
                        SKILL_ID,
                        OFFER_ID,
                        SELECTED_AVAILABILITY_ID,
                        URGENCY,
                        NOTE
                    )
                    VALUES (
                        :user_id,
                        :skill_id,
                        :offer_id,
                        :availability_id,
                        :urgency,
                        :note
                    )
                    """,
                    {
                        "user_id": user_id,
                        "skill_id": option.skill_id,
                        "offer_id": option.offer_id,
                        "availability_id": option.availability_id,
                        "urgency": urgency,
                        "note": note.strip() or None,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    def cancel_request(self, request_id: int, user_id: int) -> None:
        self._update_requester_status(request_id, user_id, "CANCELLED")

    def approve_request(self, request_id: int, user_id: int) -> None:
        self._update_offerer_status(request_id, user_id, "ACCEPTED")

    def reject_request(self, request_id: int, user_id: int) -> None:
        self._update_offerer_status(request_id, user_id, "REJECTED")

    def _update_requester_status(
        self,
        request_id: int,
        user_id: int,
        status: str,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE REQUESTS
                    SET STATUS = :status
                    WHERE REQUEST_ID = :request_id
                      AND USER_ID = :user_id
                      AND STATUS IN ('PENDING', 'ACCEPTED')
                    """,
                    {"status": status, "request_id": request_id, "user_id": user_id},
                )
                if cursor.rowcount != 1:
                    raise ValueError("Request cannot be cancelled.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    def _update_offerer_status(
        self,
        request_id: int,
        user_id: int,
        status: str,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE REQUESTS
                    SET STATUS = :status
                    WHERE REQUEST_ID = :request_id
                      AND STATUS = :pending_status
                      AND EXISTS (
                          SELECT 1
                          FROM OFFERS O
                          WHERE O.OFFER_ID = REQUESTS.OFFER_ID
                            AND O.USER_ID = :user_id
                      )
                    """,
                    {
                        "status": status,
                        "request_id": request_id,
                        "pending_status": "PENDING",
                        "user_id": user_id,
                    },
                )
                if cursor.rowcount != 1:
                    raise ValueError("Request cannot be updated.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()


class RequestsPage(ctk.CTkFrame):
    """Request creation and review screen."""

    URGENCIES = ("LOW", "MEDIUM", "HIGH")
    NO_OPTIONS = "No available offers"

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = RequestsRepository()
        self.option_lookup: dict[str, RequestOption] = {}

        self.message_var = ctk.StringVar(value="")
        self.option_var = ctk.StringVar(value=self.NO_OPTIONS)
        self.urgency_var = ctk.StringVar(value=self.URGENCIES[0])
        self.note_var = ctk.StringVar()

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
            active_key="requests",
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
        self._build_create_panel()
        self._build_requests_panel()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Requests",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Skill requests and offer responses",
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

    def _build_create_panel(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        panel.grid_columnconfigure(0, weight=2)
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_columnconfigure(2, weight=2)

        ctk.CTkLabel(
            panel,
            text="New Request",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=18, pady=(18, 12))

        self.option_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.option_var,
            values=[self.NO_OPTIONS],
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.option_menu.grid(row=1, column=0, sticky="ew", padx=(18, 8), pady=(0, 18))

        self.urgency_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.urgency_var,
            values=list(self.URGENCIES),
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.urgency_menu.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 18))

        self.note_entry = ctk.CTkEntry(
            panel,
            textvariable=self.note_var,
            placeholder_text="Note",
            height=42,
            border_width=1,
            border_color="#334155",
            fg_color="#0f172a",
            text_color="#f8fafc",
            placeholder_text_color="#64748b",
            corner_radius=8,
        )
        self.note_entry.grid(row=1, column=2, sticky="ew", padx=8, pady=(0, 18))

        self.create_button = ctk.CTkButton(
            panel,
            text="Create Request",
            command=self.create_request,
            height=42,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#042f2e",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.create_button.grid(row=1, column=3, sticky="ew", padx=(8, 18), pady=(0, 18))

    def _build_requests_panel(self) -> None:
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
            options = self.repository.fetch_request_options(int(self.user["user_id"]))
            requests = self.repository.fetch_requests(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Requests query failed: {exc}", "error")
        else:
            self._render_options(options)
            self._render_rows(requests)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def create_request(self) -> None:
        option = self.option_lookup.get(self.option_var.get())
        if option is None:
            self._show_message("Select an available offer before creating a request.", "error")
            return

        note = self.note_var.get()
        if len(note) > 500:
            self._show_message("Note cannot exceed 500 characters.", "error")
            return

        self.create_button.configure(state="disabled", text="Creating...")
        self.update_idletasks()

        try:
            self.repository.create_request(
                user_id=int(self.user["user_id"]),
                option=option,
                urgency=self.urgency_var.get(),
                note=note,
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Create request failed: {exc}", "error")
        else:
            self.note_var.set("")
            self.refresh()
            self._show_message("Request created successfully.", "success")
        finally:
            self.create_button.configure(state="normal", text="Create Request")

    def cancel_request(self, request: RequestRecord) -> None:
        self._apply_request_action(
            action=lambda: self.repository.cancel_request(
                request.request_id,
                int(self.user["user_id"]),
            ),
            success_message="Request cancelled successfully.",
            failure_prefix="Cancel request failed",
        )

    def approve_request(self, request: RequestRecord) -> None:
        self._apply_request_action(
            action=lambda: self.repository.approve_request(
                request.request_id,
                int(self.user["user_id"]),
            ),
            success_message="Request approved successfully.",
            failure_prefix="Approve request failed",
        )

    def reject_request(self, request: RequestRecord) -> None:
        self._apply_request_action(
            action=lambda: self.repository.reject_request(
                request.request_id,
                int(self.user["user_id"]),
            ),
            success_message="Request rejected successfully.",
            failure_prefix="Reject request failed",
        )

    def _apply_request_action(
        self,
        action: Callable[[], None],
        success_message: str,
        failure_prefix: str,
    ) -> None:
        try:
            action()
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"{failure_prefix}: {exc}", "error")
        else:
            self.refresh()
            self._show_message(success_message, "success")

    def _render_options(self, options: list[RequestOption]) -> None:
        if not options:
            self.option_lookup = {}
            self.option_var.set(self.NO_OPTIONS)
            self.option_menu.configure(values=[self.NO_OPTIONS], state="disabled")
            self.create_button.configure(state="disabled")
            return

        lookup = {option.label: option for option in options}
        current = self.option_var.get()
        values = list(lookup)
        self.option_lookup = lookup
        self.option_menu.configure(values=values, state="normal")
        self.option_var.set(current if current in lookup else values[0])
        self.create_button.configure(state="normal")

    def _render_rows(self, requests: list[RequestRecord]) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()

        if not requests:
            ctk.CTkLabel(
                self.rows_container,
                text="No requests found",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, request in enumerate(requests):
            row = ctk.CTkFrame(self.rows_container, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            for column in range(7):
                row.grid_columnconfigure(column, weight=1)

            values = (
                str(request.request_id),
                request.skill_name,
                request.urgency,
                request.status,
                self._format_date(request.requested_at),
                request.note or "No note",
            )
            for column, value in enumerate(values):
                ctk.CTkLabel(
                    row,
                    text=value,
                    font=ctk.CTkFont(size=12, weight="bold" if column in (0, 1) else "normal"),
                    text_color="#e2e8f0" if column in (0, 1) else "#94a3b8",
                    anchor="w",
                    wraplength=150 if column != 5 else 220,
                    justify="left",
                ).grid(row=0, column=column, sticky="ew", padx=10, pady=12)

            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=6, sticky="e", padx=8, pady=8)
            self._render_actions(actions, request)

    def _render_actions(self, parent: ctk.CTkFrame, request: RequestRecord) -> None:
        user_id = int(self.user["user_id"])
        column = 0

        if request.offerer_id == user_id and request.status == "PENDING":
            self._small_button(parent, "Approve", lambda: self.approve_request(request), column)
            column += 1
            self._small_button(parent, "Reject", lambda: self.reject_request(request), column)
            column += 1

        if request.requester_id == user_id and request.status in {"PENDING", "ACCEPTED"}:
            self._small_button(parent, "Cancel", lambda: self.cancel_request(request), column)

        if not parent.winfo_children():
            ctk.CTkLabel(
                parent,
                text="-",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0)

    def _small_button(
        self,
        parent: ctk.CTkFrame,
        text: str,
        command: Callable[[], None],
        column: int,
    ) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=72,
            height=30,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
        ).grid(row=0, column=column, padx=3)

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
