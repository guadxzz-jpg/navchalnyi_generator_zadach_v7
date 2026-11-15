"""Навчальний генератор задач — Streamlit.
Запуск: python -m streamlit run app_final.py
Потрібен edu_quiz_gui_v7k_fixed.py поруч із цим файлом.
"""
import csv
import json
import io
import re
import uuid
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from time import monotonic

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Навчальний генератор задач", page_icon="📐", layout="centered", initial_sidebar_state="expanded")

try:
    from edu_quiz_gui_v7k_fixed import (
        gen_linear, gen_fractions, gen_percent, gen_powers, gen_quadratic,
        gen_geom_rect_square, gen_geom_triangle, gen_geom_parallelogram,
        gen_geom_mixed, parse_answer, frac_to_str, list_fr_to_str,
        is_correct, pct_to_grade12,
    )
except ImportError as exc:
    st.error("Не вдалося завантажити модуль генерації задач `edu_quiz_gui_v7k_fixed.py`.")
    st.info("Покладіть `edu_quiz_gui_v7k_fixed.py` в одну папку з цим файлом та встановіть залежності.")
    st.code(str(exc))
    st.stop()


FOCUS_MONITOR = components.declare_component(
    "school_focus_monitor_v7", path=str(Path(__file__).resolve().parent / "focus_monitor")
)

TOPICS = {
    "Алгебра": {
        "Лінійні рівняння": gen_linear,
        "Дроби": gen_fractions,
        "Відсотки": gen_percent,
        "Степені": gen_powers,
        "Квадратні рівняння": gen_quadratic,
    },
    "Геометрія": {
        "Прямокутник/квадрат": gen_geom_rect_square,
        "Трикутник": gen_geom_triangle,
        "Паралелограм": gen_geom_parallelogram,
        "Змішана добірка": gen_geom_mixed,
    },
}
HEADERS = ["student_name", "class", "mode", "section", "topic", "level", "timestamp",
           "task_number", "question", "correct", "user", "ok", "time_sec",
           "total_correct", "total_tasks", "percent", "grade12",
           "tab_switches", "away_seconds", "finish_reason"]


def as_text(value):
    if isinstance(value, (list, tuple)):
        return list_fr_to_str(value)
    if isinstance(value, Fraction):
        return frac_to_str(value)
    return str(value)


def safe_filename(value):
    return re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE).strip("._")[:60] or "student"


def init_state():
    defaults = {
        "started": False, "finished": False, "training_mode": False,
        "section": "Алгебра", "topic": "Лінійні рівняння", "level": 1,
        "n_tasks": 10, "student": "", "student_class": "", "current_i": 0,
        "questions": [], "answers": [], "checks": [], "durations": [],
        "entered_at": None, "started_at": None, "summary": None,
        "session_id": "", "saved_path": "", "show_review": False,
        "focus_events": [], "focus_hidden_since": None, "focus_enabled": False,
        "finish_reason": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def update_focus(value):
    """Browser-reported focus events; informative, not tamper-proof."""
    if not isinstance(value, dict) or value.get("session") != st.session_state.session_id:
        return
    events = value.get("events", [])
    if not isinstance(events, list):
        return
    clean = []
    for event in events[:1000]:
        if isinstance(event, dict):
            try:
                clean.append({"at": str(event.get("at", ""))[:40],
                              "returned_at": str(event.get("returned_at", ""))[:40],
                              "seconds": max(0.0, float(event.get("seconds", 0)))})
            except (ValueError, TypeError):
                pass
    if len(clean) >= len(st.session_state.focus_events):
        st.session_state.focus_events = clean
    st.session_state.focus_hidden_since = value.get("hidden_since")


def focus_totals():
    events = st.session_state.focus_events
    return len(events), round(sum(e["seconds"] for e in events), 1)


def focus_csv_bytes():
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["student_name", "class", "session_id", "left_at", "returned_at", "away_seconds"])
    for e in st.session_state.focus_events:
        writer.writerow([st.session_state.student, st.session_state.student_class,
                         st.session_state.session_id, e["at"], e["returned_at"], e["seconds"]])
    return out.getvalue().encode("utf-8-sig")


def csv_bytes(rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=";")
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def build_rows():
    ss = st.session_state
    s = ss.summary
    rows = []
    switches, away = focus_totals()
    for i, item in enumerate(ss.questions):
        rows.append([
            ss.student.strip(), ss.student_class.strip(),
            "Тренування" if ss.training_mode else "Тест", ss.section, ss.topic,
            ss.level, s["timestamp"], i + 1, item["q"], as_text(item["ans"]),
            ss.answers[i], int(ss.checks[i] is True), round(ss.durations[i], 1),
            s["correct"], s["total"], s["percent"],
            "" if ss.training_mode else s["grade12"], switches, away, ss.finish_reason,
        ])
    return rows


def finish_session(reason="completed"):
    ss = st.session_state
    if ss.finished:
        return
    ss.finish_reason = reason
    total = len(ss.questions)
    correct = sum(value is True for value in ss.checks)
    percent = round(100 * correct / total) if total else 0
    ss.summary = {
        "correct": correct, "total": total, "percent": percent,
        "grade12": None if ss.training_mode else pct_to_grade12(percent),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed": round(monotonic() - ss.started_at, 1),
    }
    ss.finished = True
    # Один атомарний запис на завершену сесію; повторний фініш не створює дублікатів.
    try:
        folder = Path("results")
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"{safe_filename(ss.student)}_{ss.session_id}.csv"
        path = folder / filename
        temp = path.with_suffix(".tmp")
        temp.write_bytes(csv_bytes(build_rows()))
        temp.replace(path)
        ss.saved_path = str(path)
    except OSError as exc:
        ss.saved_path = ""
        st.warning(f"Не вдалося зберегти CSV на сервері: {exc}. Скористайтеся кнопкою завантаження.")


def submit_answer():
    ss = st.session_state
    i = ss.current_i
    if ss.finished or ss.checks[i] is not None:
        return
    raw = ss.get(f"answer_{i}", "").strip()
    ss.answers[i] = raw
    ss.durations[i] = max(0.0, monotonic() - ss.entered_at)
    try:
        parsed = parse_answer(raw)
        ss.checks[i] = bool(is_correct(parsed, ss.questions[i]["ans"], raw=raw)) if raw else False
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        ss.checks[i] = False
    except Exception:
        # Помилка формату відповіді не повинна зупиняти проходження тесту.
        ss.checks[i] = False


def next_task():
    ss = st.session_state
    if ss.checks[ss.current_i] is None:
        submit_answer()
    if ss.current_i == len(ss.questions) - 1:
        finish_session()
    else:
        ss.current_i += 1
        ss.entered_at = monotonic()


def reset_session():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()


init_state()
ss = st.session_state
st.markdown("""
<style>
/* A consistent light palette, independent of Streamlit's theme. */
:root {--ink:#24314d;--muted:#61708d;--purple:#6654c8;--teal:#087f83;--line:#e1e6f2;}
html,body,[data-testid="stAppViewContainer"],.stApp {background:#f6f5fc!important;color:var(--ink)!important;}
[data-testid="stHeader"] {background:transparent!important;}
.block-container {max-width:930px;padding-top:2.1rem;padding-bottom:3rem;}
[data-testid="stSidebar"] {background:#fff!important;border-right:1px solid #e4e4f2!important;}
[data-testid="stSidebar"] * {color:#263453;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {color:#34415d!important;font-weight:650!important;}
[data-testid="stSidebar"] input,[data-testid="stSidebar"] [data-baseweb="select"]>div {background:#f8f8ff!important;color:#24314d!important;border-color:#d8dcee!important;}
[data-testid="stSidebar"] input:disabled,[data-testid="stSidebar"] [aria-disabled="true"] {opacity:1!important;color:#253454!important;-webkit-text-fill-color:#253454!important;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {opacity:1!important;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {opacity:1!important;}
h1,h2,h3,h4 {color:#253454!important;letter-spacing:-.02em;}
p,li,label,[data-testid="stMarkdownContainer"] {color:#283750;}
[data-testid="stCaptionContainer"] p {color:#61708d!important;}
[data-testid="stTextInput"] input {background:#fff!important;color:#24314d!important;border:1px solid #d4d9ec!important;border-radius:12px!important;min-height:47px;}
[data-testid="stTextInput"] input::placeholder {color:#8290a7!important;}
[data-testid="stTextInput"] label p {color:#35425c!important;font-weight:650;}
.stButton button {border-radius:12px!important;min-height:46px!important;font-weight:700!important;border:1px solid #d9dcee!important;background:#fff!important;color:#493aa4!important;transition:transform .18s ease,box-shadow .18s ease,background .18s ease!important;}
.stButton button:hover:enabled {transform:translateY(-2px);box-shadow:0 7px 16px #5048a425!important;}
.stButton button[kind="primary"] {background:linear-gradient(110deg,#6654c8,#4d7bd5)!important;color:#fff!important;border:0!important;}
.stButton button:disabled {opacity:.85!important;color:#52617b!important;background:#e9ebf4!important;}
.stDownloadButton button {background:#f0edff!important;color:#43339b!important;border:1px solid #c8c0ee!important;font-weight:750!important;}
.stDownloadButton button * {color:#43339b!important;opacity:1!important;}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] input:disabled {background:#fff!important;color:#24314d!important;-webkit-text-fill-color:#24314d!important;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {color:#263453!important;opacity:1!important;}
[data-testid="stSidebar"] [data-testid="stTextInput"] input::placeholder {color:#63718b!important;-webkit-text-fill-color:#63718b!important;}
[data-testid="stProgressBar"]>div>div>div {background:linear-gradient(90deg,#7b65d9,#0eaaa5)!important;}
[data-testid="stMetric"] {background:#fff;padding:17px;border:1px solid var(--line);border-radius:16px;box-shadow:0 5px 15px #2b34610a;}
[data-testid="stMetricValue"] {color:#5e4ac2!important;}
[data-testid="stAlert"] {border-radius:13px!important;}
.school-banner {background:linear-gradient(115deg,#5844b4 0%,#6d61cf 52%,#258f9c 100%);padding:27px 30px;border-radius:22px;margin-bottom:24px;box-shadow:0 12px 28px #6559c02c;position:relative;overflow:hidden;animation:school-rise .6s ease both;}
.school-banner:after {content:'✦';position:absolute;right:24px;top:3px;font-size:100px;color:#ffffff19;pointer-events:none;}
.school-banner .heading {font-size:1.85rem;font-weight:800;line-height:1.25;color:white!important;position:relative;z-index:1;}
.school-banner .subtitle {font-size:.96rem;line-height:1.6;color:#f7f5ff!important;margin-top:8px;position:relative;z-index:1;}
.school-task {background:#fff;border:1px solid #e1def6;border-left:6px solid #1ca59c;border-radius:18px;padding:26px 28px;margin:19px 0 24px;box-shadow:0 8px 22px #34356c0b;animation:school-rise .45s ease both;}
.school-task .tag {color:#6450bd!important;font-weight:750;font-size:.86rem;margin-bottom:13px;text-transform:uppercase;letter-spacing:.045em;}
.school-task .question {color:#253454!important;font-size:1.25rem;font-weight:550;line-height:1.75;white-space:pre-wrap;}
.school-steps {display:flex;gap:7px;margin:8px 0 14px;}
.school-step {height:7px;flex:1;border-radius:10px;background:#e2e3f1;}
.school-step.done {background:#16a59e;}
.school-step.current {background:#725ed4;animation:school-pulse 1.8s ease-in-out infinite;}
.school-chip {display:inline-block;border-radius:30px;background:#e9e6fa;color:#5646a8!important;padding:7px 13px;font-size:.83rem;font-weight:700;margin:0 6px 9px 0;}
@keyframes school-rise {from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes school-pulse {50%{box-shadow:0 0 0 4px #7665d420;}}
@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;}}
@media(max-width:700px){.block-container{padding-top:1rem}.school-banner{padding:22px}.school-banner .heading{font-size:1.4rem}.school-task{padding:20px}.school-task .question{font-size:1.1rem}}

/* High contrast: inputs, select controls and download buttons */
[data-testid="stSidebar"] [data-testid="stTextInput"] input,
[data-testid="stSidebar"] [data-testid="stTextInput"] input:focus,
[data-testid="stSidebar"] [data-testid="stTextInput"] input:disabled,
[data-testid="stTextInput"] input,
[data-testid="stTextInput"] input:disabled {
 background-color:#ffffff!important; color:#14243d!important;
 -webkit-text-fill-color:#14243d!important; opacity:1!important;
 caret-color:#4f46e5!important;
}
[data-testid="stSidebar"] [data-testid="stTextInput"] input::placeholder,
[data-testid="stTextInput"] input::placeholder {color:#66758e!important;-webkit-text-fill-color:#66758e!important;opacity:1!important;}
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"] {background:#ffffff!important;}
[data-testid="stSidebar"] [data-baseweb="select"]>div {background:#fff!important;color:#14243d!important;}
[data-testid="stSidebar"] [data-baseweb="select"] span {color:#14243d!important;-webkit-text-fill-color:#14243d!important;}
.stDownloadButton button,.stDownloadButton button:enabled,
[data-testid="stDownloadButton"] button {background:#e9e5ff!important;color:#34218b!important;border:2px solid #b9acee!important;opacity:1!important;}
.stDownloadButton button *,[data-testid="stDownloadButton"] button * {color:#34218b!important;-webkit-text-fill-color:#34218b!important;opacity:1!important;}
[data-testid="stSidebar"] button:disabled {background:#e8e8f1!important;color:#36415c!important;opacity:1!important;}
</style>""", unsafe_allow_html=True)

# While a session is active, hide Streamlit's automatic multipage navigation.
# This is a UI lock, not a browser/security restriction; other pages must check
# st.session_state["started"] and redirect if they are directly opened.
if ss.started and not ss.finished:
    st.markdown("""<style>
    [data-testid="stSidebarNav"], [data-testid="stSidebarNavItems"],
    [data-testid="stPageLink-NavLink"], [data-testid="stSidebarNavSeparator"] {display:none!important;}
    </style>""", unsafe_allow_html=True)

st.markdown('<div class="school-banner"><div class="heading">🎒 Навчальний генератор задач</div><div class="subtitle">Шкільні завдання з алгебри та геометрії · Тренування та перевірка знань</div></div>', unsafe_allow_html=True)
if ss.started and not ss.finished:
    st.info("🔒 Шкільний режим: налаштування та навігацію всередині програми заблоковано до завершення роботи.")

with st.sidebar:
    st.header("Налаштування")
    locked = ss.started
    st.text_input("Прізвище та ім'я учня *", key="student", disabled=locked,
                  placeholder="Прізвище Ім'я")
    st.text_input("Клас (необов'язково)", key="student_class", disabled=locked,
                  placeholder="Наприклад, 5-А")
    st.checkbox("Режим тренування (без оцінки)", key="training_mode", disabled=locked)
    st.selectbox("Розділ", list(TOPICS), key="section", disabled=locked)
    available = list(TOPICS[ss.section])
    # Різні ключі для різних розділів: немає конфлікту стану selectbox.
    selected = st.selectbox("Тема", available, key=f"topic_for_{ss.section}", disabled=locked)
    if not locked:
        ss.topic = selected
    st.selectbox("Рівень складності", [1, 2, 3], key="level", disabled=locked)
    maximum = 50 if ss.training_mode else 12
    # При зміні режиму не залишаємо значення, більше допустимого максимуму.
    if not locked and ss.n_tasks > maximum:
        ss.n_tasks = maximum
    st.slider("Кількість завдань", 1, maximum, key="n_tasks", disabled=locked)
    start = st.button("Почати сесію", type="primary", disabled=locked or not ss.student.strip(),
                      use_container_width=True)

if start:
    generator = TOPICS[ss.section][ss.topic]
    try:
        generated = []
        for _ in range(ss.n_tasks):
            q, answer = generator(level=ss.level)
            generated.append({"q": str(q), "ans": answer})
    except Exception as exc:
        st.error(f"Помилка генерації задач: {exc}")
        st.stop()
    ss.questions = generated
    ss.answers = [""] * len(generated)
    ss.checks = [None] * len(generated)
    ss.durations = [0.0] * len(generated)
    ss.current_i = 0
    ss.started = True
    ss.finished = False
    ss.summary = None
    ss.saved_path = ""
    ss.focus_events = []
    ss.focus_hidden_since = None
    ss.finish_reason = ""
    ss.session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    ss.started_at = monotonic()
    ss.entered_at = ss.started_at
    st.rerun()

# Контроль активності увімкнений автоматично лише під час тесту.
# Компонент працює в iframe і повідомляє сервер про повернення у вкладку.
if ss.started and not ss.finished and not ss.training_mode:
    try:
        focus_payload = FOCUS_MONITOR(session=ss.session_id, key="focus_monitor_active", default=None)
        update_focus(focus_payload)
        violations, away_seconds = focus_totals()
        if violations >= 3:
            finish_session(reason="three_tab_switches")
            st.rerun()
        if violations:
            st.warning(f"⚠️ Зафіксовано виходів із вкладки: {violations} із 3. Після третього тест завершиться автоматично.")
        else:
            st.caption("🛡️ Контроль вкладки активний · Порушень: 0 із 3")
    except Exception as exc:
        st.error("Не вдалося запустити контроль вкладки. Тестування призупинено, щоб не проводити тест без заявленого контролю.")
        st.code(str(exc))
        st.stop()

if not ss.started:
    st.info("Введіть ім'я учня, оберіть тему й натисніть «Почати сесію».")
elif not ss.finished:
    i = ss.current_i
    total = len(ss.questions)
    st.subheader(f"Завдання {i + 1} із {total}")
    st.markdown('<div class="school-steps">'+''.join('<div class="school-step '+('done' if j < i else 'current' if j == i else '')+'"></div>' for j in range(total))+'</div>',unsafe_allow_html=True)
    st.progress(i / total)
    st.markdown(f'<span class="school-chip">{ "Тренування" if ss.training_mode else "Тестування" }</span><span class="school-chip">{ss.section}</span><span class="school-chip">Рівень {ss.level}</span>',unsafe_allow_html=True)
    import html
    st.markdown(f'<div class="school-task"><div class="tag">✏️ Розв’яжіть завдання</div><div class="question">{html.escape(ss.questions[i]["q"])}</div></div>', unsafe_allow_html=True)
    checked = ss.checks[i] is not None
    st.text_input("Відповідь (наприклад: -8,3 або -8.3; дріб -25/3; корені 1; 2)", key=f"answer_{i}",
                  disabled=checked, placeholder="Введіть відповідь")
    left, right = st.columns(2)
    with left:
        st.button("Перевірити" if ss.training_mode else "Зафіксувати відповідь",
                  on_click=submit_answer, disabled=checked, use_container_width=True)
    with right:
        st.button("Завершити тест" if i == total - 1 else "Далі ➜",
                  on_click=next_task, type="primary", use_container_width=True)
    if checked:
        if ss.training_mode:
            if ss.checks[i]:
                st.success("Правильно!")
            else:
                st.error(f"Неправильно. Правильна відповідь: {as_text(ss.questions[i]['ans'])}")
        else:
            st.info("Відповідь зафіксовано. Правильні відповіді будуть доступні після завершення тесту.")
    else:
        st.caption("Десяткові відповіді приймаються з коректним округленням: наприклад, -8,3 для -8,333… . Натисніть «Далі», щоб зберегти відповідь.")
else:
    s = ss.summary
    st.progress(1.0)
    st.header("Результати роботи")
    a, b, c = st.columns(3)
    a.metric("Правильних", f"{s['correct']} / {s['total']}")
    b.metric("Успішність", f"{s['percent']}%")
    c.metric("Час", f"{s['elapsed']:.0f} с")
    if ss.finish_reason == "three_tab_switches":
        st.error("⛔ Тест автоматично завершено: зафіксовано 3 виходи з вкладки. Незавершені завдання зараховано як невиконані.")
    if ss.training_mode:
        st.success("Тренування завершено (без оцінки).")
    else:
        st.success(f"Оцінка за 12-бальною шкалою: **{s['grade12']}**")
    switches, away = focus_totals()
    st.metric("Виходи з вкладки", f"{switches} / 3")
    st.caption(f"Приблизний час поза вкладкою: {away:.1f} с")
    st.download_button("⬇️ Завантажити журнал виходів (CSV)", data=focus_csv_bytes(),
                       file_name=f"focus_{safe_filename(ss.student)}_{ss.session_id}.csv",
                       mime="text/csv", use_container_width=True)
    st.download_button("⬇️ Завантажити результати (CSV)",
                       data=csv_bytes(build_rows()),
                       file_name=f"results_{safe_filename(ss.student)}_{ss.session_id}.csv",
                       mime="text/csv", use_container_width=True)
    if ss.saved_path:
        st.caption(f"Результати також збережено на сервері: {ss.saved_path}")
    with st.expander("Переглянути відповіді"):
        for j, item in enumerate(ss.questions):
            status = "✅" if ss.checks[j] else "❌"
            st.markdown(f"**{j + 1}. {status} {item['q']}**")
            st.write(f"Відповідь учня: {ss.answers[j] or 'Не надано'}")
            st.write(f"Правильна відповідь: {as_text(item['ans'])}")
    st.button("🔁 Нова сесія", on_click=reset_session, use_container_width=True)
