"""Short famous anime lines for the lock screen caption."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class AnimeLine:
    text: str
    speaker: str


LINES = (
    AnimeLine("Believe it!", "Naruto Uzumaki"),
    AnimeLine("I never go back on my word. That's my ninja way.", "Naruto Uzumaki"),
    AnimeLine("If you don't like your destiny, don't accept it.", "Naruto Uzumaki"),
    AnimeLine("I'm gonna be King of the Pirates!", "Monkey D. Luffy"),
    AnimeLine("A man's dream will never die!", "Marshall D. Teach"),
    AnimeLine("I am the hope of the universe.", "Son Goku"),
    AnimeLine("Power comes in response to a need, not a desire.", "Son Goku"),
    AnimeLine("It's over 9,000!", "Vegeta"),
    AnimeLine("Plus Ultra!", "All Might"),
    AnimeLine("Meddling where you don't belong is the essence of being a hero.", "All Might"),
    AnimeLine("I mustn't run away.", "Shinji Ikari"),
    AnimeLine("Just who the hell do you think I am?", "Kamina"),
    AnimeLine("Believe in the you that believes in yourself.", "Kamina"),
    AnimeLine("Yare yare daze.", "Jotaro Kujo"),
    AnimeLine("I reject my humanity, JoJo!", "Dio Brando"),
    AnimeLine("Omae wa mou shindeiru.", "Kenshiro"),
    AnimeLine("A lesson without pain is meaningless.", "Edward Elric"),
    AnimeLine("Stand up and walk. Keep moving forward.", "Edward Elric"),
    AnimeLine("Nothing happened.", "Roy Mustang"),
    AnimeLine("I'll take a potato chip and eat it.", "Light Yagami"),
    AnimeLine("El Psy Kongroo.", "Rintaro Okabe"),
    AnimeLine("This is the choice of Steins Gate.", "Rintaro Okabe"),
    AnimeLine("The world is not beautiful, therefore it is.", "Kino"),
    AnimeLine("You should enjoy the little detours.", "Ging Freecss"),
    AnimeLine("People die when they are killed.", "Shirou Emiya"),
    AnimeLine("Tatakae.", "Eren Yeager"),
    AnimeLine("Dedicate your heart.", "Erwin Smith"),
    AnimeLine("Bankai.", "Ichigo Kurosaki"),
    AnimeLine("I want to be a hero who saves everyone.", "Izuku Midoriya"),
    AnimeLine("I'm not gonna run away, I never go back on my word.", "Naruto Uzumaki"),
)


def random_anime_line() -> str:
    line = random.choice(LINES)
    return f"“{line.text}”\n\n{line.speaker}"
