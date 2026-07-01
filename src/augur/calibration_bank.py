"""A bundled bank of trivia for calibration practice.

Two flavours, matching the two classic calibration exercises:

* ``NUMERIC`` -- questions with a single numeric answer. Used for the
  "90% confidence interval" drill (Hubbard, *How to Measure Anything*): give a
  range you're 90% sure contains the truth; a well-calibrated person captures
  the answer in ~90% of their ranges.
* ``BINARY`` -- true/false statements. Used for the confidence drill: say
  whether it's true and how sure you are (50-100%); scored with the Brier score.

Every fact here is meant to be stable and checkable. Each item carries an
optional ``source`` note. The set is intentionally general-knowledge and
Western-biased-neutral where possible; it is a practice aid, not a pub quiz.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NumericQuestion:
    prompt: str
    answer: float
    unit: str = ""
    source: str = ""


@dataclass(frozen=True)
class BinaryQuestion:
    prompt: str
    answer: bool
    source: str = ""


NUMERIC: list[NumericQuestion] = [
    NumericQuestion("In what year was the Eiffel Tower completed?", 1889, ""),
    NumericQuestion("How long is the river Nile, to the nearest 100 km?", 6650, "km"),
    NumericQuestion("How many bones are in the adult human body?", 206, ""),
    NumericQuestion("In what year did Apollo 11 land humans on the Moon?", 1969, ""),
    NumericQuestion("How many member states does the United Nations have (2024)?", 193, ""),
    NumericQuestion("What is the height of Mount Everest above sea level?", 8849, "m"),
    NumericQuestion("What is the average distance from the Earth to the Moon?", 384400, "km"),
    NumericQuestion("How many keys are on a standard piano?", 88, ""),
    NumericQuestion("In what year did the Berlin Wall fall?", 1989, ""),
    NumericQuestion("How many chemical elements are on the periodic table (2024)?", 118, ""),
    NumericQuestion("How many players from one team are on a soccer field at kickoff?", 11, ""),
    NumericQuestion("In what year was the first iPhone released?", 2007, ""),
    NumericQuestion("What is the speed of light in a vacuum, in km/s?", 299792, "km/s"),
    NumericQuestion("How many chromosomes are in a typical human body cell?", 46, ""),
    NumericQuestion("In what year did the Titanic sink?", 1912, ""),
    NumericQuestion("What is the atomic number of oxygen?", 8, ""),
    NumericQuestion("What is the length of a marathon, to the nearest 0.1 km?", 42.2, "km"),
    NumericQuestion("How many hearts does an octopus have?", 3, ""),
    NumericQuestion("What is the speed of sound in air at 20 C, to the nearest m/s?", 343, "m/s"),
    NumericQuestion("In what year did World War II end?", 1945, ""),
    NumericQuestion("How many natural moons does Mars have?", 2, ""),
    NumericQuestion("What is the height of the Burj Khalifa?", 828, "m"),
    NumericQuestion("How many cards are in a standard deck without jokers?", 52, ""),
    NumericQuestion("In what year were the first modern Olympic Games held in Athens?", 1896, ""),
    NumericQuestion("What is the length of an Olympic swimming pool?", 50, "m"),
    NumericQuestion("How many teeth does a typical adult human have, including wisdom teeth?", 32, ""),
    NumericQuestion("What is the average human body temperature in Celsius?", 37, "C"),
    NumericQuestion("In what year was the United States Declaration of Independence adopted?", 1776, ""),
    NumericQuestion("How many Great Lakes are there in North America?", 5, ""),
    NumericQuestion("What is the mean diameter of the Earth, to the nearest 10 km?", 12742, "km"),
    NumericQuestion("How many pairs of ribs does a typical human have?", 12, ""),
    NumericQuestion("What is the distance from the Earth to the Sun (1 AU), in millions of km?", 149.6, "million km"),
    NumericQuestion("How many strings does a standard violin have?", 4, ""),
    NumericQuestion("In what year did the Western Roman Empire traditionally fall?", 476, ""),
    NumericQuestion("How many days does the Moon take to orbit Earth (sidereal), to 1 decimal?", 27.3, "days"),
    NumericQuestion("In what year were euro banknotes and coins first introduced?", 2002, ""),
    NumericQuestion("What is the boiling point of water at sea level in Celsius?", 100, "C"),
    NumericQuestion("How many legs does an insect have?", 6, ""),
    NumericQuestion("What is the freezing point of water in Fahrenheit?", 32, "F"),
    NumericQuestion("Around what year did Gutenberg introduce his printing press in Europe?", 1440, ""),
]


BINARY: list[BinaryQuestion] = [
    BinaryQuestion("The Great Wall of China is visible from space with the naked eye.", False),
    BinaryQuestion("Mount Everest is the highest mountain on Earth above sea level.", True),
    BinaryQuestion("Sharks are mammals.", False),
    BinaryQuestion("The Pacific is the largest ocean on Earth.", True),
    BinaryQuestion("Antarctica is the largest desert on Earth.", True),
    BinaryQuestion("Humans and non-avian dinosaurs lived at the same time.", False),
    BinaryQuestion("An octopus has three hearts.", True),
    BinaryQuestion("Humans only use 10% of their brains.", False),
    BinaryQuestion("Venus is the hottest planet in the Solar System.", True),
    BinaryQuestion("Sound travels faster in water than in air.", True),
    BinaryQuestion("Glass at room temperature is a slow-flowing liquid.", False),
    BinaryQuestion("Bats are blind.", False),
    BinaryQuestion("Gold is denser than lead.", True),
    BinaryQuestion("Mercury is the closest planet to the Sun.", True),
    BinaryQuestion("Diamonds are made of carbon.", True),
    BinaryQuestion("The Mona Lisa was painted by Leonardo da Vinci.", True),
    BinaryQuestion("Saturn is the only planet in the Solar System with rings.", False),
    BinaryQuestion("Perfectly pure water is a good conductor of electricity.", False),
    BinaryQuestion("The 'tongue map' of distinct taste zones is a myth.", True),
    BinaryQuestion("Mount Kilimanjaro is the highest mountain in Africa.", True),
    BinaryQuestion("Penguins live naturally in the Arctic.", False),
    BinaryQuestion("Tomatoes are botanically a fruit.", True),
    BinaryQuestion("A year is a leap year every four years with no exceptions.", False),
    BinaryQuestion("The Sahara is larger than the contiguous United States.", True),
    BinaryQuestion("Lightning never strikes the same place twice.", False),
    BinaryQuestion("The human heart is located entirely on the left side of the chest.", False),
    BinaryQuestion("Goldfish have a memory of only a few seconds.", False),
    BinaryQuestion("The Dead Sea's shore is the lowest exposed land on Earth.", True),
    BinaryQuestion("The Great Barrier Reef is the world's largest living structure.", True),
    BinaryQuestion("Light travels faster than sound.", True),
    BinaryQuestion("Chameleons change colour mainly to camouflage themselves.", False),
    BinaryQuestion("Bananas grow on a plant that is botanically a herb, not a tree.", True),
    BinaryQuestion("Water expands when it freezes.", True),
    BinaryQuestion("The adult human has more than 300 bones.", False),
    BinaryQuestion("Neptune is the farthest recognised planet from the Sun.", True),
]


def counts() -> tuple[int, int]:
    """Return (numeric, binary) question counts. Handy for the CLI banner."""
    return len(NUMERIC), len(BINARY)
