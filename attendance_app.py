import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from datetime import date

# ---------------- Database Setup ----------------
conn = sqlite3.connect("attendance.db", check_same_thread=False)
c = conn.cursor()

# ---- Migration Fix: Rename 'phone' to 'roll_no' if needed ----
def migrate_db():
    c.execute("PRAGMA table_info(students)")
    cols = [col[1] for col in c.fetchall()]
    if "phone" in cols and "roll_no" not in cols:
        try:
            c.execute("ALTER TABLE students RENAME COLUMN phone TO roll_no;")
            conn.commit()
        except:
            pass

    c.execute("PRAGMA table_info(records)")
    cols = [col[1] for col in c.fetchall()]
    if "phone" in cols and "roll_no" not in cols:
        try:
            c.execute("ALTER TABLE records RENAME COLUMN phone TO roll_no;")
            conn.commit()
        except:
            pass

migrate_db()

# Students table (totals)
c.execute('''CREATE TABLE IF NOT EXISTS students (
                roll_no TEXT PRIMARY KEY,
                total_classes INTEGER,
                attended_classes INTEGER
            )''')

# Records table (daily entries)
c.execute('''CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roll_no TEXT,
                date TEXT,
                total_classes INTEGER,
                attended_classes INTEGER
            )''')
conn.commit()

# ---------------- Functions ----------------
def get_student(roll_no):
    c.execute("SELECT * FROM students WHERE roll_no=?", (roll_no,))
    return c.fetchone()

def add_student(roll_no):
    c.execute("INSERT INTO students VALUES (?, ?, ?)", (roll_no, 0, 0))
    conn.commit()

def get_record_by_id(record_id):
    c.execute("SELECT * FROM records WHERE id=?", (record_id,))
    return c.fetchone()

def update_record(record_id, roll_no, new_total, new_attended):
    record = get_record_by_id(record_id)
    if not record:
        return False
    
    old_total, old_attended = record[3], record[4]

    # Update record
    c.execute("UPDATE records SET total_classes=?, attended_classes=? WHERE id=?",
              (new_total, new_attended, record_id))

    # Adjust student totals
    student = get_student(roll_no)
    total, attended = student[1], student[2]
    total = total - old_total + new_total
    attended = attended - old_attended + new_attended

    c.execute("UPDATE students SET total_classes=?, attended_classes=? WHERE roll_no=?",
              (total, attended, roll_no))
    conn.commit()
    return True

def get_today_record(roll_no):
    today = str(date.today())
    c.execute("SELECT * FROM records WHERE roll_no=? AND date=?", (roll_no, today))
    return c.fetchone()

def add_or_update_today(roll_no, today_total, today_attended):
    today = str(date.today())
    existing = get_today_record(roll_no)

    if existing:  # Update today's
        return update_record(existing[0], roll_no, today_total, today_attended)
    else:  # New record
        c.execute("INSERT INTO records (roll_no, date, total_classes, attended_classes) VALUES (?, ?, ?, ?)",
                  (roll_no, today, today_total, today_attended))

        student = get_student(roll_no)
        total, attended = student[1], student[2]
        total += today_total
        attended += today_attended

        c.execute("UPDATE students SET total_classes=?, attended_classes=? WHERE roll_no=?",
                  (total, attended, roll_no))
        conn.commit()
        return True

def get_records(roll_no):
    df = pd.read_sql_query("SELECT id, date, total_classes, attended_classes FROM records WHERE roll_no=? ORDER BY date DESC", conn, params=(roll_no,))
    return df

# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="Attendance Portal", page_icon="🎓", layout="centered")
st.title("📲 Student Attendance Portal")

roll_no = st.text_input("Enter Roll Number to Login")

if roll_no:
    student = get_student(roll_no)
    if not student:
        st.info("New student detected! Creating your record...")
        add_student(roll_no)
        student = get_student(roll_no)

    st.success(f"Welcome, student with Roll No: {roll_no}")

    # ---------------- Mark/Edit Today's Attendance ----------------
    st.subheader("📌 Mark or Edit Today's Attendance")

    today_record = get_today_record(roll_no)
    if today_record:
        st.info("You already submitted today's attendance. Update it if needed 👇")
        today_total = st.number_input("Total Classes Conducted Today", min_value=0, step=1, value=today_record[3])
        today_attended = st.number_input("Classes You Attended Today", min_value=0, step=1, value=today_record[4])
    else:
        today_total = st.number_input("Total Classes Conducted Today", min_value=0, step=1)
        today_attended = st.number_input("Classes You Attended Today", min_value=0, step=1)

    if st.button("📥 Save Today's Attendance"):
        if today_attended <= today_total:
            add_or_update_today(roll_no, today_total, today_attended)
            st.success("✅ Attendance saved successfully!")
        else:
            st.error("❌ Attended classes cannot exceed total classes.")

    # ---------------- Show Stats ----------------
    student = get_student(roll_no)
    total_classes, attended_classes = student[1], student[2]

    if total_classes > 0:
        percent = (attended_classes / total_classes) * 100

        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=percent,
            title={'text': "Attendance %"},
            gauge={'axis': {'range': [0, 100]},
                   'bar': {'color': "green" if percent >= 75 else "red"}}
        ))
        st.plotly_chart(fig)

        st.metric("📊 Current Attendance", f"{percent:.2f}%")

        required = 75
        if percent >= required:
            st.success("✅ You are SAFE! 🎉")
        else:
            st.error("⚠️ Attendance Shortage!")

            needed = ((required * total_classes) - (100 * attended_classes)) / (100 - required)
            needed = int(needed) + 1
            st.warning(f"You must attend **{needed} more classes** in a row to reach 75%.")
    else:
        st.info("No classes recorded yet.")

    # ---------------- Edit Past Attendance ----------------
    st.subheader("✏️ Edit Past Attendance Records")

    df = get_records(roll_no)
    if not df.empty:
        st.dataframe(df)

        record_id = st.selectbox("Select a record to edit", df["id"])
        if record_id:
            record = get_record_by_id(record_id)
            if record:
                st.write(f"Editing Record for 📅 {record[2]}")

                new_total = st.number_input("Edit Total Classes", min_value=0, step=1, value=record[3], key="edit_total")
                new_attended = st.number_input("Edit Attended Classes", min_value=0, step=1, value=record[4], key="edit_attended")

                if st.button("💾 Save Changes"):
                    if new_attended <= new_total:
                        update_record(record_id, roll_no, new_total, new_attended)
                        st.success("✅ Record updated successfully!")
                    else:
                        st.error("❌ Attended classes cannot exceed total classes.")
    else:
        st.write("No past records yet.")
