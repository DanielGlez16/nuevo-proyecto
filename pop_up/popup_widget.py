#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini Pop-Up Flotante de Escritorio - Asistente de Moodle (Tema Oscuro)
Ventana nativa sin bordes, arrastrable por toda la pantalla y Always-On-Top.
"""

import argparse
import datetime
import json
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from app import load_data, save_data, open_url_in_google, launch_desktop_window, find_free_port

BASE_DIR = Path(__file__).resolve().parent

# Paleta Dark Obsidian
BG_MAIN = "#0b0f19"
BG_CARD = "#131b2e"
BG_CARD_HOVER = "#1e293b"
BG_HEADER = "#111827"
FG_PRIMARY = "#f8fafc"
FG_MUTED = "#94a3b8"
ACCENT_INDIGO = "#6366f1"
ACCENT_EMERALD = "#10b981"
ACCENT_AMBER = "#f59e0b"
ACCENT_ROSE = "#f43f5e"
BORDER_COLOR = "#1e293b"


class MoodleFloatingPopup:
    def __init__(self, root: tk.Tk, server_port: int = 8765):
        self.root = root
        self.server_port = server_port
        self.is_minimized_pill = False
        self.always_on_top = True
        self.pomo_running = False
        self.pomo_seconds = 25 * 60
        self.pomo_job = None

        self.root.title("Moodle Assistant Pop-Up")
        self.root.configure(bg=BG_MAIN)
        self.root.overrideredirect(True)  # Ventana tipo pop-up sin bordes nativos para mover libremente
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)

        # Posicionar en la esquina superior derecha de la pantalla
        screen_w = self.root.winfo_screenwidth()
        self.full_w = 370
        self.full_h = 540
        x_pos = max(20, screen_w - self.full_w - 30)
        y_pos = 40
        self.root.geometry(f"{self.full_w}x{self.full_h}+{x_pos}+{y_pos}")

        # Variables para arrastrar libremente la ventana
        self._drag_x = 0
        self._drag_y = 0

        self.outer_frame = tk.Frame(
            self.root,
            bg=BG_MAIN,
            highlightbackground="#334155",
            highlightthickness=1
        )
        self.outer_frame.pack(fill="both", expand=True)

        self._build_header()
        self._build_body()
        self.refresh_data()

    def _build_header(self):
        self.header = tk.Frame(self.outer_frame, bg=BG_HEADER, height=44, cursor="fleur")
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        # Eventos para arrastrar la ventana por el escritorio
        for widget in (self.header,):
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)

        self.dot_canvas = tk.Canvas(self.header, width=12, height=12, bg=BG_HEADER, highlightthickness=0)
        self.dot_canvas.pack(side="left", padx=(12, 6), pady=14)
        self.dot_canvas.create_oval(2, 2, 10, 10, fill=ACCENT_EMERALD, outline="")

        self.title_lbl = tk.Label(
            self.header,
            text="🎓 Moodle Pop-Up Assistant",
            bg=BG_HEADER,
            fg=FG_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            cursor="fleur"
        )
        self.title_lbl.pack(side="left", padx=2)
        self.title_lbl.bind("<ButtonPress-1>", self._start_move)
        self.title_lbl.bind("<B1-Motion>", self._on_move)

        # Botón cerrar
        btn_close = tk.Button(
            self.header,
            text="✕",
            bg=BG_HEADER,
            fg=FG_MUTED,
            activebackground=ACCENT_ROSE,
            activeforeground=FG_PRIMARY,
            bd=0,
            font=("Segoe UI", 9, "bold"),
            width=3,
            cursor="hand2",
            command=self.root.destroy
        )
        btn_close.pack(side="right", padx=(2, 6), pady=6)

        # Botón modo píldora / desplegar
        self.btn_collapse = tk.Button(
            self.header,
            text="—",
            bg=BG_HEADER,
            fg=FG_MUTED,
            activebackground=BG_CARD_HOVER,
            activeforeground=FG_PRIMARY,
            bd=0,
            font=("Segoe UI", 9, "bold"),
            width=3,
            cursor="hand2",
            command=self.toggle_pill_mode
        )
        self.btn_collapse.pack(side="right", padx=2, pady=6)

        # Botón fijar siempre encima
        self.btn_pin = tk.Button(
            self.header,
            text="📌",
            bg=BG_HEADER,
            fg=ACCENT_INDIGO,
            activebackground=BG_CARD_HOVER,
            activeforeground=FG_PRIMARY,
            bd=0,
            font=("Segoe UI", 9),
            width=3,
            cursor="hand2",
            command=self.toggle_topmost
        )
        self.btn_pin.pack(side="right", padx=2, pady=6)

    def _build_body(self):
        self.body = tk.Frame(self.outer_frame, bg=BG_MAIN)
        self.body.pack(fill="both", expand=True, padx=12, pady=10)

        # Tarjeta de Perfil Enlazado
        self.profile_frame = tk.Frame(self.body, bg=BG_CARD, padx=10, pady=8)
        self.profile_frame.pack(fill="x", pady=(0, 8))

        self.lbl_profile_name = tk.Label(
            self.profile_frame,
            text="Conectado a Moodle",
            bg=BG_CARD,
            fg=FG_PRIMARY,
            font=("Segoe UI", 9, "bold"),
            anchor="w"
        )
        self.lbl_profile_name.pack(fill="x")

        self.lbl_profile_uni = tk.Label(
            self.profile_frame,
            text="Campus Virtual",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=("Segoe UI", 8),
            anchor="w"
        )
        self.lbl_profile_uni.pack(fill="x")

        # Temporizador Pomodoro Rápido
        pomo_frame = tk.Frame(self.body, bg=BG_CARD, padx=10, pady=8)
        pomo_frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            pomo_frame,
            text="⏱️ POMODORO ESTUDIO",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=("Segoe UI", 7, "bold")
        ).pack(side="left")

        self.lbl_pomo_time = tk.Label(
            pomo_frame,
            text="25:00",
            bg=BG_CARD,
            fg=ACCENT_INDIGO,
            font=("Consolas", 13, "bold")
        )
        self.lbl_pomo_time.pack(side="left", padx=10)

        tk.Button(
            pomo_frame,
            text="↺",
            bg=BG_CARD_HOVER,
            fg=FG_PRIMARY,
            bd=0,
            font=("Segoe UI", 8, "bold"),
            width=3,
            cursor="hand2",
            command=self.reset_pomodoro
        ).pack(side="right", padx=(4, 0))

        self.btn_pomo_toggle = tk.Button(
            pomo_frame,
            text="▶ Iniciar",
            bg=ACCENT_INDIGO,
            fg=FG_PRIMARY,
            bd=0,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            cursor="hand2",
            command=self.toggle_pomodoro
        )
        self.btn_pomo_toggle.pack(side="right")

        # Sección: Próximas Tareas de Moodle (Clic lleva a Google Chrome)
        hdr_tasks = tk.Frame(self.body, bg=BG_MAIN)
        hdr_tasks.pack(fill="x", pady=(2, 4))
        tk.Label(
            hdr_tasks,
            text="📅 TAREAS MOODLE (Clic → Abrir en Google)",
            bg=BG_MAIN,
            fg=FG_MUTED,
            font=("Segoe UI", 8, "bold")
        ).pack(side="left")

        tk.Button(
            hdr_tasks,
            text="🔄",
            bg=BG_MAIN,
            fg=FG_MUTED,
            bd=0,
            cursor="hand2",
            command=self.refresh_data
        ).pack(side="right")

        self.tasks_container = tk.Frame(self.body, bg=BG_MAIN)
        self.tasks_container.pack(fill="both", expand=True)

        # Sección: Clases de Hoy
        tk.Label(
            self.body,
            text="⏰ HORARIO DE HOY",
            bg=BG_MAIN,
            fg=FG_MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor="w"
        ).pack(fill="x", pady=(6, 4))

        self.schedule_container = tk.Frame(self.body, bg=BG_MAIN)
        self.schedule_container.pack(fill="x")

        # Botón inferior para abrir el panel de escritorio completo
        bottom_bar = tk.Frame(self.body, bg=BG_MAIN)
        bottom_bar.pack(fill="x", side="bottom", pady=(10, 0))

        tk.Button(
            bottom_bar,
            text="🚀 Abrir Panel Completo del Asistente",
            bg=ACCENT_INDIGO,
            fg=FG_PRIMARY,
            activebackground="#4f46e5",
            activeforeground=FG_PRIMARY,
            bd=0,
            pady=7,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            command=self.open_full_app
        ).pack(fill="x")

    def _start_move(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_move(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_x)
        y = self.root.winfo_y() + (event.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")

    def toggle_pill_mode(self):
        self.is_minimized_pill = not self.is_minimized_pill
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        if self.is_minimized_pill:
            self.body.pack_forget()
            self.root.geometry(f"{self.full_w}x46+{x}+{y}")
            self.btn_collapse.config(text="▢")
        else:
            self.body.pack(fill="both", expand=True, padx=12, pady=10)
            self.root.geometry(f"{self.full_w}x{self.full_h}+{x}+{y}")
            self.btn_collapse.config(text="—")

    def toggle_topmost(self):
        self.always_on_top = not self.always_on_top
        self.root.attributes("-topmost", self.always_on_top)
        self.btn_pin.config(fg=ACCENT_INDIGO if self.always_on_top else FG_MUTED)

    def toggle_pomodoro(self):
        self.pomo_running = not self.pomo_running
        if self.pomo_running:
            self.btn_pomo_toggle.config(text="⏸ Pausar", bg=ACCENT_AMBER)
            self._tick_pomodoro()
        else:
            self.btn_pomo_toggle.config(text="▶ Reanudar", bg=ACCENT_INDIGO)
            if self.pomo_job:
                self.root.after_cancel(self.pomo_job)
                self.pomo_job = None

    def _tick_pomodoro(self):
        if not self.pomo_running:
            return
        if self.pomo_seconds > 0:
            self.pomo_seconds -= 1
            mins, secs = divmod(self.pomo_seconds, 60)
            self.lbl_pomo_time.config(text=f"{mins:02d}:{secs:02d}")
            self.pomo_job = self.root.after(1000, self._tick_pomodoro)
        else:
            self.pomo_running = False
            self.btn_pomo_toggle.config(text="▶ Iniciar", bg=ACCENT_INDIGO)
            self.pomo_seconds = 25 * 60
            self.lbl_pomo_time.config(text="25:00")
            data = load_data()
            stats = data.get("pomodoroStats", {"completedSessions": 0, "totalMinutes": 0})
            stats["completedSessions"] = stats.get("completedSessions", 0) + 1
            stats["totalMinutes"] = stats.get("totalMinutes", 0) + 25
            data["pomodoroStats"] = stats
            save_data(data)

    def reset_pomodoro(self):
        self.pomo_running = False
        if self.pomo_job:
            self.root.after_cancel(self.pomo_job)
            self.pomo_job = None
        self.pomo_seconds = 25 * 60
        self.lbl_pomo_time.config(text="25:00")
        self.btn_pomo_toggle.config(text="▶ Iniciar", bg=ACCENT_INDIGO)

    def refresh_data(self):
        data = load_data()
        profile = data.get("profile", {})
        is_linked = bool(profile.get("linked"))
        student = profile.get("studentName") or profile.get("username") or "Sin sesión iniciada"
        uni = profile.get("university", "Moodle Centros Sevilla")
        status_label = "Conectado" if is_linked else "Inicia sesión en el panel"
        self.lbl_profile_name.config(text=f"👤 {student} • {status_label}")
        self.lbl_profile_uni.config(text=f"🏛️ {uni} (Sinc: {profile.get('lastSync', 'Pendiente')})")

        # Limpiar contenedor de tareas
        for w in self.tasks_container.winfo_children():
            w.destroy()

        tasks = [t for t in data.get("moodleTasks", []) if t.get("status") != "completed"]
        tasks.sort(key=lambda x: (x.get("dueDate", "9999-99-99"), x.get("dueTime", "23:59")))

        if not tasks:
            msg_empty = (
                "🎉 No tienes entregas pendientes en Moodle."
                if is_linked
                else "🔐 Abre el Panel Completo e inicia sesión en tu Moodle para cargar tus tareas reales."
            )
            tk.Label(
                self.tasks_container,
                text=msg_empty,
                bg=BG_CARD,
                fg=ACCENT_EMERALD if is_linked else FG_MUTED,
                font=("Segoe UI", 8),
                wraplength=320,
                justify="left",
                padx=8,
                pady=10
            ).pack(fill="x")
        else:
            for t in tasks[:4]:
                card = tk.Frame(self.tasks_container, bg=BG_CARD, padx=8, pady=6, cursor="hand2")
                card.pack(fill="x", pady=3)

                bar = tk.Frame(card, bg=t.get("color", ACCENT_INDIGO), width=4)
                bar.pack(side="left", fill="y", padx=(0, 6))

                info = tk.Frame(card, bg=BG_CARD, cursor="hand2")
                info.pack(side="left", fill="x", expand=True)

                title_txt = t.get("title", "Tarea")
                if len(title_txt) > 38:
                    title_txt = title_txt[:36] + "…"

                lbl_t = tk.Label(
                    info,
                    text=title_txt,
                    bg=BG_CARD,
                    fg=FG_PRIMARY,
                    font=("Segoe UI", 8, "bold"),
                    anchor="w",
                    cursor="hand2"
                )
                lbl_t.pack(fill="x")

                sub_txt = f"{t.get('course', 'Moodle')} • Vence: {t.get('dueDate', '')} ({t.get('dueTime', '')})"
                lbl_s = tk.Label(
                    info,
                    text=sub_txt,
                    bg=BG_CARD,
                    fg=FG_MUTED,
                    font=("Segoe UI", 7),
                    anchor="w",
                    cursor="hand2"
                )
                lbl_s.pack(fill="x")

                def make_open_handler(task_obj):
                    def _handler(_event=None):
                        query = f"Moodle {task_obj.get('course', '')} {task_obj.get('title', '')}"
                        open_url_in_google(task_obj.get("moodleUrl", ""), query, mode="direct")
                    return _handler

                handler = make_open_handler(t)
                for w in (card, info, lbl_t, lbl_s):
                    w.bind("<Button-1>", handler)

        # Limpiar y mostrar horario de hoy
        for w in self.schedule_container.winfo_children():
            w.destroy()

        weekday = datetime.date.today().weekday()  # 0=Lunes .. 6=Domingo
        todays_classes = [c for c in data.get("schedule", []) if int(c.get("day", -1)) == weekday]
        todays_classes.sort(key=lambda x: x.get("startTime", "00:00"))

        if not todays_classes:
            # Mostrar las primeras 2 clases de la semana como referencia
            all_classes = sorted(data.get("schedule", []), key=lambda x: (int(x.get("day", 0)), x.get("startTime", "00:00")))[:2]
            day_names = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
            for c in all_classes:
                d_idx = int(c.get("day", 0)) % 7
                row = tk.Frame(self.schedule_container, bg=BG_CARD, padx=8, pady=4)
                row.pack(fill="x", pady=2)
                tk.Label(
                    row,
                    text=f"{day_names[d_idx]} {c.get('startTime', '')} - {c.get('subject', '')} ({c.get('room', '')})",
                    bg=BG_CARD,
                    fg=FG_PRIMARY,
                    font=("Segoe UI", 8),
                    anchor="w"
                ).pack(fill="x")
        else:
            for c in todays_classes[:3]:
                row = tk.Frame(self.schedule_container, bg=BG_CARD, padx=8, pady=4)
                row.pack(fill="x", pady=2)
                tk.Label(
                    row,
                    text=f"{c.get('startTime', '')}-{c.get('endTime', '')} • {c.get('subject', '')} [{c.get('room', '')}]",
                    bg=BG_CARD,
                    fg=FG_PRIMARY,
                    font=("Segoe UI", 8),
                    anchor="w"
                ).pack(fill="x")

    def open_full_app(self):
        url = f"http://127.0.0.1:{self.server_port}"
        launch_desktop_window(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    root = tk.Tk()
    app = MoodleFloatingPopup(root, server_port=args.port)
    root.mainloop()


if __name__ == "__main__":
    main()

