"""Compact, pill-based CustomTkinter interface for ERIC's Quoter."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageGrab, ImageOps, ImageTk

from .history import load_recent_customers, remember_customer
from .models import LocationSpec, QuoteMode, QuoteRequest
from .workbook_service import (
    MAX_LOCATIONS,
    WorkbookGenerationError,
    generate_quote,
    resource_root,
)

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

COLORS = {
    "mesh_base": "#075C88",
    "navy": "#173F60",
    "primary": "#086A9D",
    "primary_hover": "#075681",
    "primary_pressed": "#06486D",
    "tint": "#E8F4FA",
    "surface": "#FCFDFE",
    "surface_alt": "#F0F4F7",
    "surface_strong": "#E5EDF2",
    "text": "#142A3A",
    "muted": "#60717E",
    "border": "#D6E0E6",
    "error": "#B42318",
    "success": "#176B45",
    "focus": "#1296D4",
}


def _enable_keyboard_button(button: ctk.CTkButton, on_blur=None) -> None:
    """Add tab/space/return behavior to CustomTkinter's canvas button."""
    focus_target = button._canvas  # noqa: SLF001 - no public CTk focus hook
    focus_target.configure(takefocus=1)
    focus_target.bind("<Return>", lambda _event: button.invoke())
    focus_target.bind("<space>", lambda _event: button.invoke())
    focus_target.bind(
        "<FocusIn>",
        lambda _event: button.configure(
            border_width=2,
            border_color=COLORS["focus"],
        ),
    )

    def restore(_event=None) -> None:
        button.configure(border_width=0)
        if on_blur:
            on_blur()

    focus_target.bind("<FocusOut>", restore)


class MeshBackground(tk.Canvas):
    """Scale the supplied mesh across the complete application window."""

    def __init__(self, master) -> None:
        super().__init__(master, highlightthickness=0, bd=0, bg=COLORS["mesh_base"])
        self._source = Image.open(
            resource_root() / "GDI-BLUE_mesh-background-1.jpg"
        ).convert("RGB")
        self._photo: ImageTk.PhotoImage | None = None
        self._paint_job: str | None = None
        self.bind("<Configure>", self._schedule_paint)

    def _schedule_paint(self, _event=None) -> None:
        if self._paint_job:
            self.after_cancel(self._paint_job)
        self._paint_job = self.after(35, self._paint)

    def _paint(self) -> None:
        self._paint_job = None
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)
        image = ImageOps.fit(
            self._source,
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        self._photo = ImageTk.PhotoImage(image)
        self.delete("all")
        self.create_image(0, 0, image=self._photo, anchor="nw")


class LocationPill(ctk.CTkFrame):
    """One named location with a text-labelled required/optional state."""

    def __init__(self, master, index: int, on_change) -> None:
        super().__init__(
            master,
            height=52,
            corner_radius=26,
            fg_color=COLORS["surface"],
            border_width=1,
            border_color=COLORS["border"],
        )
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)
        self.index = index
        self._on_change = on_change
        self.name_var = tk.StringVar(value=f"Location {index}")
        self.optional_var = tk.BooleanVar(value=False)

        ctk.CTkLabel(
            self,
            text=f"{index:02d}",
            width=38,
            height=34,
            corner_radius=17,
            fg_color=COLORS["surface_alt"],
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
        ).grid(row=0, column=0, padx=(9, 4), pady=9)

        self.name_entry = ctk.CTkEntry(
            self,
            textvariable=self.name_var,
            height=38,
            corner_radius=19,
            border_width=0,
            fg_color="transparent",
            text_color=COLORS["text"],
            placeholder_text=f"Location {index}",
            font=ctk.CTkFont("Segoe UI", 12),
        )
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=7)

        self.state_button = ctk.CTkButton(
            self,
            text="Required",
            width=104,
            height=36,
            corner_radius=18,
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["surface_strong"],
            text_color=COLORS["navy"],
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
            command=self._toggle_optional,
        )
        self.state_button.grid(row=0, column=2, padx=(5, 9), pady=8)
        _enable_keyboard_button(self.state_button, self._restore_state_style)
        self.name_var.trace_add("write", lambda *_: self._on_change())

    def _toggle_optional(self) -> None:
        self.optional_var.set(not self.optional_var.get())
        self._restore_state_style()
        self._on_change()

    def _restore_state_style(self) -> None:
        if self.optional_var.get():
            self.state_button.configure(
                text="Optional",
                fg_color=COLORS["tint"],
                hover_color="#D7EBF5",
                text_color=COLORS["primary"],
                border_width=1,
                border_color="#B8D9E9",
            )
        else:
            self.state_button.configure(
                text="Required",
                fg_color=COLORS["surface_alt"],
                hover_color=COLORS["surface_strong"],
                text_color=COLORS["navy"],
                border_width=0,
            )

    def spec(self) -> LocationSpec:
        return LocationSpec(self.name_var.get().strip(), self.optional_var.get())


class QuoterApp(ctk.CTk):
    """Single-window workbook builder with a compact native-app layout."""

    def __init__(self, screenshot_path: Path | None = None) -> None:
        super().__init__()
        self.title("ERIC's Quoter")
        self.geometry("1120x780")
        self.minsize(960, 720)
        self.configure(fg_color=COLORS["mesh_base"])
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._mode = QuoteMode.MULTI_LOCATION
        self._location_count = 2
        self._screenshot_path = screenshot_path
        self._recent_customers = load_recent_customers()
        self._resize_job: str | None = None

        self._set_window_icon()
        self._build_layout()
        self._bind_shortcuts()
        self.bind("<Configure>", self._schedule_shell_resize)
        self._set_mode(QuoteMode.MULTI_LOCATION)
        self.after(120, self.customer_entry.focus_set)
        if screenshot_path:
            self.after(1200, self._capture_screenshot)

    def _set_window_icon(self) -> None:
        image = Image.open(resource_root() / "GDI-ICON.jpg").resize((64, 64))
        self._window_icon = ImageTk.PhotoImage(image)
        self.iconphoto(True, self._window_icon)

    def _build_layout(self) -> None:
        background = MeshBackground(self)
        background.grid(row=0, column=0, sticky="nsew")

        self.shell = ctk.CTkFrame(
            self,
            width=1020,
            height=708,
            corner_radius=34,
            fg_color=COLORS["surface"],
            border_width=1,
            border_color="#C8D8E1",
            bg_color=COLORS["mesh_base"],
        )
        self.shell.place(relx=0.5, rely=0.5, anchor="center")
        self.shell.grid_propagate(False)
        self.shell.grid_columnconfigure(0, weight=1)
        self.shell.grid_rowconfigure(4, weight=1)

        self._build_header()
        self._build_mode_control()
        self._build_customer_fields()
        self._build_dynamic_section()
        self._build_output_control()
        self._build_footer()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.shell, fg_color="transparent", height=92)
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(24, 8))
        header.grid_columnconfigure(1, weight=1)

        logo = Image.open(resource_root() / "gdi-ainsworth-logo.png").convert("RGBA")
        self._header_logo = ctk.CTkImage(
            light_image=logo,
            dark_image=logo,
            size=(252, 36),
        )
        ctk.CTkLabel(header, text="", image=self._header_logo).grid(
            row=0,
            column=0,
            rowspan=2,
            sticky="w",
            padx=(0, 26),
        )

        ctk.CTkLabel(
            header,
            text="Quote Builder",
            anchor="w",
            text_color=COLORS["text"],
            font=ctk.CTkFont("Segoe UI", 23, weight="bold"),
        ).grid(row=0, column=1, sticky="sw")
        self.header_subtitle = ctk.CTkLabel(
            header,
            text="Build a multi-location costing workbook.",
            anchor="w",
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 11),
        )
        self.header_subtitle.grid(row=1, column=1, sticky="nw", pady=(2, 0))

        self.ready_badge = ctk.CTkLabel(
            header,
            text="Ready",
            width=72,
            height=34,
            corner_radius=17,
            fg_color="#EAF6F0",
            text_color=COLORS["success"],
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
        )
        self.ready_badge.grid(row=0, column=2, rowspan=2, sticky="e")

    def _build_mode_control(self) -> None:
        track = ctk.CTkFrame(
            self.shell,
            height=52,
            corner_radius=26,
            fg_color=COLORS["surface_alt"],
        )
        track.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 14))
        track.grid_propagate(False)
        track.grid_columnconfigure((0, 1), weight=1)

        self.multi_location_button = self._mode_button(
            track,
            "Multi-location",
            QuoteMode.MULTI_LOCATION,
            0,
        )
        self.multi_year_button = self._mode_button(
            track,
            "Multi-year contract",
            QuoteMode.MULTI_YEAR,
            1,
        )
        _enable_keyboard_button(self.multi_location_button, self._restore_mode_style)
        _enable_keyboard_button(self.multi_year_button, self._restore_mode_style)

    def _mode_button(self, master, text: str, mode: QuoteMode, column: int):
        button = ctk.CTkButton(
            master,
            text=text,
            height=42,
            corner_radius=21,
            bg_color=COLORS["surface_alt"],
            fg_color="transparent",
            hover_color=COLORS["surface_strong"],
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
            command=lambda: self._set_mode(mode),
        )
        button.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(5, 3) if column == 0 else (3, 5),
            pady=5,
        )
        return button

    def _build_customer_fields(self) -> None:
        details = ctk.CTkFrame(self.shell, fg_color="transparent")
        details.grid(row=2, column=0, sticky="ew", padx=30, pady=(0, 10))
        details.grid_columnconfigure((0, 1), weight=1, uniform="detail_fields")

        self.customer_var = tk.StringVar()
        self.project_var = tk.StringVar()
        self._field_label(details, "Customer name *", 0)
        self._field_label(details, "Project / scope", 1)

        self.customer_pill = ctk.CTkFrame(
            details,
            height=46,
            corner_radius=23,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_alt"],
        )
        self.customer_pill.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 7),
            pady=(5, 0),
        )
        self.customer_pill.grid_propagate(False)
        self.customer_pill.grid_columnconfigure(0, weight=1)

        self.customer_entry = ctk.CTkEntry(
            self.customer_pill,
            textvariable=self.customer_var,
            height=38,
            corner_radius=19,
            border_width=0,
            fg_color="transparent",
            text_color=COLORS["text"],
            font=ctk.CTkFont("Segoe UI", 12),
        )
        self.customer_entry.grid(row=0, column=0, sticky="ew", padx=(13, 4), pady=4)
        self.customer_entry.bind("<FocusOut>", self._validate_customer_inline)
        self.customer_entry.bind("<Alt-Down>", self._show_customer_history)

        self.customer_history_button = ctk.CTkButton(
            self.customer_pill,
            text="Recent",
            width=72,
            height=34,
            corner_radius=17,
            fg_color=COLORS["surface_strong"],
            hover_color="#D6E2E8",
            text_color=COLORS["navy"],
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
            command=self._show_customer_history,
            state="normal" if self._recent_customers else "disabled",
        )
        self.customer_history_button.grid(row=0, column=1, padx=(4, 6), pady=6)
        _enable_keyboard_button(self.customer_history_button)
        if not self._recent_customers:
            self.customer_history_button._canvas.configure(takefocus=0)  # noqa: SLF001

        self.project_entry = ctk.CTkEntry(
            details,
            textvariable=self.project_var,
            placeholder_text="Optional project description",
            height=46,
            corner_radius=23,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_alt"],
            text_color=COLORS["text"],
            font=ctk.CTkFont("Segoe UI", 12),
        )
        self.project_entry.grid(row=1, column=1, sticky="ew", padx=(7, 0), pady=(5, 0))

        self.customer_error = ctk.CTkLabel(
            details,
            text="",
            height=16,
            anchor="w",
            text_color=COLORS["error"],
            font=ctk.CTkFont("Segoe UI", 9),
        )
        self.customer_error.grid(row=2, column=0, sticky="ew", padx=(12, 7), pady=(1, 0))

        self.customer_var.trace_add("write", lambda *_: self._update_preview())
        self.project_var.trace_add("write", lambda *_: self._update_preview())

    def _field_label(self, master, text: str, column: int) -> None:
        ctk.CTkLabel(
            master,
            text=text,
            anchor="w",
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
        ).grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(12, 7) if column == 0 else (19, 12),
        )

    def _build_dynamic_section(self) -> None:
        self.dynamic_host = ctk.CTkFrame(self.shell, fg_color="transparent")
        self.dynamic_host.grid(row=4, column=0, sticky="nsew", padx=30, pady=(0, 10))
        self.dynamic_host.grid_rowconfigure(0, weight=1)
        self.dynamic_host.grid_columnconfigure(0, weight=1)

        self.locations_panel = ctk.CTkFrame(self.dynamic_host, fg_color="transparent")
        self.locations_panel.grid(row=0, column=0, sticky="nsew")
        self.locations_panel.grid_rowconfigure(1, weight=1)
        self.locations_panel.grid_columnconfigure(0, weight=1)

        locations_header = ctk.CTkFrame(self.locations_panel, fg_color="transparent")
        locations_header.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        locations_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            locations_header,
            text="Locations",
            text_color=COLORS["text"],
            font=ctk.CTkFont("Segoe UI", 14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=(10, 12))
        ctk.CTkLabel(
            locations_header,
            text="Tap a status pill to mark a location optional.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 10),
        ).grid(row=0, column=1, sticky="w")

        stepper = ctk.CTkFrame(
            locations_header,
            height=42,
            corner_radius=21,
            fg_color=COLORS["surface_alt"],
        )
        stepper.grid(row=0, column=2, sticky="e")
        self.minus_button = self._step_button(stepper, "−", -1, 0)
        self.location_count_label = ctk.CTkLabel(
            stepper,
            text="2",
            width=42,
            text_color=COLORS["text"],
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
        )
        self.location_count_label.grid(row=0, column=1, pady=4)
        self.plus_button = self._step_button(stepper, "+", 1, 2)

        self.location_list = ctk.CTkScrollableFrame(
            self.locations_panel,
            corner_radius=24,
            fg_color=COLORS["surface_alt"],
            scrollbar_button_color="#BED0DB",
            scrollbar_button_hover_color="#A8C0CD",
        )
        self.location_list.grid(row=1, column=0, sticky="nsew")
        self.location_list.grid_columnconfigure(0, weight=1)
        self.location_rows = [
            LocationPill(self.location_list, index, self._update_preview)
            for index in range(1, MAX_LOCATIONS + 1)
        ]
        for index, row in enumerate(self.location_rows):
            row.grid(row=index, column=0, sticky="ew", padx=7, pady=4)

        self.year_panel = ctk.CTkFrame(
            self.dynamic_host,
            corner_radius=26,
            fg_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
        )
        self.year_panel.grid_columnconfigure((0, 1, 2), weight=1)
        self._year_stat(self.year_panel, "5", "contract years", 0)
        self._year_stat(self.year_panel, "1", "combined total", 1)
        self._year_stat(self.year_panel, "A–V", "complete print range", 2)
        ctk.CTkLabel(
            self.year_panel,
            text="The workbook opens directly on Multi Year Contract Pricing."
            " Years 1–5 and the contract total fit on one landscape page.",
            justify="center",
            wraplength=690,
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 11),
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=28, pady=(8, 24))

    def _step_button(self, master, text: str, delta: int, column: int):
        button = ctk.CTkButton(
            master,
            text=text,
            width=36,
            height=36,
            corner_radius=0,
            bg_color=COLORS["surface_alt"],
            fg_color="transparent",
            hover_color=COLORS["surface_strong"],
            text_color=COLORS["primary"],
            font=ctk.CTkFont("Segoe UI", 16, weight="bold"),
            command=lambda: self._change_location_count(delta),
        )
        button.grid(row=0, column=column, padx=3, pady=3)
        _enable_keyboard_button(button)
        return button

    def _year_stat(self, master, value: str, label: str, column: int) -> None:
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=0, column=column, sticky="nsew", padx=12, pady=(22, 4))
        ctk.CTkLabel(
            frame,
            text=value,
            text_color=COLORS["primary"],
            font=ctk.CTkFont("Segoe UI", 24, weight="bold"),
        ).pack()
        ctk.CTkLabel(
            frame,
            text=label,
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 10),
        ).pack(pady=(0, 4))

    def _build_output_control(self) -> None:
        output = ctk.CTkFrame(self.shell, fg_color="transparent")
        output.grid(row=5, column=0, sticky="ew", padx=30, pady=(0, 10))
        output.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            output,
            text="Save folder",
            anchor="w",
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 4))

        default_output = Path.home() / "Documents" / "GDI Quotes"
        self.output_var = tk.StringVar(value=str(default_output))
        output_pill = ctk.CTkFrame(
            output,
            height=48,
            corner_radius=24,
            fg_color=COLORS["surface_alt"],
            border_width=1,
            border_color=COLORS["border"],
        )
        output_pill.grid(row=1, column=0, columnspan=2, sticky="ew")
        output_pill.grid_propagate(False)
        output_pill.grid_columnconfigure(0, weight=1)
        self.output_entry = ctk.CTkEntry(
            output_pill,
            textvariable=self.output_var,
            height=38,
            corner_radius=19,
            border_width=0,
            fg_color="transparent",
            text_color=COLORS["text"],
            font=ctk.CTkFont("Segoe UI", 11),
        )
        self.output_entry.grid(row=0, column=0, sticky="ew", padx=(13, 4), pady=5)
        self.browse_button = ctk.CTkButton(
            output_pill,
            text="Change",
            width=88,
            height=36,
            corner_radius=18,
            fg_color=COLORS["surface_strong"],
            hover_color="#D6E2E8",
            text_color=COLORS["navy"],
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
            command=self._choose_output_directory,
        )
        self.browse_button.grid(row=0, column=1, padx=(4, 6), pady=6)
        _enable_keyboard_button(self.browse_button)
        self.output_var.trace_add("write", lambda *_: self._update_preview())

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self.shell, fg_color="transparent", height=60)
        footer.grid(row=6, column=0, sticky="ew", padx=30, pady=(0, 24))
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)

        self.preview_label = ctk.CTkLabel(
            footer,
            text="",
            anchor="w",
            text_color=COLORS["muted"],
            font=ctk.CTkFont("Segoe UI", 9),
        )
        self.preview_label.grid(row=0, column=0, sticky="sw", padx=(10, 16))
        self.status_label = ctk.CTkLabel(
            footer,
            text="",
            anchor="w",
            text_color=COLORS["error"],
            font=ctk.CTkFont("Segoe UI", 9),
        )
        self.status_label.grid(row=1, column=0, sticky="nw", padx=(10, 16))

        self.create_button = ctk.CTkButton(
            footer,
            text="Create & open workbook",
            width=244,
            height=50,
            corner_radius=25,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="white",
            font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
            command=self._create_workbook,
        )
        self.create_button.grid(row=0, column=1, rowspan=2, sticky="e")
        _enable_keyboard_button(self.create_button)
        self._show_location_rows()
        self._update_preview()

    def _set_mode(self, mode: QuoteMode) -> None:
        self._mode = mode
        self._restore_mode_style()
        if mode is QuoteMode.MULTI_LOCATION:
            self.year_panel.grid_remove()
            self.locations_panel.grid(row=0, column=0, sticky="nsew")
            self.header_subtitle.configure(
                text="Build a multi-location costing workbook."
            )
        else:
            self.locations_panel.grid_remove()
            self.year_panel.grid(row=0, column=0, sticky="nsew")
            self.header_subtitle.configure(
                text="Build a complete five-year contract workbook."
            )
        self._update_preview()

    def _restore_mode_style(self) -> None:
        selected = {
            "fg_color": COLORS["surface"],
            "hover_color": "#F8FBFC",
            "text_color": COLORS["primary"],
            "border_width": 1,
            "border_color": COLORS["border"],
        }
        unselected = {
            "fg_color": "transparent",
            "hover_color": COLORS["surface_strong"],
            "text_color": COLORS["muted"],
            "border_width": 0,
        }
        self.multi_location_button.configure(
            **(selected if self._mode is QuoteMode.MULTI_LOCATION else unselected)
        )
        self.multi_year_button.configure(
            **(selected if self._mode is QuoteMode.MULTI_YEAR else unselected)
        )

    def _change_location_count(self, delta: int) -> None:
        self._location_count = max(1, min(MAX_LOCATIONS, self._location_count + delta))
        self._show_location_rows()
        self._update_preview()

    def _show_location_rows(self) -> None:
        for index, row in enumerate(self.location_rows):
            if index < self._location_count:
                row.grid()
            else:
                row.grid_remove()
        self.location_count_label.configure(text=str(self._location_count))
        self.minus_button.configure(state="disabled" if self._location_count == 1 else "normal")
        self.plus_button.configure(
            state="disabled" if self._location_count == MAX_LOCATIONS else "normal"
        )

    def _validate_customer_inline(self, _event=None) -> bool:
        valid = bool(self.customer_var.get().strip())
        self.customer_error.configure(text="" if valid else "Enter a customer name.")
        self.customer_pill.configure(
            border_color=COLORS["border"] if valid else COLORS["error"]
        )
        return valid

    def _show_customer_history(self, _event=None) -> str:
        if not self._recent_customers:
            return "break"

        menu = tk.Menu(
            self,
            tearoff=False,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            activebackground=COLORS["tint"],
            activeforeground=COLORS["primary"],
            bd=1,
            relief="solid",
            font=("Segoe UI", 10),
        )
        for customer in self._recent_customers:
            menu.add_command(
                label=customer,
                command=lambda value=customer: self._select_customer(value),
            )
        x = self.customer_pill.winfo_rootx()
        y = self.customer_pill.winfo_rooty() + self.customer_pill.winfo_height() + 4
        menu.tk_popup(x, y)
        return "break"

    def _select_customer(self, customer: str) -> None:
        self.customer_var.set(customer)
        self.customer_entry.focus_set()
        self._validate_customer_inline()

    def _choose_output_directory(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose where to save quote workbooks",
            initialdir=self.output_var.get() or str(Path.home()),
            mustexist=False,
        )
        if selected:
            self.output_var.set(selected)

    def _current_locations(self) -> tuple[LocationSpec, ...]:
        return tuple(row.spec() for row in self.location_rows[: self._location_count])

    def _request(self) -> QuoteRequest:
        return QuoteRequest(
            mode=self._mode,
            customer_name=self.customer_var.get(),
            project_scope=self.project_var.get(),
            locations=self._current_locations() if self._mode is QuoteMode.MULTI_LOCATION else (),
            output_directory=Path(self.output_var.get().strip()),
        )

    def _create_workbook(self) -> None:
        self.status_label.configure(text="", text_color=COLORS["error"])
        if not self._validate_customer_inline():
            self.status_label.configure(text="Fix the customer field, then try again.")
            self.customer_entry.focus_set()
            return
        if not self.output_var.get().strip():
            self.status_label.configure(text="Choose a folder for the generated workbook.")
            self.output_entry.focus_set()
            return
        if self._mode is QuoteMode.MULTI_LOCATION:
            for row in self.location_rows[: self._location_count]:
                if not row.name_var.get().strip():
                    self.status_label.configure(
                        text=f"Enter a name for location {row.index}."
                    )
                    row.name_entry.focus_set()
                    return

        self.create_button.configure(state="disabled", text="Creating workbook…")
        self.ready_badge.configure(
            text="Working",
            fg_color=COLORS["tint"],
            text_color=COLORS["primary"],
        )
        self.status_label.configure(
            text="Building a fresh copy of the selected template…",
            text_color=COLORS["muted"],
        )
        self.after(50, self._finish_create)

    def _finish_create(self) -> None:
        try:
            destination = generate_quote(self._request())
        except WorkbookGenerationError as exc:
            self.status_label.configure(text=str(exc), text_color=COLORS["error"])
            self.ready_badge.configure(
                text="Needs input",
                width=92,
                fg_color="#FDECEC",
                text_color=COLORS["error"],
            )
        except OSError as exc:
            self.status_label.configure(
                text=f"Windows could not create the file: {exc}",
                text_color=COLORS["error"],
            )
        else:
            remember_customer(self.customer_var.get())
            self._recent_customers = load_recent_customers()
            self.customer_history_button.configure(state="normal")
            self.customer_history_button._canvas.configure(takefocus=1)  # noqa: SLF001
            self.status_label.configure(
                text=f"Saved: {destination.name}",
                text_color=COLORS["success"],
            )
            self.ready_badge.configure(
                text="Created",
                width=78,
                fg_color="#EAF6F0",
                text_color=COLORS["success"],
            )
            try:
                os.startfile(destination)  # type: ignore[attr-defined]
            except OSError:
                self.status_label.configure(
                    text=f"Saved to {destination}. Open it from that folder.",
                    text_color=COLORS["success"],
                )
        finally:
            self.create_button.configure(state="normal", text="Create & open workbook")

    def _update_preview(self) -> None:
        if not hasattr(self, "preview_label"):
            return
        customer = self.customer_var.get().strip() or "Customer"
        project = self.project_var.get().strip()
        mode = "Multi Location" if self._mode is QuoteMode.MULTI_LOCATION else "Multi Year"
        project_text = f" - {project}" if project else ""
        self.preview_label.configure(
            text=f"{customer}{project_text} - {mode}.xlsx"
        )

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-Return>", lambda _event: self._create_workbook())
        self.bind_all(
            "<Alt-KeyPress-1>",
            lambda _event: self._set_mode(QuoteMode.MULTI_LOCATION),
        )
        self.bind_all(
            "<Alt-KeyPress-2>",
            lambda _event: self._set_mode(QuoteMode.MULTI_YEAR),
        )

    def _schedule_shell_resize(self, event) -> None:
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(30, self._resize_shell)

    def _resize_shell(self) -> None:
        self._resize_job = None
        width = min(max(self.winfo_width() - 70, 880), 1040)
        height = min(max(self.winfo_height() - 62, 656), 718)
        self.shell.configure(width=width, height=height)

    def _capture_screenshot(self) -> None:
        if not self._screenshot_path:
            return
        self.update_idletasks()
        self.lift()
        self.attributes("-topmost", True)
        self.update()
        x = self.winfo_rootx()
        y = self.winfo_rooty()
        width = self.winfo_width()
        height = self.winfo_height()
        screenshot = ImageGrab.grab(
            bbox=(x, y, x + width, y + height),
            all_screens=True,
        )
        self._screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot.save(self._screenshot_path)
        self.after(100, self.destroy)
