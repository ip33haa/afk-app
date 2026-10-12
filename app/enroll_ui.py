"""Enrollment and settings window."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageTk

from app.paths import credential_provider_registered
from app.secure_store import SecureStore, current_account_label
from app.startup import set_start_with_windows


class SettingsWindow:
    def __init__(self, root, camera, face, config, on_saved) -> None:
        self._camera = camera
        self._face = face
        self._config = config
        self._on_saved = on_saved
        self._store = SecureStore()
        self._photo = None
        self._samples: list = []
        self._capture_tries = 0
        self._after = None
        self._closed = False

        self.window = tk.Toplevel(root)
        self.window.title("Set up face and PIN")
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.attributes("-topmost", True)
        self.window.after(800, lambda: self.window.attributes("-topmost", False))

        frame = ttk.Frame(self.window, padding=12)
        frame.grid(row=0, column=0)

        self.video = ttk.Label(frame)
        self.video.grid(row=0, column=0, columnspan=2, pady=(0, 8))

        self.sample_label = ttk.Label(frame, text=self._sample_text())
        self.sample_label.grid(row=1, column=0, sticky="w")
        ttk.Button(frame, text="Record face", command=self._start_capture).grid(row=1, column=1, sticky="e")

        ttk.Label(frame, text="Windows account").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(frame, text=current_account_label()).grid(row=2, column=1, sticky="w", pady=(10, 0))

        ttk.Label(frame, text="PIN").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._password = tk.StringVar()
        self._password_entry = ttk.Entry(frame, textvariable=self._password, show="*", width=28)
        self._password_entry.grid(row=3, column=1, sticky="ew", pady=(6, 0))
        hint = (
            "Leave blank to keep the saved PIN."
            if self._store.has_secret()
            else "Enter the PIN you type at the lock screen. If Windows rejects it, use your account password."
        )
        ttk.Label(frame, text=hint, wraplength=460).grid(row=4, column=0, columnspan=2, sticky="w")

        self._show = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Show password", variable=self._show, command=self._toggle_show).grid(
            row=5, column=0, columnspan=2, sticky="w"
        )

        ttk.Label(frame, text="Lock after you leave (seconds)").grid(row=6, column=0, sticky="w", pady=(8, 0))
        self._grace = tk.Spinbox(frame, from_=3, to=120, width=8)
        self._grace.delete(0, "end")
        self._grace.insert(0, str(int(config.grace_seconds)))
        self._grace.grid(row=6, column=1, sticky="w", pady=(8, 0))

        self._blink = tk.BooleanVar(value=config.require_blink)
        ttk.Checkbutton(frame, text="Require a blink to unlock", variable=self._blink).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        self._startup = tk.BooleanVar(value=config.start_with_windows)
        ttk.Checkbutton(frame, text="Start when I sign in", variable=self._startup).grid(
            row=8, column=0, columnspan=2, sticky="w"
        )

        self._verse = tk.BooleanVar(value=config.show_verse)
        ttk.Checkbutton(frame, text="Show a Bible verse under the clock", variable=self._verse).grid(
            row=9, column=0, columnspan=2, sticky="w"
        )

        provider = (
            "Looking at the camera unlocks the Windows lock screen."
            if credential_provider_registered()
            else "Looking at the camera unlocks AFK's lock screen. Your wallpaper, the clock, and an anime line stay up until it sees you."
        )
        ttk.Label(frame, text=provider, wraplength=460).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))

        warning = (
            "Your PIN is encrypted for this Windows account only. Any program you run can decrypt it. "
            "A normal webcam can be fooled more easily than Windows Hello, including by a photo. "
            "A cold start still asks you to sign in."
        )
        ttk.Label(frame, text=warning, wraplength=460).grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=12, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Save and start", command=self._save).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Close", command=self.close).grid(row=0, column=1)

        self._preview()
        self.window.update_idletasks()
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._password.set("")
        if self._after is not None:
            try:
                self.window.after_cancel(self._after)
            except tk.TclError:
                pass
        self.window.destroy()

    def _sample_text(self) -> str:
        if self._face.has_enrollment() and not self._samples:
            return "A face is already saved. Record again to replace it."
        return f"Samples: {len(self._samples)} / 8"

    def _toggle_show(self) -> None:
        self._password_entry.configure(show="" if self._show.get() else "*")

    def _preview(self) -> None:
        if self._closed:
            return
        frame = self._camera.latest()
        if frame is not None:
            box = self._face.largest_box(frame)
            if box is not None:
                x, y, w, h = box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (40, 180, 80), 2)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb).resize((480, 360))
            self._photo = ImageTk.PhotoImage(image)
            self.video.configure(image=self._photo)
        self._after = self.window.after(200, self._preview)

    def _start_capture(self) -> None:
        self._samples = []
        self._capture_tries = 0
        self.sample_label.configure(text="Look at the camera and turn your head slightly.")
        self._capture_step()

    def _capture_step(self) -> None:
        if self._closed:
            return
        frame = self._camera.latest()
        if frame is not None:
            embedding = self._face.embed(frame)
            if embedding is not None:
                self._samples.append(embedding)
        self.sample_label.configure(text=f"Samples: {len(self._samples)} / 8")
        if len(self._samples) >= 8:
            try:
                self._face.save_enrollment(self._samples)
            except ValueError as exc:
                messagebox.showerror("AFK", str(exc), parent=self.window)
                return
            self.sample_label.configure(text="Face saved")
            return
        self._capture_tries += 1
        if self._capture_tries >= 50:
            messagebox.showerror(
                "AFK",
                "Could not see your face clearly. Face the camera in better light and try again.",
                parent=self.window,
            )
            return
        self.window.after(200, self._capture_step)

    def _save(self) -> None:
        password = self._password.get()
        try:
            grace = float(self._grace.get())
        except ValueError:
            messagebox.showerror("AFK", "Enter a number of seconds.", parent=self.window)
            return
        if grace < 3 or grace > 120:
            messagebox.showerror("AFK", "Choose a lock delay between 3 and 120 seconds.", parent=self.window)
            return
        try:
            if password:
                self._store.save(password)
            elif not self._store.has_secret():
                raise ValueError("Enter your PIN. If Windows Hello rejects it, enter your account password.")
            if not self._face.has_enrollment():
                raise ValueError("Record your face first.")
        except ValueError as exc:
            messagebox.showerror("AFK", str(exc), parent=self.window)
            return
        finally:
            self._password.set("")
        self._config.grace_seconds = grace
        self._config.require_blink = bool(self._blink.get())
        self._config.start_with_windows = bool(self._startup.get())
        self._config.show_verse = bool(self._verse.get())
        self._config.monitoring = True
        self._config.save()
        set_start_with_windows(self._config.start_with_windows)
        self._on_saved()
        self.close()
