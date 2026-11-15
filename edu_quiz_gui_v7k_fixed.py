
# edu_quiz_gui_v7k.py — мінімальний робочий модуль для app.py
# Містить генератори задач (алгебра/геометрія), парсер відповідей, перевірку,
# конвертацію у 12-бальну систему та утиліти збереження.
from __future__ import annotations
from fractions import Fraction
from random import randint, choice
import os

# ------------- УТИЛІТИ -------------
def ensure_results_dir():
    os.makedirs("results", exist_ok=True)

def frac_to_str(fr: Fraction) -> str:
    if isinstance(fr, Fraction):
        if fr.denominator == 1:
            return str(fr.numerator)
        return f"{fr.numerator}/{fr.denominator}"
    return str(fr)

def list_fr_to_str(v) -> str:
    # Форматує список дробів або чисел: "a, b, c"
    if isinstance(v, (list, tuple)):
        return ", ".join(frac_to_str(x) for x in v)
    return frac_to_str(v)

def parse_answer(s: str):
    """Числа, дроби, десяткові з комою або крапкою; корені через ; ."""
    if s is None or not str(s).strip():
        raise ValueError("Порожня відповідь")
    raw = str(s).strip().replace("−", "-").replace(" ", "")
    # Крапка з комою розділяє корені, кома може бути десятковим знаком.
    if ";" in raw:
        parts = raw.split(";")
    elif "," in raw and raw.count(",") > 1:
        parts = raw.split(",")
    elif "," in raw:
        # Неоднозначне "1,2": за замовчуванням десяткове число;
        # для коренів рекомендуємо крапку з комою.
        parts = [raw.replace(",", ".")]
    else:
        parts = [raw]
    if not all(parts):
        raise ValueError("Неправильний формат")
    values = [Fraction(p.replace(",", ".")) for p in parts]
    return values[0] if len(values) == 1 else values

def _number_matches(user, correct, raw=None):
    """Exact fractions, or correctly rounded decimal answers (>=1 decimal place)."""
    u, c = Fraction(user), Fraction(correct)
    if u == c:
        return True
    if raw is None:
        return False
    raw = str(raw).strip().replace("−", "-").replace(",", ".")
    if "/" in raw or "." not in raw:
        return False
    decimals = len(raw.split(".", 1)[1])
    if decimals < 1 or decimals > 12:
        return False
    # Accept the mathematical result when it rounds to the student's decimal.
    # Half-unit in the last entered decimal place; strict boundary avoids ties.
    tolerance = Fraction(1, 2 * (10 ** decimals))
    return abs(u - c) < tolerance


def is_correct(user, correct, raw=None) -> bool:
    """Compare exact answers and decimal rounding, including unordered roots."""
    if isinstance(correct, (list, tuple)):
        if not isinstance(user, (list, tuple)) or len(user) != len(correct):
            return False
        raw_parts = str(raw).split(";") if raw is not None else []
        remaining = list(correct)
        for index, item in enumerate(user):
            original = raw_parts[index].strip() if index < len(raw_parts) else None
            match = next((j for j, candidate in enumerate(remaining)
                          if _number_matches(item, candidate, original)), None)
            if match is None:
                return False
            remaining.pop(match)
        return not remaining
    if isinstance(user, (list, tuple)):
        return False
    try:
        return _number_matches(user, correct, raw)
    except (ValueError, TypeError, ZeroDivisionError):
        return False

def pct_to_grade12(pct: int) -> int:
    """
    Просте шкалювання % → 12-бальна оцінка.
      0-9%  → 1
      10-24 → 2
      25-39 → 3
      40-49 → 4
      50-59 → 6
      60-69 → 8
      70-79 → 9
      80-89 → 10
      90-96 → 11
      97-100 → 12
    """
    p = max(0, min(100, int(pct)))
    if p < 10: return 1
    if p < 25: return 2
    if p < 40: return 3
    if p < 50: return 4
    if p < 60: return 6
    if p < 70: return 8
    if p < 80: return 9
    if p < 90: return 10
    if p < 97: return 11
    return 12

# ------------- ГЕНЕРАТОРИ АЛГЕБРИ -------------
def _rand_nonzero(low, high):
    x = 0
    while x == 0:
        x = randint(low, high)
    return x

def gen_linear(level=1):
    """
    Лінійні рівняння виду ax + b = c
    level 1: |a|,|b|,|c| ≤ 10
    level 2: ≤ 20
    level 3: ≤ 50
    """
    LIM = {1: 10, 2: 20, 3: 50}[level]
    a = _rand_nonzero(-LIM, LIM)
    b = randint(-LIM, LIM)
    c = randint(-LIM, LIM)
    # a x + b = c → x = (c-b)/a
    x = Fraction(c - b, a)
    q = f"Розв'яжіть рівняння: {a}·x + ({b}) = {c}. Відповідь x = ?"
    return q, x

def gen_fractions(level=1):
    """
    Дії з дробами: додавання/віднімання.
    """
    LIM = {1: 7, 2: 12, 3: 20}[level]
    a = Fraction(randint(1, LIM), randint(2, LIM+1))
    b = Fraction(randint(1, LIM), randint(2, LIM+1))
    op = choice(["+", "-"])
    if op == "+":
        ans = a + b
    else:
        ans = a - b
    q = f"Обчисліть: {frac_to_str(a)} {op} {frac_to_str(b)} = ?"
    return q, ans

def gen_percent(level=1):
    """
    Відсотки: знайти p% від n.
    """
    LIMN = {1: 100, 2: 500, 3: 2000}[level]
    n = randint(20, LIMN)
    p = choice([5, 10, 12, 15, 20, 25, 30, 40, 50])
    ans = Fraction(n * p, 100)
    q = f"Знайдіть {p}% від {n}."
    return q, ans

def gen_powers(level=1):
    """
    Степені: обчислити a^b (малі числа).
    """
    A = {1: (2, 5), 2: (2, 7), 3: (2, 9)}[level]
    a = randint(*A)
    b = randint(2, 5 if level==1 else (6 if level==2 else 7))
    ans = Fraction(a ** b, 1)
    q = f"Обчисліть: {a}^{b}."
    return q, ans

def gen_quadratic(level=1):
    """
    Квадратні рівняння з цілими коренями (можуть бути 1 або 2 корені).
    """
    # Будуємо (x - r1)(x - r2) = 0
    L = {1: 5, 2: 7, 3: 9}[level]
    r1 = randint(-L, L)
    r2 = randint(-L, L)
    a = choice([1, 1, 1, 2])  # частіше a=1
    b = -a*(r1 + r2)
    c = a*r1*r2
    # x^2 + (b/a)x + c/a = 0 (якщо a=1 просто)
    if a == 1:
        eq = f"x² + ({b})x + ({c}) = 0"
    else:
        eq = f"{a}x² + ({b})x + ({c}) = 0"
    # корені:
    if r1 == r2:
        ans = Fraction(r1, 1)
    else:
        ans = sorted([Fraction(r1,1), Fraction(r2,1)], key=lambda z: (z.numerator/z.denominator))
    q = f"Розв'яжіть квадратне рівняння: {eq}. Вкажіть корінь або корені (розділяйте корені крапкою з комою)."
    return q, ans

# ------------- ГЕНЕРАТОРИ ГЕОМЕТРІЇ -------------
def gen_geom_rect_square(level=1):
    """
    Площа прямокутника/квадрата. Випадково обираємо фігуру.
    """
    if choice([True, False]):
        a = randint(2, 15*level)
        b = randint(2, 15*level)
        S = a*b
        q = f"Знайдіть площу прямокутника зі сторонами {a} см і {b} см."
        return q, Fraction(S,1)
    else:
        a = randint(2, 20*level)
        S = a*a
        q = f"Знайдіть площу квадрата зі стороною {a} см."
        return q, Fraction(S,1)

def gen_geom_triangle(level=1):
    """
    Площа трикутника за формулою S = 1/2 * a * h.
    """
    a = randint(3, 20*level)
    h = randint(2, 15*level)
    S = Fraction(a*h, 2)
    q = f"Знайдіть площу трикутника з основою {a} см і висотою {h} см."
    return q, S

def gen_geom_parallelogram(level=1):
    """
    Площа паралелограма: S = a * h.
    """
    a = randint(3, 20*level)
    h = randint(2, 15*level)
    S = a*h
    q = f"Знайдіть площу паралелограма з основою {a} см і висотою {h} см."
    return q, Fraction(S,1)

def gen_geom_mixed(level=1):
    """
    Змішана добірка: випадково обираємо один із геометричних генераторів.
    """
    f = choice([gen_geom_rect_square, gen_geom_triangle, gen_geom_parallelogram])
    return f(level=level)
