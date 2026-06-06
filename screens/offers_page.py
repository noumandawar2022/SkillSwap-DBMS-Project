from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class SkillOption:
    skill_id: int
    skill_name: str


@dataclass(frozen=True)
class OfferRecord:
    offer_id: int
    skill_id: int
    skill_name: str
    skill_level: str
    session_mode: str
    created_at: object


class OffersRepository:
    """Read and write operations for the logged-in user's offers."""

    def fetch_skills(self) -> list[SkillOption]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT SKILL_ID, SKILL_NAME
                    FROM SKILLS
                    ORDER BY SKILL_NAME, SKILL_ID
                    """
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            SkillOption(skill_id=int(row[0]), skill_name=str(row[1]))
            for row in rows
        ]

    def fetch_user_offers(self, user_id: int) -> list[OfferRecord]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT
                        O.OFFER_ID,
                        O.SKILL_ID,
                        SK.SKILL_NAME,
                        O.SKILL_LEVEL,
                        O.SESSION_MODE,
                        O.CREATED_AT
                    FROM OFFERS O
                    JOIN SKILLS SK
                      ON O.SKILL_ID = SK.SKILL_ID
                    WHERE O.USER_ID = :user_id
                    ORDER BY O.CREATED_AT DESC, SK.SKILL_NAME
                    """,
                    {"user_id": user_id},
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            OfferRecord(
                offer_id=int(row[0]),
                skill_id=int(row[1]),
                skill_name=str(row[2]),
                skill_level=str(row[3]),
                session_mode=str(row[4]),
                created_at=row[5],
            )
            for row in rows
        ]

    def create_offer(
        self,
        user_id: int,
        skill_id: int,
        skill_level: str,
        session_mode: str,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO OFFERS (
                        USER_ID,
                        SKILL_ID,
                        SKILL_LEVEL,
                        SESSION_MODE
                    )
                    VALUES (
                        :user_id,
                        :skill_id,
                        :skill_level,
                        :session_mode
                    )
                    """,
                    {
                        "user_id": user_id,
                        "skill_id": skill_id,
                        "skill_level": skill_level,
                        "session_mode": session_mode,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    def update_offer(
        self,
        offer_id: int,
        user_id: int,
        skill_id: int,
        skill_level: str,
        session_mode: str,
    ) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE OFFERS
                    SET SKILL_ID = :skill_id,
                        SKILL_LEVEL = :skill_level,
                        SESSION_MODE = :session_mode
                    WHERE OFFER_ID = :offer_id
                      AND USER_ID = :user_id
                    """,
                    {
                        "offer_id": offer_id,
                        "user_id": user_id,
                        "skill_id": skill_id,
                        "skill_level": skill_level,
                        "session_mode": session_mode,
                    },
                )
                if cursor.rowcount != 1:
                    raise ValueError("Offer not found.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    def delete_offer(self, offer_id: int, user_id: int) -> None:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    DELETE FROM OFFERS
                    WHERE OFFER_ID = :offer_id
                      AND USER_ID = :user_id
                    """,
                    {"offer_id": offer_id, "user_id": user_id},
                )
                if cursor.rowcount != 1:
                    raise ValueError("Offer not found.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()


class OffersPage(ctk.CTkFrame):
    """Manage offers belonging to the logged-in user."""

    SKILL_LEVELS = ("BEGINNER", "INTERMEDIATE", "EXPERT")
    SESSION_MODES = ("ONLINE", "IN_PERSON", "BOTH")
    NO_SKILLS_LABEL = "No skills available"

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = OffersRepository()

        self.message_var = ctk.StringVar(value="")
        self.skill_var = ctk.StringVar(value=self.NO_SKILLS_LABEL)
        self.level_var = ctk.StringVar(value=self.SKILL_LEVELS[0])
        self.mode_var = ctk.StringVar(value=self.SESSION_MODES[0])
        self.selected_offer_id: int | None = None
        self.skill_lookup: dict[str, int] = {}
        self.skill_label_by_id: dict[int, str] = {}

        self._build_layout(on_navigate, on_logout)
        self.after(100, self.refresh)

    def _build_layout(
        self,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        sidebar = Sidebar(
            self,
            user=self.user,
            active_key="offers",
            on_select=on_navigate,
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
        self._build_message_banner()
        self._build_form()
        self._build_table()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Offers",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Your teaching skills and session preferences",
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

    def _build_form(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        panel.grid_columnconfigure(0, weight=2)
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            panel,
            text="Offer Details",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(18, 12))

        self.skill_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.skill_var,
            values=[self.NO_SKILLS_LABEL],
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.skill_menu.grid(row=1, column=0, sticky="ew", padx=(18, 8), pady=(0, 14))

        self.level_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.level_var,
            values=list(self.SKILL_LEVELS),
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.level_menu.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 14))

        self.mode_menu = ctk.CTkOptionMenu(
            panel,
            variable=self.mode_var,
            values=list(self.SESSION_MODES),
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.mode_menu.grid(row=1, column=2, sticky="ew", padx=(8, 18), pady=(0, 14))

        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", padx=18, pady=(0, 18))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        actions.grid_columnconfigure(2, weight=1)

        self.create_button = ctk.CTkButton(
            actions,
            text="Create Offer",
            command=self.create_offer,
            height=42,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#042f2e",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.create_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.save_button = ctk.CTkButton(
            actions,
            text="Save Changes",
            command=self.save_offer,
            height=42,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
        )
        self.save_button.grid(row=0, column=1, sticky="ew", padx=8)

        self.clear_button = ctk.CTkButton(
            actions,
            text="Clear",
            command=self.clear_form,
            height=42,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.clear_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    def _build_table(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 28))
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        header.grid_columnconfigure(0, weight=2)
        header.grid_columnconfigure(1, weight=1)
        header.grid_columnconfigure(2, weight=1)
        header.grid_columnconfigure(3, weight=1)
        header.grid_columnconfigure(4, weight=1)

        for column, title in enumerate(
            ("Skill Name", "Skill Level", "Session Mode", "Created Date", "Actions")
        ):
            ctk.CTkLabel(
                header,
                text=title,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#64748b",
            ).grid(row=0, column=column, sticky="w", padx=(0, 8))

        self.rows_container = ctk.CTkFrame(panel, fg_color="transparent")
        self.rows_container.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        self.rows_container.grid_columnconfigure(0, weight=1)

    def refresh(self) -> None:
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.message_banner.grid_remove()
        self.update_idletasks()

        try:
            skills = self.repository.fetch_skills()
            offers = self.repository.fetch_user_offers(int(self.user["user_id"]))
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Offers query failed: {exc}", "error")
        else:
            self._render_skill_options(skills)
            self._render_rows(offers)
        finally:
            self.refresh_button.configure(state="normal", text="Refresh")

    def create_offer(self) -> None:
        skill_id = self._selected_skill_id()
        if skill_id is None:
            self._show_message("Select a valid skill before creating an offer.", "error")
            return

        self.create_button.configure(state="disabled", text="Creating...")
        self.update_idletasks()

        try:
            self.repository.create_offer(
                user_id=int(self.user["user_id"]),
                skill_id=skill_id,
                skill_level=self.level_var.get(),
                session_mode=self.mode_var.get(),
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Create offer failed: {exc}", "error")
        else:
            self.clear_form(reset_selection=False)
            self.refresh()
            self._show_message("Offer created successfully.", "success")
        finally:
            self.create_button.configure(state="normal", text="Create Offer")

    def save_offer(self) -> None:
        if self.selected_offer_id is None:
            self._show_message("Select an offer to edit.", "error")
            return

        skill_id = self._selected_skill_id()
        if skill_id is None:
            self._show_message("Select a valid skill before saving changes.", "error")
            return

        self.save_button.configure(state="disabled", text="Saving...")
        self.update_idletasks()

        try:
            self.repository.update_offer(
                offer_id=self.selected_offer_id,
                user_id=int(self.user["user_id"]),
                skill_id=skill_id,
                skill_level=self.level_var.get(),
                session_mode=self.mode_var.get(),
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Save offer failed: {exc}", "error")
        else:
            self.clear_form(reset_selection=False)
            self.refresh()
            self._show_message("Offer updated successfully.", "success")
        finally:
            self.save_button.configure(text="Save Changes")
            if self.selected_offer_id is not None:
                self.save_button.configure(state="normal")

    def delete_offer(self, offer: OfferRecord) -> None:
        confirmed = messagebox.askyesno(
            "Delete Offer",
            f"Delete your offer for {offer.skill_name}?",
        )
        if not confirmed:
            return

        try:
            self.repository.delete_offer(
                offer_id=offer.offer_id,
                user_id=int(self.user["user_id"]),
            )
        except DatabaseConnectionError as exc:
            self._show_message(str(exc), "error")
        except Exception as exc:
            self._show_message(f"Delete offer failed: {exc}", "error")
        else:
            if self.selected_offer_id == offer.offer_id:
                self.clear_form(reset_selection=False)
            self.refresh()
            self._show_message("Offer deleted successfully.", "success")

    def clear_form(self, reset_selection: bool = True) -> None:
        self.selected_offer_id = None
        if reset_selection and self.skill_lookup:
            self.skill_var.set(next(iter(self.skill_lookup)))
        self.level_var.set(self.SKILL_LEVELS[0])
        self.mode_var.set(self.SESSION_MODES[0])
        self.save_button.configure(state="disabled", text="Save Changes")
        self.create_button.configure(state="normal", text="Create Offer")

    def _render_skill_options(self, skills: list[SkillOption]) -> None:
        if not skills:
            self.skill_lookup = {}
            self.skill_label_by_id = {}
            self.skill_var.set(self.NO_SKILLS_LABEL)
            self.skill_menu.configure(values=[self.NO_SKILLS_LABEL], state="disabled")
            self.create_button.configure(state="disabled")
            self.save_button.configure(state="disabled")
            return

        counts = Counter(skill.skill_name for skill in skills)
        skill_lookup: dict[str, int] = {}
        label_by_id: dict[int, str] = {}

        for skill in skills:
            label = skill.skill_name
            if counts[skill.skill_name] > 1:
                label = f"{skill.skill_name} ({skill.skill_id})"
            skill_lookup[label] = skill.skill_id
            label_by_id[skill.skill_id] = label

        self.skill_lookup = skill_lookup
        self.skill_label_by_id = label_by_id
        values = list(skill_lookup)
        current = self.skill_var.get()
        self.skill_menu.configure(values=values, state="normal")
        self.skill_var.set(current if current in skill_lookup else values[0])
        self.create_button.configure(state="normal")

    def _render_rows(self, offers: list[OfferRecord]) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()

        if not offers:
            ctk.CTkLabel(
                self.rows_container,
                text="No offers found",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, offer in enumerate(offers):
            row = ctk.CTkFrame(self.rows_container, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(0, weight=2)
            row.grid_columnconfigure(1, weight=1)
            row.grid_columnconfigure(2, weight=1)
            row.grid_columnconfigure(3, weight=1)

            values = (
                offer.skill_name,
                offer.skill_level,
                offer.session_mode,
                self._format_date(offer.created_at),
            )
            for column, value in enumerate(values):
                ctk.CTkLabel(
                    row,
                    text=value,
                    font=ctk.CTkFont(size=13, weight="bold" if column == 0 else "normal"),
                    text_color="#e2e8f0" if column == 0 else "#94a3b8",
                    anchor="w",
                    wraplength=220,
                    justify="left",
                ).grid(row=0, column=column, sticky="ew", padx=12, pady=12)

            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=4, sticky="e", padx=10, pady=8)

            ctk.CTkButton(
                actions,
                text="Edit",
                width=66,
                height=32,
                corner_radius=8,
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#e2e8f0",
                command=lambda current_offer=offer: self.load_offer_for_edit(current_offer),
            ).grid(row=0, column=0, padx=(0, 6))

            ctk.CTkButton(
                actions,
                text="Delete",
                width=72,
                height=32,
                corner_radius=8,
                fg_color="#7f1d1d",
                hover_color="#991b1b",
                text_color="#fee2e2",
                command=lambda current_offer=offer: self.delete_offer(current_offer),
            ).grid(row=0, column=1)

    def load_offer_for_edit(self, offer: OfferRecord) -> None:
        self.selected_offer_id = offer.offer_id
        label = self.skill_label_by_id.get(offer.skill_id)
        if label is not None:
            self.skill_var.set(label)
        self.level_var.set(offer.skill_level)
        self.mode_var.set(offer.session_mode)
        self.save_button.configure(state="normal")
        self._show_message("Offer loaded for editing.", "info")

    def _selected_skill_id(self) -> int | None:
        return self.skill_lookup.get(self.skill_var.get())

    def _show_message(self, message: str, kind: str) -> None:
        colors = {
            "success": ("#064e3b", "#bbf7d0"),
            "error": ("#451a1a", "#fecaca"),
            "info": ("#0f172a", "#cbd5e1"),
        }
        fg_color, text_color = colors.get(kind, colors["info"])
        self.message_banner.configure(fg_color=fg_color, text_color=text_color)
        self.message_var.set(message)
        self.message_banner.grid()

    @staticmethod
    def _format_date(value: object) -> str:
        if isinstance(value, datetime | date):
            return value.strftime("%Y-%m-%d")
        return str(value or "")
