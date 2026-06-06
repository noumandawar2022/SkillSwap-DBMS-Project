from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable

import customtkinter as ctk

from database.db_connection import DatabaseConnectionError, connection_scope
from widgets.sidebar import Sidebar


@dataclass(frozen=True)
class SkillRecord:
    skill_id: int
    skill_name: str
    category_id: int
    category_name: str


@dataclass(frozen=True)
class CategoryRecord:
    category_id: int
    category_name: str


class SkillsRepository:
    """Read-only Skill and Skill Category queries."""

    def fetch_categories(self) -> list[CategoryRecord]:
        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT CATEGORY_ID, CATEGORY_NAME
                    FROM SKILL_CATEGORIES
                    ORDER BY CATEGORY_NAME, CATEGORY_ID
                    """
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            CategoryRecord(category_id=int(row[0]), category_name=str(row[1]))
            for row in rows
        ]

    def fetch_skills(
        self,
        search_text: str = "",
        category_id: int | None = None,
    ) -> list[SkillRecord]:
        clauses: list[str] = []
        params: dict[str, object] = {}

        if search_text.strip():
            clauses.append("LOWER(SK.SKILL_NAME) LIKE :search_pattern")
            params["search_pattern"] = f"%{search_text.strip().lower()}%"

        if category_id is not None:
            clauses.append("SC.CATEGORY_ID = :category_id")
            params["category_id"] = category_id

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        sql = f"""
            SELECT
                SK.SKILL_ID,
                SK.SKILL_NAME,
                SC.CATEGORY_ID,
                SC.CATEGORY_NAME
            FROM SKILLS SK
            JOIN SKILL_CATEGORIES SC
              ON SK.CATEGORY_ID = SC.CATEGORY_ID
            {where_clause}
            ORDER BY SK.SKILL_NAME, SC.CATEGORY_NAME
        """

        with connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            finally:
                cursor.close()

        return [
            SkillRecord(
                skill_id=int(row[0]),
                skill_name=str(row[1]),
                category_id=int(row[2]),
                category_name=str(row[3]),
            )
            for row in rows
        ]


class SkillsPage(ctk.CTkFrame):
    """Skills browser with search and category filtering."""

    ALL_CATEGORIES = "All Categories"

    def __init__(
        self,
        master: ctk.CTk,
        user: dict,
        on_navigate: Callable[[str], None],
        on_logout: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="#0b1018")
        self.user = user
        self.repository = SkillsRepository()

        self.search_var = ctk.StringVar()
        self.category_var = ctk.StringVar(value=self.ALL_CATEGORIES)
        self.message_var = ctk.StringVar(value="")
        self.category_lookup: dict[str, int | None] = {self.ALL_CATEGORIES: None}

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
            active_key="skills",
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
        self._build_filters()
        self._build_table()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Skills",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#f8fafc",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Skill catalog",
            font=ctk.CTkFont(size=14),
            text_color="#94a3b8",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _build_message_banner(self) -> None:
        self.message_banner = ctk.CTkLabel(
            self.content,
            textvariable=self.message_var,
            fg_color="#451a1a",
            text_color="#fecaca",
            corner_radius=8,
            height=38,
            font=ctk.CTkFont(size=13),
            wraplength=780,
            justify="left",
        )
        self.message_banner.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 16))
        self.message_banner.grid_remove()

    def _build_filters(self) -> None:
        filters = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        filters.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        filters.grid_columnconfigure(0, weight=2)
        filters.grid_columnconfigure(1, weight=1)

        self.search_entry = ctk.CTkEntry(
            filters,
            textvariable=self.search_var,
            placeholder_text="Search by skill name",
            height=42,
            border_width=1,
            border_color="#334155",
            fg_color="#0f172a",
            text_color="#f8fafc",
            placeholder_text_color="#64748b",
            corner_radius=8,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(18, 10), pady=18)
        self.search_entry.bind("<Return>", self._refresh_from_event)

        self.category_menu = ctk.CTkOptionMenu(
            filters,
            variable=self.category_var,
            values=[self.ALL_CATEGORIES],
            command=lambda _selected: self.refresh(load_categories=False),
            height=42,
            corner_radius=8,
            fg_color="#0f172a",
            button_color="#1e293b",
            button_hover_color="#334155",
            text_color="#f8fafc",
            dropdown_fg_color="#111827",
            dropdown_hover_color="#1e293b",
        )
        self.category_menu.grid(row=0, column=1, sticky="ew", padx=10, pady=18)

        self.search_button = ctk.CTkButton(
            filters,
            text="Search",
            command=lambda: self.refresh(load_categories=False),
            width=100,
            height=42,
            corner_radius=8,
            fg_color="#14b8a6",
            hover_color="#0f766e",
            text_color="#042f2e",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.search_button.grid(row=0, column=2, sticky="e", padx=10, pady=18)

        self.refresh_button = ctk.CTkButton(
            filters,
            text="Refresh",
            command=self.refresh,
            width=110,
            height=42,
            corner_radius=8,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.refresh_button.grid(row=0, column=3, sticky="e", padx=(10, 18), pady=18)

    def _build_table(self) -> None:
        panel = ctk.CTkFrame(self.content, fg_color="#111827", corner_radius=8)
        panel.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 28))
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Skill Name",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#64748b",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Category Name",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#64748b",
        ).grid(row=0, column=1, sticky="w")

        self.rows_container = ctk.CTkFrame(panel, fg_color="transparent")
        self.rows_container.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        self.rows_container.grid_columnconfigure(0, weight=1)

    def refresh(self, load_categories: bool = True) -> None:
        self.search_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled", text="Loading...")
        self.message_banner.grid_remove()
        self.update_idletasks()

        try:
            if load_categories:
                categories = self.repository.fetch_categories()
                self._render_categories(categories)

            category_id = self.category_lookup.get(self.category_var.get())
            rows = self.repository.fetch_skills(
                search_text=self.search_var.get(),
                category_id=category_id,
            )
        except DatabaseConnectionError as exc:
            self._show_error(str(exc))
        except Exception as exc:
            self._show_error(f"Skills query failed: {exc}")
        else:
            self._render_rows(rows)
        finally:
            self.search_button.configure(state="normal")
            self.refresh_button.configure(state="normal", text="Refresh")

    def _render_categories(self, categories: list[CategoryRecord]) -> None:
        counts = Counter(category.category_name for category in categories)
        lookup: dict[str, int | None] = {self.ALL_CATEGORIES: None}

        for category in categories:
            label = category.category_name
            if counts[category.category_name] > 1:
                label = f"{category.category_name} ({category.category_id})"
            lookup[label] = category.category_id

        current = self.category_var.get()
        values = list(lookup)
        self.category_lookup = lookup
        self.category_menu.configure(values=values)
        self.category_var.set(current if current in lookup else self.ALL_CATEGORIES)

    def _render_rows(self, rows: list[SkillRecord]) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()

        if not rows:
            ctk.CTkLabel(
                self.rows_container,
                text="No skills found",
                font=ctk.CTkFont(size=13),
                text_color="#64748b",
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        for index, skill in enumerate(rows):
            row = ctk.CTkFrame(self.rows_container, fg_color="#0f172a", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row,
                text=skill.skill_name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#e2e8f0",
                anchor="w",
                wraplength=320,
                justify="left",
            ).grid(row=0, column=0, sticky="ew", padx=14, pady=12)

            ctk.CTkLabel(
                row,
                text=skill.category_name,
                font=ctk.CTkFont(size=13),
                text_color="#94a3b8",
                anchor="w",
                wraplength=320,
                justify="left",
            ).grid(row=0, column=1, sticky="ew", padx=14, pady=12)

    def _show_error(self, message: str) -> None:
        self.message_var.set(message)
        self.message_banner.grid()

    def _refresh_from_event(self, _event) -> None:
        self.refresh(load_categories=False)
