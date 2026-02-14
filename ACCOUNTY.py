import sqlite3
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import subprocess
import threading

# ================== PATHS & CONFIG ==================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "store.db"
RECEIPT_FILE = str(BASE_DIR / "receipt_a4.pdf")
PRINTER_NAME = "HP_LaserJet_MFP_M28_M31"

# ================== DATABASE INIT ==================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT NOT NULL,
        name TEXT NOT NULL,
        pounds REAL NOT NULL,
        money REAL NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ================== PHONE CLEANING ==================

def clean_phone_number(value):
    return "".join(filter(str.isdigit, value))

# ================== DATABASE LOOKUPS ==================

def get_customer_info(number):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM entries WHERE number=? ORDER BY id DESC LIMIT 1",
        (number,)
    )
    name_row = cursor.fetchone()

    cursor.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(pounds), 0),
               COALESCE(SUM(money), 0)
        FROM entries WHERE number=?
        """,
        (number,)
    )
    visits, total_weight, total_price = cursor.fetchone()

    conn.close()

    return (name_row[0] if name_row else None), visits, total_weight, total_price

# ================== RECEIPT PRINT ==================

def print_receipt(number, name, weight, price, created_at):
    c = canvas.Canvas(RECEIPT_FILE, pagesize=A4)
    width, height = A4

    c.setFont("Courier-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "SENTER LAUNDROMAT")

    c.setFont("Courier", 10)
    c.drawCentredString(width / 2, height - 70, "2266 Senter Road")

    y = height - 120
    c.drawString(50, y, f"Date: {created_at}")
    y -= 25

    c.drawString(50, y, f"Phone Number: {number}")
    y -= 18
    c.drawString(50, y, f"Customer Name: {name}")
    y -= 25

    c.drawString(50, y, f"Weight of Clothes (lbs): {weight:.2f}")
    y -= 18
    c.drawString(50, y, f"Price ($): {price:.2f}")

    y -= 40
    c.setFont("Courier-Bold", 12)
    c.drawCentredString(width / 2, y, "Thank you for your business!")

    c.save()

    subprocess.run(
        ["lp", "-d", PRINTER_NAME, "-o", "media=A4", RECEIPT_FILE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

# ================== GUI CALLBACKS ==================

def on_phone_change(*args):
    cleaned = clean_phone_number(phone_var.get())
    if phone_var.get() != cleaned:
        phone_var.set(cleaned)

def on_phone_focus_out(event):
    txt = clean_phone_number(phone_var.get())

    if not txt:
        status_label.config(text="")
        totals_label.config(text="")
        visits_label.config(text="")
        return

    name, visits, total_weight, total_price = get_customer_info(txt)

    if name:
        name_entry.delete(0, tk.END)
        name_entry.insert(0, name)
        status_label.config(text="")

        totals_label.config(
            text=f"Total Weight: {total_weight:.2f} lbs | Total Price: ${total_price:.2f}",
            fg="blue"
        )

        visits_label.config(
            text=f"Visits: {visits} time{'s' if visits != 1 else ''}",
            fg="purple"
        )
    else:
        name_entry.delete(0, tk.END)
        status_label.config(text="New customer", fg="green")
        totals_label.config(text="")
        visits_label.config(text="")

def save_entry():
    number = clean_phone_number(phone_var.get())

    if not number:
        messagebox.showerror("Error", "Invalid phone number")
        return

    name = name_entry.get().strip()
    if not name:
        messagebox.showerror("Error", "Name required")
        return

    try:
        weight = float(weight_entry.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid weight")
        return

    price = weight * 1.5

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO entries (number, name, pounds, money) VALUES (?, ?, ?, ?)",
        (number, name, weight, price)
    )
    conn.commit()

    cursor.execute(
        "SELECT created_at FROM entries ORDER BY id DESC LIMIT 1"
    )
    created_at = cursor.fetchone()[0]
    conn.close()

    threading.Thread(
        target=print_receipt,
        args=(number, name, weight, price, created_at),
        daemon=True
    ).start()

    phone_var.set("")
    name_entry.delete(0, tk.END)
    weight_entry.delete(0, tk.END)
    money_var.set("")
    status_label.config(text="")
    totals_label.config(text="")
    visits_label.config(text="")

def on_weight_change(*args):
    try:
        money_var.set(f"{float(weight_var.get()) * 1.5:.2f}")
    except:
        money_var.set("")

# ================== GUI ==================

root = tk.Tk()
root.title("Laundromat Kiosk")
root.geometry("900x780")

frame = tk.Frame(root, padx=30, pady=30)
frame.pack(fill="both", expand=True)

tk.Label(frame, text="Phone Number").pack(anchor="w")
phone_var = tk.StringVar()
phone_var.trace_add("write", on_phone_change)
phone_entry = tk.Entry(frame, width=40, textvariable=phone_var)
phone_entry.pack()
phone_entry.bind("<FocusOut>", on_phone_focus_out)

tk.Label(frame, text="Customer Name").pack(anchor="w")
name_entry = tk.Entry(frame, width=40)
name_entry.pack()

status_label = tk.Label(frame, text="", fg="green")
status_label.pack(anchor="w")

totals_label = tk.Label(frame, text="", fg="blue")
totals_label.pack(anchor="w")

visits_label = tk.Label(frame, text="", fg="purple")
visits_label.pack(anchor="w", pady=(0, 15))

tk.Label(frame, text="Weight of Clothes (lbs)").pack(anchor="w")
weight_var = tk.StringVar()
weight_var.trace_add("write", on_weight_change)
weight_entry = tk.Entry(frame, width=40, textvariable=weight_var)
weight_entry.pack()

tk.Label(frame, text="Price ($)").pack(anchor="w")
money_var = tk.StringVar()
tk.Entry(frame, width=40, textvariable=money_var, state="readonly").pack()

tk.Button(
    frame,
    text="Save Entry & Print Receipt",
    command=save_entry,
    bg="#4CAF50",
    fg="white",
    height=2
).pack(fill="x", pady=20)

root.mainloop()
                          