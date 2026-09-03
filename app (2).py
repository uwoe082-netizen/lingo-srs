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

st.set_page_config(page_title="Lingo-SRS", page_icon="📚", layout="centered")


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
# SIDEBAR NAVIGASI
# ==============================================================================

st.sidebar.title("📚 Lingo-SRS")
page = st.sidebar.radio(
    "Menu",
    ["Sesi Belajar Hari Ini", "Dashboard Progress", "Peta Kurikulum", "Rekomendasi Coursera"],
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


def page_session():
    st.header("Sesi Retrieval Practice")
    st.caption(
        "Soal hari ini otomatis dicampur (interleaved) antara Bahasa Inggris & Mandarin, "
        "grammar & vocab, materi baru & materi yang jatuh tempo direview."
    )

    if st.session_state.stage == "idle":
        if st.button("🚀 Mulai Sesi Hari Ini", type="primary"):
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
        f"**{LANG_LABEL[item['lang']]}**  |  {item['level'].upper()}  |  "
        f"{TYPE_LABEL[item['item_type']]}  |  topik: `{item['topic']}`"
    )
    st.subheader(item["prompt"])
    if item["hint"]:
        st.caption(f"💡 hint: {item['hint']}")

    if st.session_state.stage == "answering":
        with st.form(key=f"answer_form_{idx}"):
            user_answer = st.text_input("Jawaban Anda", key=f"input_{idx}")
            submitted = st.form_submit_button("Kirim Jawaban")
        if submitted:
            correct = _check_answer(user_answer, item["answer"])
            st.session_state.last_correct = correct
            st.session_state.last_user_answer = user_answer
            st.session_state.stage = "feedback"
            st.rerun()

    elif st.session_state.stage == "feedback":
        if st.session_state.last_correct:
            st.success("✅ Benar!")
        else:
            st.error(f"❌ Kurang tepat. Jawaban benar: **{item['answer']}**")

        st.markdown("**Seberapa yakin Anda dengan jawaban tadi? (metakognisi)**")
        st.caption(
            "1 = Lupa total / menebak   ·   2 = Ingat tapi ragu-ragu   ·   "
            "3 = Ingat, cukup yakin   ·   4 = Sangat yakin / mudah"
        )
        cols = st.columns(4)
        labels = ["1 - Lupa total", "2 - Ragu-ragu", "3 - Cukup yakin", "4 - Sangat yakin"]
        for i, col in enumerate(cols, start=1):
            if col.button(labels[i - 1], key=f"metacog_{idx}_{i}"):
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
    st.session_state._last_schedule_note = f"Dijadwalkan ulang: {new_stage} (tanggal {next_review.isoformat()})"
    st.session_state.current_idx += 1
    st.session_state.stage = "answering" if st.session_state.current_idx < len(st.session_state.session_items) else "done"


def _finish_session():
    scores = st.session_state.metacog_scores
    avg = sum(scores) / len(scores) if scores else 0

    st.success("🎉 Sesi selesai!")
    st.metric("Rata-rata metakognisi", f"{avg:.2f} / 4")

    st.markdown("**Secara keseluruhan, seberapa menantang sesi hari ini?**")
    cols = st.columns(4)
    labels = ["1 - Terlalu mudah", "2 - Cukup mudah", "3 - Menantang", "4 - Sangat menantang"]
    for i, col in enumerate(cols, start=1):
        if col.button(labels[i - 1], key=f"session_rating_{i}"):
            db.exec(
                "UPDATE sessions SET items_reviewed=?, avg_metacog=?, session_rating=? WHERE id=?",
                (len(st.session_state.session_items), avg, i, st.session_state.session_id),
            )
            st.session_state.stage = "idle"
            st.session_state.session_items = None
            st.rerun()

    st.info(
        "Materi yang salah/skornya rendah otomatis dijadwalkan H+1 supaya diulang besok "
        "(spaced repetition). Klik salah satu tombol di atas untuk menyimpan sesi."
    )


# ==============================================================================
# HALAMAN 2: DASHBOARD PROGRESS
# ==============================================================================

def page_dashboard():
    st.header("Dashboard Progress")

    for lang in ("en", "zh"):
        st.subheader(LANG_LABEL[lang])
        rows = []
        for level in ("basic", "intermediate", "advanced"):
            total = db.q1(
                "SELECT COUNT(*) c FROM materials WHERE lang=? AND level=?", (lang, level)
            )["c"]
            mastered = db.q1(
                """SELECT COUNT(*) c FROM materials m JOIN progress p ON p.material_id=m.id
                   WHERE m.lang=? AND m.level=? AND p.interval_stage IN ('H7','H14','mastered')""",
                (lang, level),
            )["c"]
            rows.append({"Level": level, "Dikuasai (H7+/mastered)": mastered, "Total materi": total})
        st.dataframe(rows, hide_index=True, use_container_width=True)

    due_today = db.q1(
        "SELECT COUNT(*) c FROM progress WHERE next_review <= ?",
        (datetime.date.today().isoformat(),),
    )["c"]
    st.metric("Materi jatuh tempo (due) untuk direview hari ini", due_today)

    st.subheader("5 Sesi Terakhir")
    sessions = db.q("SELECT * FROM sessions ORDER BY id DESC LIMIT 5")
    if sessions:
        st.dataframe(
            [
                {
                    "Tanggal": s["date"],
                    "Jumlah Soal": s["items_reviewed"],
                    "Avg Metakognisi": round(s["avg_metacog"], 2) if s["avg_metacog"] else None,
                    "Kesulitan Sesi": s["session_rating"],
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
    st.header("Peta Kurikulum (Pemula -> Menengah -> Mahir)")
    for lang, label in (("en", "🇬🇧 Bahasa Inggris"), ("zh", "🇨🇳 Bahasa Mandarin")):
        st.subheader(label)
        for level in ("basic", "intermediate", "advanced"):
            topics = CURRICULUM_MAP[lang][level]
            st.markdown(f"**{level.upper()}**: {', '.join(topics)}")


# ==============================================================================
# HALAMAN 4: REKOMENDASI COURSERA
# ==============================================================================

def page_coursera():
    st.header("Rekomendasi Jalur Coursera (Financial Aid)")
    st.caption(
        "Cek tombol 'Financial Aid' di halaman course/specialization masing-masing "
        "(biasanya muncul setelah klik 'Enroll'). Bisa diajukan untuk semua level sekaligus."
    )
    for lang, label in (("en", "🇬🇧 Bahasa Inggris"), ("zh", "🇨🇳 Bahasa Mandarin")):
        st.subheader(label)
        for c in COURSERA_TRACKS[lang]:
            st.markdown(f"**[{c['level']}] {c['name']}**  \nPenyedia: {c['provider']}  \n{c['url']}")


# ==============================================================================
# ROUTER
# ==============================================================================

if page == "Sesi Belajar Hari Ini":
    page_session()
elif page == "Dashboard Progress":
    page_dashboard()
elif page == "Peta Kurikulum":
    page_curriculum()
elif page == "Rekomendasi Coursera":
    page_coursera()
