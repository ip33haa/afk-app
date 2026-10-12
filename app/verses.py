"""Short public-domain Bible verses for the lock screen."""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.anime import random_anime_line


@dataclass(frozen=True)
class Verse:
    text: str
    reference: str


VERSES = (
    Verse("The Lord is my shepherd; I shall not want.", "Psalm 23:1"),
    Verse("The Lord is my light and my salvation; whom shall I fear?", "Psalm 27:1"),
    Verse("Be still, and know that I am God.", "Psalm 46:10"),
    Verse("God is our refuge and strength, a very present help in trouble.", "Psalm 46:1"),
    Verse("Create in me a clean heart, O God.", "Psalm 51:10"),
    Verse("O taste and see that the Lord is good.", "Psalm 34:8"),
    Verse("This is the day which the Lord hath made; we will rejoice and be glad in it.", "Psalm 118:24"),
    Verse("Thy word is a lamp unto my feet, and a light unto my path.", "Psalm 119:105"),
    Verse("I will lift up mine eyes unto the hills, from whence cometh my help.", "Psalm 121:1"),
    Verse("The Lord shall preserve thy going out and thy coming in.", "Psalm 121:8"),
    Verse("Trust in the Lord with all thine heart.", "Proverbs 3:5"),
    Verse("In all thy ways acknowledge him, and he shall direct thy paths.", "Proverbs 3:6"),
    Verse("A merry heart doeth good like a medicine.", "Proverbs 17:22"),
    Verse("The name of the Lord is a strong tower.", "Proverbs 18:10"),
    Verse("But they that wait upon the Lord shall renew their strength.", "Isaiah 40:31"),
    Verse("Fear thou not; for I am with thee.", "Isaiah 41:10"),
    Verse("When thou passest through the waters, I will be with thee.", "Isaiah 43:2"),
    Verse("The Lord is good, a strong hold in the day of trouble.", "Nahum 1:7"),
    Verse("Come unto me, all ye that labour and are heavy laden, and I will give you rest.", "Matthew 11:28"),
    Verse("Let your light so shine before men.", "Matthew 5:16"),
    Verse("With God all things are possible.", "Matthew 19:26"),
    Verse("Lo, I am with you alway, even unto the end of the world.", "Matthew 28:20"),
    Verse("Peace I leave with you, my peace I give unto you.", "John 14:27"),
    Verse("I am the way, the truth, and the life.", "John 14:6"),
    Verse("And ye shall know the truth, and the truth shall make you free.", "John 8:32"),
    Verse("For God so loved the world, that he gave his only begotten Son.", "John 3:16"),
    Verse("We love him, because he first loved us.", "1 John 4:19"),
    Verse("God is love.", "1 John 4:8"),
    Verse("The joy of the Lord is your strength.", "Nehemiah 8:10"),
    Verse("I can do all things through Christ which strengtheneth me.", "Philippians 4:13"),
    Verse("Be careful for nothing; but in every thing by prayer and supplication with thanksgiving let your requests be made known unto God.", "Philippians 4:6"),
    Verse("And the peace of God, which passeth all understanding, shall keep your hearts and minds.", "Philippians 4:7"),
    Verse("Rejoice in the Lord alway: and again I say, Rejoice.", "Philippians 4:4"),
    Verse("Faith is the substance of things hoped for, the evidence of things not seen.", "Hebrews 11:1"),
    Verse("Jesus Christ the same yesterday, and to day, and for ever.", "Hebrews 13:8"),
    Verse("The Lord bless thee, and keep thee.", "Numbers 6:24"),
    Verse("The Lord make his face shine upon thee, and be gracious unto thee.", "Numbers 6:25"),
)


def random_verse() -> str:
    verse = random.choice(VERSES)
    return f"“{verse.text}”\n\n{verse.reference}"


def lock_screen_text(*, show_verse: bool, require_blink: bool) -> str:
    del require_blink
    if show_verse:
        return random_verse()
    return random_anime_line()
