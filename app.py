#!/usr/bin/env python3
"""
================================================================================
 LINGO-SRS - Antarmuka Web (Streamlit)
================================================================================
File ini HANYA lapisan UI. Semua logika (database, SRS engine, interleaving
engine, dataset 15 hari, peta kurikulum, rekomendasi Coursera) diimpor
langsung dari lingo_srs.py -- tidak ada duplikasi/rewrite logika di sini.

Jalankan:
    streamlit run app.py

--------------------------------------------------------------------------
TOKEN DESAIN (ubah di satu tempat ini kalau mau ganti nuansa ke depannya):

  KONSEP: spaced repetition aslinya metode analog -- kotak kartu index
  (Leitner box) dengan kompartemen per interval. Bahasa visualnya diangkat
  dari situ: soal = kartu index fisik, navigasi = tab pembatas map arsip.

  Kertas/parchment  : #FBF7EE (warna kartu)
  Navy tinta         : #1F2A44 (struktur, nav, teks judul)
  Teks isi           : #3B3226 (cokelat tinta lembut, bukan hitam pekat)
  Aksen brass        : #A97C34 (SATU aksen -- tombol utama & tab aktif saja)
  Sukses/benar       : #5B8266 (sage)
  Perlu perhatian     : #B0503D (rust muted, bukan terracotta cerah)
  Garis/border        : #DDD4BF
  Tipografi           : Fraunces (judul, serif berkarakter) + IBM Plex Sans
                        (isi/label)
--------------------------------------------------------------------------

Catatan penting soal Streamlit:
- Streamlit menjalankan ulang seluruh script setiap kali ada interaksi
  (klik tombol, submit form). Karena itu, state sesi belajar yang sedang
  berjalan (soal keberapa, skor yang sudah dikumpulkan, dst) TIDAK boleh
  disimpan sebagai variabel biasa -- harus disimpan di st.session_state
  supaya tidak hilang / ter-reset setiap re-run.
- Koneksi SQLite (objek Database) juga disimpan di session_state supaya
  tidak dibuka ulang terus-menerus.
================================================================================
"""

import datetime
import os
import streamlit as st

# Ambil kredensial Turso dari Streamlit Secrets (Settings -> Secrets di
# Streamlit Cloud, atau file .streamlit/secrets.toml saat run lokal) dan
# taruh sebagai environment variable SEBELUM lingo_srs.Database() dibuat.
# Kalau secrets ini tidak diisi, aplikasi otomatis jatuh ke SQLite lokal
# biasa (perilaku lama, tidak ada yang rusak).
if "TURSO_DATABASE_URL" in st.secrets:
    os.environ["TURSO_DATABASE_URL"] = st.secrets["TURSO_DATABASE_URL"]
    os.environ["TURSO_AUTH_TOKEN"] = st.secrets["TURSO_AUTH_TOKEN"]

from lingo_srs import (
    Database,
    SRSEngine,
    Interleaver,
    CURRICULUM_MAP,
    COURSERA_TRACKS,
    LANG_LABEL,
    TYPE_LABEL,
    _check_answer,
)

st.set_page_config(page_title="Lingo-SRS", page_icon="\U0001F4C7", layout="centered")


# ==============================================================================
# CSS GLOBAL -- satu-satunya tempat yang mengatur seluruh nuansa visual
# ==============================================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

    :root {
        --paper: #FBF7EE;
        --bg: #F1ECE0;
        --navy: #1F2A44;
        --ink: #3B3226;
        --ink-soft: #8A7F6C;
        --brass: #A97C34;
        --sage: #5B8266;
        --rust: #B0503D;
        --line: #DDD4BF;
    }

    #MainMenu, footer, header {visibility: hidden;}

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
        color: var(--ink);
    }
    .stApp { background: var(--bg); }

    h1, h2, h3 { font-family: 'Fraunces', serif; font-weight: 600; color: var(--navy); }

    .block-container { padding-top: 1.4rem; padding-bottom: 4rem; max-width: 640px; }

    /* Brand mark -- tanpa gradasi, tanpa efek berlebihan */
    .lsrs-brand {
        font-family: 'Fraunces', serif;
        font-weight: 600;
        font-size: 1.25rem;
        color: var(--navy);
        margin-bottom: 0.9rem;
        border-bottom: 2px solid var(--brass);
        display: inline-block;
        padding-bottom: 2px;
    }

    /* --- Navigasi bergaya tab pembatas map arsip --- */
    div[role="radiogroup"] {
        display: flex;
        gap: 3px;
        border-bottom: 2px solid var(--navy);
        margin-bottom: 20px;
    }
    div[role="radiogroup"] label {
        flex: 1;
        text-align: center;
        background: var(--line);
        color: var(--ink-soft);
        border-radius: 8px 8px 0 0 !important;
        padding: 8px 4px !important;
        font-size: 0.82rem;
        font-weight: 500;
        border: none !important;
        margin-bottom: -2px;
    }
    div[role="radiogroup"] label div:first-child { display: none; }
    div[role="radiogroup"] label:has(input:checked) {
        background: var(--navy);
        color: var(--paper);
    }

    /* --- Kartu index untuk soal, ala kartu perpustakaan --- */
    .lsrs-card {
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 4px 4px 4px 4px;
        padding: 22px 22px 18px 22px;
        margin-bottom: 16px;
        position: relative;
        box-shadow: 3px 3px 0 var(--line);
    }
    /* sudut "terpotong" di kanan atas, ciri khas kartu index fisik */
    .lsrs-card::before {
        content: "";
        position: absolute;
        top: 0; right: 0;
        width: 0; height: 0;
        border-style: solid;
        border-width: 0 18px 18px 0;
        border-color: transparent var(--bg) transparent transparent;
    }

    /* Tag kategori -- kotak kecil bergaris, bukan pil */
    .lsrs-tag {
        display: inline-block;
        padding: 3px 9px;
        border: 1px solid var(--line);
        border-radius: 3px;
        font-size: 0.72rem;
        color: var(--ink-soft);
        margin-right: 6px;
        margin-bottom: 8px;
        background: var(--bg);
    }

    /* Label "due" ala stempel tanggal kartu perpustakaan */
    .lsrs-duetag {
        display: inline-block;
        padding: 3px 10px;
        border: 1px dashed var(--brass);
        border-radius: 3px;
        font-size: 0.72rem;
        color: var(--brass);
        font-weight: 600;
    }

    /* Kotak statistik "isi kotak kartu" di beranda */
    .lsrs-box {
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 4px;
        padding: 16px;
        text-align: center;
    }
    .lsrs-box .num { font-family: 'Fraunces', serif; font-size: 1.9rem; font-weight: 600; color: var(--navy); }
    .lsrs-box .lbl { color: var(--ink-soft); font-size: 0.8rem; margin-top: 2px; }

    /* Tombol utama -- solid navy, aksen brass, sudut sedang (bukan pil) */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: var(--navy);
        color: var(--paper);
        border: none;
        border-radius: 6px;
        padding: 0.55rem 1.3rem;
        font-weight: 600;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: var(--brass);
    }
    div[data-testid="stButton"] > button[kind="secondary"] {
        border-radius: 6px;
        border: 1px solid var(--line);
    }

    /* Progress bar -- brass solid, bukan gradasi pelangi */
    div[data-testid="stProgress"] > div > div > div {
        background: var(--brass);
        border-radius: 4px;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 4px !important;
        border-color: var(--line) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# INISIALISASI STATE (sekali per browser session)
# ==============================================================================

def init_state():
    if "db" not in st.session_state:
        st.session_state.db = Database()
        st.session_state.srs = SRSEngine(st.session_state.db)
        st.session_state.interleaver = Interleaver(st.session_state.db)

    st.session_state.setdefault("session_items", None)
    st.session_state.setdefault("session_id", None)
    st.session_state.setdefault("current_idx", 0)
    st.session_state.setdefault("stage", "idle")
    st.session_state.setdefault("last_correct", None)
    st.session_state.setdefault("metacog_scores", [])


init_state()
db = st.session_state.db
srs = st.session_state.srs
interleaver = st.session_state.interleaver


# ==============================================================================
# BRAND MARK + NAVIGASI (tab pembatas map arsip)
# ==============================================================================

st.markdown('<div class="lsrs-brand">Lingo-SRS</div>', unsafe_allow_html=True)

page = st.radio(
    "Menu",
    ["Kartu Hari Ini", "Kotak Progress", "Peta Kurikulum", "Rak Kursus"],
    horizontal=True,
    label_visibility="collapsed",
)


# ==============================================================================
# HALAMAN 1: SESI BELAJAR (Retrieval Practice + interleaving + SRS)
# ==============================================================================

def start_new_session():
    today = datetime.date.today()
    items = interleaver.build_session(target_size=12, today=today)
    st.session_state.session_items = items
    st.session_state.current_idx = 0
    st.session_state.stage = "answering" if items else "idle"
    st.session_state.metacog_scores = []

    st.session_state.session_id = db.insert_and_get_id(
        "INSERT INTO sessions (date, items_reviewed, avg_metacog) VALUES (?,0,0)",
        (today.isoformat(),),
    )


def _due_today_count():
    return db.q1(
        "SELECT COUNT(*) c FROM progress WHERE next_review <= ?",
        (datetime.date.today().isoformat(),),
    )["c"]


def page_session():
    if st.session_state.stage == "idle":
        due = _due_today_count()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f'<div class="lsrs-box"><div class="num">{due}</div>'
                f'<div class="lbl">Kartu jatuh tempo</div></div>',
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f'<div class="lsrs-box"><div class="num">12</div>'
                f'<div class="lbl">Kartu per sesi</div></div>',
                unsafe_allow_html=True,
            )
        st.write("")
        st.caption(
            "Setiap sesi mencampur Inggris & Mandarin, tata bahasa & kosakata -- "
            "urutan ini disengaja (interleaving), bukan acak."
        )
        if st.button("Buka Kotak Kartu", type="primary"):
            start_new_session()
            st.rerun()
        return

    items = st.session_state.session_items
    idx = st.session_state.current_idx

    if st.session_state.stage == "done" or (items is not None and idx >= len(items)):
        _finish_session()
        return

    item = items[idx]
    total = len(items)

    st.progress((idx) / total, text=f"Kartu {idx + 1} dari {total}")

    st.markdown(
        f"""
        <div class="lsrs-card">
            <span class="lsrs-tag">{LANG_LABEL[item['lang']]}</span>
            <span class="lsrs-tag">{item['level'].capitalize()}</span>
            <span class="lsrs-tag">{TYPE_LABEL[item['item_type']]}</span>
        """,
        unsafe_allow_html=True,
    )
    st.subheader(item["prompt"])
    if item["hint"]:
        st.caption(f"Hint: {item['hint']}")
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.stage == "answering":
        with st.form(key=f"answer_form_{idx}"):
            user_answer = st.text_input("Jawaban kamu", key=f"input_{idx}")
            submitted = st.form_submit_button("Kirim Jawaban", type="primary")
        if submitted:
            correct = _check_answer(user_answer, item["answer"])
            st.session_state.last_correct = correct
            st.session_state.last_user_answer = user_answer
            st.session_state.stage = "feedback"
            st.rerun()

    elif st.session_state.stage == "feedback":
        if st.session_state.last_correct:
            st.success("Benar!")
        else:
            st.error(f"Kurang tepat. Jawaban benar: **{item['answer']}**")

        st.markdown("**Seberapa yakin kamu dengan jawaban tadi?**")
        st.caption("1 Lupa total  ·  2 Ragu-ragu  ·  3 Cukup yakin  ·  4 Sangat yakin")
        cols = st.columns(4)
        labels = ["1", "2", "3", "4"]
        for i, col in enumerate(cols, start=1):
            if col.button(labels[i - 1], key=f"metacog_{idx}_{i}", use_container_width=True):
                _submit_metacog(item, i)
                st.rerun()


def _submit_metacog(item, score):
    today = datetime.date.today()
    new_stage, next_review = srs.record_answer(
        item["id"], st.session_state.last_correct, score, today
    )
    st.session_state.metacog_scores.append(score)
    db.exec(
        "INSERT INTO session_log (session_id, material_id, correct, metacog_score) VALUES (?,?,?,?)",
        (st.session_state.session_id, item["id"], int(st.session_state.last_correct), score),
    )
    st.session_state._last_schedule_note = f"Kembali ke kotak: {new_stage} ({next_review.isoformat()})"
    st.session_state.current_idx += 1
    st.session_state.stage = "answering" if st.session_state.current_idx < len(st.session_state.session_items) else "done"


def _finish_session():
    scores = st.session_state.metacog_scores
    avg = sum(scores) / len(scores) if scores else 0

    st.markdown(
        f'<div class="lsrs-box"><div class="num">{avg:.2f} / 4</div>'
        f'<div class="lbl">Rata-rata keyakinan diri sesi ini</div></div>',
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown("**Seberapa menantang sesi ini secara keseluruhan?**")
    cols = st.columns(4)
    labels = ["1", "2", "3", "4"]
    captions = ["Terlalu mudah", "Cukup mudah", "Menantang", "Sangat menantang"]
    for i, col in enumerate(cols, start=1):
        with col:
            if st.button(labels[i - 1], key=f"session_rating_{i}", use_container_width=True):
                db.exec(
                    "UPDATE sessions SET items_reviewed=?, avg_metacog=?, session_rating=? WHERE id=?",
                    (len(st.session_state.session_items), avg, i, st.session_state.session_id),
                )
                st.session_state.stage = "idle"
                st.session_state.session_items = None
                st.rerun()
            st.caption(captions[i - 1])

    st.caption(
        "Kartu yang salah/skornya rendah otomatis kembali ke kotak lebih cepat "
        "(spaced repetition). Pilih tingkat kesulitan di atas untuk menyimpan sesi."
    )


# ==============================================================================
# HALAMAN 2: DASHBOARD PROGRESS
# ==============================================================================

def page_dashboard():
    due = _due_today_count()
    total_sessions = db.q1("SELECT COUNT(*) c FROM sessions")["c"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'<div class="lsrs-box"><div class="num">{due}</div>'
            f'<div class="lbl">Jatuh tempo hari ini</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="lsrs-box"><div class="num">{total_sessions}</div>'
            f'<div class="lbl">Total sesi selesai</div></div>',
            unsafe_allow_html=True,
        )

    st.write("")
    for lang in ("en", "zh"):
        st.markdown(f"**{LANG_LABEL[lang]}**")
        with st.container(border=True):
            for level in ("basic", "intermediate", "advanced"):
                total = db.q1(
                    "SELECT COUNT(*) c FROM materials WHERE lang=? AND level=?", (lang, level)
                )["c"]
                mastered = db.q1(
                    """SELECT COUNT(*) c FROM materials m JOIN progress p ON p.material_id=m.id
                       WHERE m.lang=? AND m.level=? AND p.interval_stage IN ('H7','H14','mastered')""",
                    (lang, level),
                )["c"]
                pct = mastered / total if total else 0
                st.caption(f"{level.capitalize()} -- {mastered}/{total} dikuasai")
                st.progress(pct)

    st.markdown("**Sesi terakhir**")
    sessions = db.q("SELECT * FROM sessions ORDER BY id DESC LIMIT 5")
    if sessions:
        st.dataframe(
            [
                {
                    "Tanggal": s["date"],
                    "Kartu": s["items_reviewed"],
                    "Avg Keyakinan": round(s["avg_metacog"], 2) if s["avg_metacog"] else None,
                    "Kesulitan": s["session_rating"],
                }
                for s in sessions
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Belum ada sesi yang diselesaikan.")


# ==============================================================================
# HALAMAN 3: PETA KURIKULUM
# ==============================================================================

def page_curriculum():
    st.caption("Pemula -> Menengah -> Mahir, untuk kedua bahasa.")
    for lang, label in (("en", "Bahasa Inggris"), ("zh", "Bahasa Mandarin")):
        st.markdown(f"**{label}**")
        with st.container(border=True):
            for level in ("basic", "intermediate", "advanced"):
                topics = CURRICULUM_MAP[lang][level]
                st.markdown(f"**{level.capitalize()}**")
                st.caption(", ".join(topics))


# ==============================================================================
# HALAMAN 4: REKOMENDASI COURSERA
# ==============================================================================

def page_coursera():
    st.caption(
        "Cek tombol 'Financial Aid' di halaman course/specialization masing-masing "
        "(biasanya muncul setelah klik 'Enroll'). Bisa diajukan untuk semua level sekaligus."
    )
    for lang, label in (("en", "Bahasa Inggris"), ("zh", "Bahasa Mandarin")):
        st.markdown(f"**{label}**")
        for c in COURSERA_TRACKS[lang]:
            with st.container(border=True):
                st.markdown(f"**{c['name']}**")
                st.caption(f"{c['level']} -- {c['provider']}")
                st.markdown(f"[Buka kursus]({c['url']})")


# ==============================================================================
# ROUTER
# ==============================================================================

if page == "Kartu Hari Ini":
    page_session()
elif page == "Kotak Progress":
    page_dashboard()
elif page == "Peta Kurikulum":
    page_curriculum()
elif page == "Rak Kursus":
    page_coursera()
