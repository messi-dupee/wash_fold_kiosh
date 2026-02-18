import sqlite3
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import subprocess
import threading
from datetime import datetime, timedelta

# ================== PATHS ==================

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
        weight REAL NOT NULL,
        price REAL NOT NULL,
        dropoff_time TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ================== CLEANING ==================

def clean_phone_number(value):
    digits = "".join(filter(str.isdigit, value))
    return digits[:10]

def clean_name(value):
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "
    return "".join(c for c in value if c in allowed)

# ================== PICKUP LOGIC ==================

def calculate_pickup_time(dropoff):
    pickup = dropoff + timedelta(hours=8)

    # Wednesday rule (only once)
    if pickup.weekday() == 2:
        pickup += timedelta(days=1)

    # Morning rule
    if pickup.hour < 12:
        pickup = pickup.replace(hour=12, minute=0, second=0)

    return pickup

# ================== DATABASE LOOKUP ==================

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
               COALESCE(SUM(weight), 0),
               COALESCE(SUM(price), 0)
        FROM entries WHERE number=?
        """,
        (number,)
    )
    visits, total_weight, total_price = cursor.fetchone()

    conn.close()

    return (name_row[0] if name_row else None), visits, total_weight, total_price

# ================== PRINT RECEIPT ==================

def print_receipt(number, name, weight, price, dropoff, pickup):
    c = canvas.Canvas(RECEIPT_FILE, pagesize=A4)
    width, height = A4

    c.setFont("Courier-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "SENTER LAUNDROMAT")

    c.setFont("Courier", 10)
    c.drawCentredString(width / 2, height - 70, "2266 Senter Road")

    y = height - 120
    c.drawString(50, y, f"Drop-Off Time: {dropoff}")
    y -= 18
    c.drawString(50, y, f"Pickup Time:   {pickup}")
    y -= 25

    c.drawString(50, y, f"Phone Number: {number}")
    y -= 18
    c.drawString(50, y, f"Customer Name: {name}")
    y -= 25

    c.drawString(50, y, f"Weight of Clothes (lbs): {weight:.2f}")
    y -= 18
    c.drawString(50, y, f"Price ($): {price:.2f}")

    c.save()

    # subprocess.run(
    #     ["lp", "-d", PRINTER_NAME, RECEIPT_FILE],
    #     stdout=subprocess.PIPE,
    #     stderr=subprocess.PIPE
    # )

# ================== SAVE ENTRY ==================

def save_entry():
    number = clean_phone_number(phone_var.get())
    name = clean_name(name_var.get()).strip()

    if len(number) != 10:
        messagebox.showerror("Error", "Phone number must be exactly 10 digits")
        return

    if not name:
        messagebox.showerror("Error", "Name must contain letters only")
        return

    try:
        weight = float(weight_entry.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid weight")
        return

    price = weight * 1.5

    now = datetime.now()
    pickup_time = calculate_pickup_time(now)

    dropoff_str = now.strftime("%Y-%m-%d %I:%M %p")
    pickup_str = pickup_time.strftime("%Y-%m-%d %I:%M %p")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO entries (number, name, weight, price, dropoff_time) VALUES (?, ?, ?, ?, ?)",
        (number, name, weight, price, dropoff_str)
    )
    conn.commit()
    conn.close()

    threading.Thread(
        target=print_receipt,
        args=(number, name, weight, price, dropoff_str, pickup_str),
        daemon=True
    ).start()

    dropoff_label.config(text=f"Drop-Off: {dropoff_str}")
    pickup_label.config(text=f"Pickup: {pickup_str}")

    phone_var.set("")
    name_var.set("")
    weight_entry.delete(0, tk.END)
    money_var.set("")
    totals_label.config(text="")
    visits_label.config(text="")
    status_label.config(text="")

# ================== AUTO LOOKUP ==================

def on_phone_change(*args):
    cleaned = clean_phone_number(phone_var.get())
    if phone_var.get() != cleaned:
        phone_var.set(cleaned)

    if len(cleaned) == 10:
        name, visits, total_weight, total_price = get_customer_info(cleaned)

        if name:
            name_var.set(name)
            status_label.config(text="")

            totals_label.config(
                text=f"Total Weight: {total_weight:.2f} lbs | Total Price: ${total_price:.2f}",
                fg="blue"
            )

            visits_label.config(
                text=f"Visits: {visits}",
                fg="purple"
            )
        else:
            name_var.set("")
            status_label.config(text="New customer", fg="green")
            totals_label.config(text="")
            visits_label.config(text="")
    else:
        name_var.set("")
        status_label.config(text="")
        totals_label.config(text="")
        visits_label.config(text="")

# ================== LIVE FIELD UPDATES ==================

def on_weight_change(*args):
    try:
        money_var.set(f"{float(weight_var.get()) * 1.5:.2f}")
    except:
        money_var.set("")

def on_name_change(*args):
    cleaned = clean_name(name_var.get())
    if name_var.get() != cleaned:
        name_var.set(cleaned)

# ================== GUI ==================

root = tk.Tk()
root.title("Laundromat Kiosk")
root.geometry("900x820")

frame = tk.Frame(root, padx=30, pady=30)
frame.pack(fill="both", expand=True)

tk.Label(frame, text="Phone Number (10 digits)").pack(anchor="w")
phone_var = tk.StringVar()
phone_var.trace_add("write", on_phone_change)
phone_entry = tk.Entry(frame, width=40, textvariable=phone_var)
phone_entry.pack()

tk.Label(frame, text="Customer Name").pack(anchor="w")
name_var = tk.StringVar()
name_var.trace_add("write", on_name_change)
name_entry = tk.Entry(frame, width=40, textvariable=name_var)
name_entry.pack()

status_label = tk.Label(frame, text="", fg="green")
status_label.pack()

totals_label = tk.Label(frame, text="", fg="blue")
totals_label.pack()

visits_label = tk.Label(frame, text="", fg="purple")
visits_label.pack(pady=(0, 10))

tk.Label(frame, text="Weight of Clothes (lbs)").pack(anchor="w")
weight_var = tk.StringVar()
weight_var.trace_add("write", on_weight_change)
weight_entry = tk.Entry(frame, width=40, textvariable=weight_var)
weight_entry.pack()

tk.Label(frame, text="Price ($)").pack(anchor="w")
money_var = tk.StringVar()
tk.Entry(frame, width=40, textvariable=money_var, state="readonly").pack()

dropoff_label = tk.Label(frame, text="", fg="blue")
dropoff_label.pack()

pickup_label = tk.Label(frame, text="", fg="purple")
pickup_label.pack()

tk.Button(
    frame,
    text="Save Entry & Print Receipt",
    command=save_entry,
    bg="#4CAF50",
    fg="white",
    height=2
).pack(fill="x", pady=20)

root.mainloop()
