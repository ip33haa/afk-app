"""Lock when the enrolled face leaves. Unlock only after it comes back."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TickResult:
    action: str | None = None
    clear_blink: bool = False
    status: str = ""


class PresenceEngine:
    def __init__(
        self,
        grace_seconds: float = 8.0,
        match_hold_seconds: float = 1.0,
        cooldown_seconds: float = 8.0,
        require_blink: bool = True,
        unlock_timeout_seconds: float = 12.0,
        match_gap_seconds: float = 0.4,
    ) -> None:
        self.grace_seconds = grace_seconds
        self.match_hold_seconds = match_hold_seconds
        self.cooldown_seconds = cooldown_seconds
        self.require_blink = require_blink
        self.unlock_timeout_seconds = unlock_timeout_seconds
        self.match_gap_seconds = match_gap_seconds
        self.state = "idle"
        self._absent_since: float | None = None
        self._match_since: float | None = None
        self._last_match_at: float | None = None
        self._cooldown_until: float | None = None
        self._unlock_started: float | None = None
        self._lock_requested_at: float | None = None
        self._submitted = False
        self._wait_until_face_lost = False
        self._next_unlock_try = 0.0
        self._unavailable_tries = 0

    def update(
        self,
        *,
        enrolled_face_present: bool,
        blinked: bool,
        session_locked: bool,
        now: float,
    ) -> TickResult:
        action: str | None = None
        clear_blink = False

        if self.state == "idle":
            if session_locked:
                clear_blink = self._enter_watching()
            elif enrolled_face_present:
                self._enter_armed()

        elif self.state == "armed":
            if session_locked:
                clear_blink = self._enter_watching()
            elif enrolled_face_present:
                self._absent_since = None
            else:
                if self._absent_since is None:
                    self._absent_since = now
                elif now - self._absent_since >= self.grace_seconds:
                    self.state = "locking"
                    self._lock_requested_at = now
                    action = "lock"

        elif self.state == "locking":
            if session_locked:
                clear_blink = self._enter_watching()
            elif enrolled_face_present:
                self._enter_armed()
            elif (
                self._lock_requested_at is not None
                and now - self._lock_requested_at >= 2.0
            ):
                self._lock_requested_at = now
                action = "lock"

        elif self.state == "watching_locked":
            if not session_locked:
                self._enter_cooldown(now)
                clear_blink = True
            else:
                if self._track_match(enrolled_face_present, now):
                    clear_blink = True
                face_held = self._match_since is not None
                if self._wait_until_face_lost:
                    if not face_held and self._last_match_at is None:
                        self._wait_until_face_lost = False
                else:
                    stable = (
                        self._match_since is not None
                        and now - self._match_since >= self.match_hold_seconds
                    )
                    blink_ok = blinked or not self.require_blink
                    if (
                        stable
                        and blink_ok
                        and now >= self._next_unlock_try
                        and not self._submitted
                    ):
                        self.state = "unlocking"
                        self._unlock_started = now
                        action = "unlock"

        elif self.state == "unlocking":
            if not session_locked:
                self._enter_cooldown(now)
                clear_blink = True
            elif (
                self._unlock_started is not None
                and now - self._unlock_started >= self.unlock_timeout_seconds
            ):
                self.state = "watching_locked"
                self._wait_until_face_lost = self._submitted
                self._submitted = False
                self._unlock_started = None
                clear_blink = True
                if not self._wait_until_face_lost:
                    self._next_unlock_try = now + 1.0

        elif self.state == "cooldown":
            if session_locked:
                clear_blink = self._enter_watching()
            elif self._cooldown_until is not None and now >= self._cooldown_until:
                self._enter_armed()
                if not enrolled_face_present:
                    self._absent_since = now
        else:
            self.state = "idle"

        return TickResult(action=action, clear_blink=clear_blink, status=self.status_text(now))

    def note_unlock_result(self, result: str, now: float) -> None:
        if self.state != "unlocking":
            return
        if result == "accepted":
            self._submitted = True
            return
        self._unlock_started = None
        self.state = "watching_locked"
        if result == "rejected":
            self._submitted = False
            self._wait_until_face_lost = True
            return
        self._unavailable_tries += 1
        if self._unavailable_tries >= 10:
            self._wait_until_face_lost = True
            return
        self._next_unlock_try = now + 1.0

    def status_text(self, now: float) -> str:
        if self.state == "idle":
            return "Waiting until you are in view"
        if self.state == "armed":
            if self._absent_since is None:
                return "You are present"
            left = self.grace_seconds - (now - self._absent_since)
            seconds = max(0, int(left + 0.999))
            return f"You stepped away — locking in {seconds}s"
        if self.state == "locking":
            return "Locking"
        if self.state == "watching_locked":
            if self._wait_until_face_lost:
                return "Unlock did not complete — step away and look again"
            return "Locked"
        if self.state == "unlocking":
            return "Face recognized, unlocking"
        if self.state == "cooldown":
            return "Just unlocked"
        return self.state

    def _enter_armed(self) -> None:
        self.state = "armed"
        self._absent_since = None
        self._lock_requested_at = None

    def _enter_watching(self) -> bool:
        self.state = "watching_locked"
        self._match_since = None
        self._last_match_at = None
        self._submitted = False
        self._wait_until_face_lost = False
        self._unavailable_tries = 0
        self._next_unlock_try = 0.0
        self._lock_requested_at = None
        self._unlock_started = None
        return True

    def _enter_cooldown(self, now: float) -> None:
        self.state = "cooldown"
        self._cooldown_until = now + self.cooldown_seconds
        self._submitted = False
        self._wait_until_face_lost = False
        self._match_since = None
        self._last_match_at = None
        self._unlock_started = None

    def _track_match(self, present: bool, now: float) -> bool:
        """Remember a steady match. Return True when the match has been lost."""
        if present:
            self._last_match_at = now
            if self._match_since is None:
                self._match_since = now
            return False
        if (
            self._last_match_at is not None
            and now - self._last_match_at <= self.match_gap_seconds
        ):
            return False
        lost = self._match_since is not None or self._last_match_at is not None
        self._match_since = None
        self._last_match_at = None
        return lost
