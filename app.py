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
TOKEN DESAIN (dipakai di blok CSS di bawah -- ubah di satu tempat ini kalau
mau ganti nuansa warna/tipografi ke depannya):

  Warna dasar     : #FAF7FF (putih keunguan lembut)
  Teks utama      : #241934 (plum gelap)
  Gradasi utama   : #6C3CE9 -> #FF5DA2 (violet ke pink) -- dipakai di hero
                    sesi belajar & tombol CTA utama, sengaja HANYA di dua
                    tempat itu supaya tetap terasa istimewa, bukan dekorasi
                    di mana-mana.
  Sukses/benar    : #2EC4B6 (teal)
  Perlu perhatian : #FF6B6B (coral) -- salah jawab / due review
  Tipografi       : Poppins untuk headline (tegas, sedikit playful),
                    Inter untuk isi/label (netral, gampang dibaca)
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

st.set_page_config(page_title="Lingo-SRS", page_icon="\U0001F4DA", layout="centered")


# ==============================================================================
# CSS GLOBAL -- satu-satunya tempat yang mengatur seluruh nuansa visual
# ==============================================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600;700&family=Inter:wght@400;500;600&display=swap');

    :root {
        --bg: #FAF7FF;
        --ink: #241934;
        --ink-soft: #6B6178;
        --violet: #6C3CE9;
        --pink: #FF5DA2;
        --teal: #2EC4B6;
        --coral: #FF6B6B;
        --card: #FFFFFF;
        --card-border: #EDE6FB;
    }

    /* Sembunyikan chrome bawaan Streamlit yang tidak relevan untuk app harian */
    #MainMenu, footer, header {visibility: hidden;}

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: var(--ink);
    }
    .stApp { background: var(--bg); }

    h1, h2, h3 { font-family: 'Poppins', sans-serif; letter-spacing: -0.01em; }

    .block-container { padding-top: 1.6rem; padding-bottom: 4rem; max-width: 640px; }

    /* Brand mark di atas tiap halaman */
    .lsrs-brand {
        font-family: 'Poppins', sans-serif;
        font-weight: 700;
        font-size: 1.3rem;
        margin-bottom: 0.2rem;
    }
    .lsrs-brand span { color: var(--pink); }

    /* Hero gradasi -- satu-satunya tempat gradasi dipakai besar-besaran */
    .lsrs-hero {
        background: linear-gradient(135deg, var(--violet), var(--pink));
        border-radius: 24px;
        padding: 28px 24px;
        color: white;
        margin-bottom: 20px;
    }
    .lsrs-hero h2 {
        color: white;
        font-size: 1.6rem;
        margin: 0 0 6px 0;
    }
    .lsrs-hero p {
        color: rgba(255,255,255,0.85);
        font-size: 0.92rem;
        margin: 0 0 16px 0;
        line-height: 1.5;
    }

    /* Badge pil kecil untuk tag kategori (bahasa/tipe/level) */
    .lsrs-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 500;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .lsrs-badge-light { background: rgba(255,255,255,0.22); color: white; }
    .lsrs-badge-tint  { background: var(--card-border); color: var(--violet); }

    /* Kartu statistik ringkas */
    .lsrs-stat {
        background: var(--card);
        border: 1px solid var(--card-border);
        border-radius: 18px;
        padding: 16px 18px;
        margin-bottom: 12px;
    }
    .lsrs-stat .num { font-family: 'Poppins', sans-serif; font-size: 1.6rem; font-weight: 700; }
    .lsrs-stat .lbl { color: var(--ink-soft); font-size: 0.85rem; }

    /* Tombol utama jadi pil gradasi */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, var(--violet), var(--pink));
        border: none;
        border-radius: 999px;
        padding: 0.6rem 1.4rem;
        font-weight: 600;
        box-shadow: 0 6px 16px rgba(108, 60, 233, 0.25);
    }
    div[data-testid="stButton"] > button[kind="secondary"] {
        border-radius: 999px;
        border: 1px solid var(--card-border);
        font-weight: 500;
    }

    /* Segmented nav (menggantikan sidebar) */
    div[role="radiogroup"] {
        display: flex;
        gap: 6px;
        background: var(--card-border);
        padding: 4px;
        border-radius: 999px;
        margin-bottom: 18px;
    }
    div[role="radiogroup"] label {
        flex: 1;
        text-align: center;
        border-radius: 999px !important;
        padding: 6px 4px !important;
        font-size: 0.8rem;
    }
    div[role="radiogroup"] label div:first-child { display: none; } /* sembunyikan bulatan radio asli */

    /* Progress bar jadi lebih tebal & bulat */
    div[data-testid="stProgress"] > div > div > div {
        background: linear-gradient(90deg, var(--violet), var(--pink));
        border-radius: 999px;
    }

    /* Kartu bordered bawaan Streamlit (st.container(border=True)) dipercantik */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 18px !important;
        border-color: var(--card-border) !important;
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

    # State untuk sesi belajar yang sedang berjalan
    st.session_state.setdefault("session_items", None)   # list soal hari ini
    st.session_state.setdefault("session_id", None)       # id baris di tabel sessions
    st.session_state.setdefault("current_idx", 0)         # soal ke berapa
    st.session_state.setdefault("stage", "idle")          # idle | answering | feedback | done
    st.session_state.setdefault("last_correct", None)
    st.session_state.setdefault("metacog_scores", [])


init_state()
db = st.session_state.db
srs = st.session_state.srs
interleaver = st.session_state.interleaver


# ==============================================================================
# BRAND MARK + NAVIGASI (segmented control di bagian atas, bukan sidebar)
# ==============================================================================

st.markdown('<div class="lsrs-brand">Lingo-<span>SRS</span></div>', unsafe_allow_html=True)

page = st.radio(
    "Menu",
    ["Beranda", "Progress", "Kurikulum", "Kursus"],
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
        st.markdown(
            f"""
            <div class="lsrs-hero">
                <h2>Mulai sesi hari ini</h2>
                <p>{due} materi jatuh tempo. Campur Inggris & Mandarin biar otakmu
                tetap waspada -- variasi ini disengaja, bukan acak.</p>
                <span class="lsrs-badge lsrs-badge-light">Kosakata</span>
                <span class="lsrs-badge lsrs-badge-light">Tata bahasa</span>
                <span class="lsrs-badge lsrs-badge-light">Nada (ZH)</span>
                <span class="lsrs-badge lsrs-badge-light">Terjemahan</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Mulai Sesi Hari Ini", type="primary"):
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

    st.progress((idx) / total, text=f"Soal {idx + 1} dari {total}")

    st.markdown(
        f"""
        <span class="lsrs-badge lsrs-badge-tint">{LANG_LABEL[item['lang']]}</span>
        <span class="lsrs-badge lsrs-badge-tint">{item['level'].capitalize()}</span>
        <span class="lsrs-badge lsrs-badge-tint">{TYPE_LABEL[item['item_type']]}</span>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.subheader(item["prompt"])
        if item["hint"]:
            st.caption(f"Hint: {item['hint']}")

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
            st.caption(
                "1 Lupa total  ·  2 Ragu-ragu  ·  3 Cukup yakin  ·  4 Sangat yakin"
            )
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
    st.session_state._last_schedule_note = f"Direview lagi: {new_stage} ({next_review.isoformat()})"
    st.session_state.current_idx += 1
    st.session_state.stage = "answering" if st.session_state.current_idx < len(st.session_state.session_items) else "done"


def _finish_session():
    scores = st.session_state.metacog_scores
    avg = sum(scores) / len(scores) if scores else 0

    st.markdown(
        f"""
        <div class="lsrs-hero">
            <h2>Sesi selesai!</h2>
            <p>Rata-rata keyakinan diri kamu: {avg:.2f} dari 4.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
        "Materi yang salah/skornya rendah otomatis dijadwalkan ulang lebih cepat "
        "(spaced repetition). Pilih salah satu tingkat kesulitan di atas untuk menyimpan sesi."
    )


# ==============================================================================
# HALAMAN 2: DASHBOARD PROGRESS
# ==============================================================================

def page_dashboard():
    st.markdown("### Progress kamu")

    due = _due_today_count()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'<div class="lsrs-stat"><div class="num">{due}</div>'
            f'<div class="lbl">Jatuh tempo hari ini</div></div>',
            unsafe_allow_html=True,
        )

    total_sessions = db.q1("SELECT COUNT(*) c FROM sessions")["c"]
    with c2:
        st.markdown(
            f'<div class="lsrs-stat"><div class="num">{total_sessions}</div>'
            f'<div class="lbl">Total sesi selesai</div></div>',
            unsafe_allow_html=True,
        )

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
                    "Soal": s["items_reviewed"],
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
    st.markdown("### Peta kurikulum")
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
    st.markdown("### Rekomendasi kursus (Financial Aid)")
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

if page == "Beranda":
    page_session()
elif page == "Progress":
    page_dashboard()
elif page == "Kurikulum":
    page_curriculum()
elif page == "Kursus":
    page_coursera()
