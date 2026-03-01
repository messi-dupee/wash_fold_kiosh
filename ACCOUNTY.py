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

    if pickup.weekday() == 2:  # Wednesday
        pickup += timedelta(days=1)

    if pickup.hour < 12:
        pickup = pickup.replace(hour=12, minute=0, second=0)

    return pickup

# ================== ORDER NUMBER ==================

def get_today_order_number():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM entries WHERE dropoff_time LIKE ?",
        (today + "%",)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count + 1

# ================== CUSTOMER LOOKUP ==================

def get_customer_info(number):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM entries WHERE number=? ORDER BY id DESC LIMIT 1",
        (number,)
    )
    name_row = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*),
               COALESCE(SUM(weight), 0),
               COALESCE(SUM(price), 0)
        FROM entries WHERE number=?
    """, (number,))
    visits, total_weight, total_price = cursor.fetchone()

    conn.close()
    return (name_row[0] if name_row else None), visits, total_weight, total_price

# ================== PRINT RECEIPT ==================

def print_receipt(order_number, number, name, weight, price, dropoff, pickup):
    c = canvas.Canvas(RECEIPT_FILE, pagesize=A4)
    width, height = A4

    c.setFont("Courier-Bold", 18)
    c.drawCentredString(width / 2, height - 50, "SENTER LAUNDROMAT")
    c.drawCentredString(width / 2, height - 75, f"ORDER #{order_number}")

    c.setFont("Courier", 12)

    y = height - 120
    c.drawString(50, y, f"Drop-Off Time: {dropoff}")
    y -= 22
    c.drawString(50, y, f"Pickup Time: {pickup}")
    y -= 30

    c.drawString(50, y, f"Phone Number: {number}")
    y -= 22
    c.drawString(50, y, f"Customer Name: {name}")
    y -= 30

    c.drawString(50, y, f"Weight (lbs): {weight:.2f}")
    y -= 22
    c.drawString(50, y, f"Price ($): {price:.2f}")

    c.save()

    subprocess.run(
        ["lp", "-d", PRINTER_NAME, RECEIPT_FILE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

# ================== SAVE ENTRY ==================

def save_entry():
    number = clean_phone_number(phone_var.get())
    name = clean_name(name_var.get()).strip()

    if len(number) != 10:
        messagebox.showerror("Error", "Phone number must be 10 digits")
        return

    if not name:
        messagebox.showerror("Error", "Invalid name")
        return

    try:
        weight = float(weight_var.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid weight")
        return

    price = weight * 1.5
    now = datetime.now()
    pickup_time = calculate_pickup_time(now)
    order_number = get_today_order_number()

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
        args=(order_number, number, name, weight, price, dropoff_str, pickup_str),
        daemon=True
    ).start()

    order_label.config(text=f"{translations[current_language]['order']}: {order_number}")
    dropoff_label.config(text=f"Drop-Off: {dropoff_str}")
    pickup_label.config(text=f"Pickup: {pickup_str}")

    phone_var.set("")
    name_var.set("")
    weight_var.set("")
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
                text=f"{translations[current_language]['total_weight']}: {total_weight:.2f} lbs | "
                     f"{translations[current_language]['total_price']}: ${total_price:.2f}",
                fg="blue"
            )
            visits_label.config(
                text=f"{translations[current_language]['visits']}: {visits}",
                fg="purple"
            )
        else:
            name_var.set("")
            status_label.config(
                text=translations[current_language]["new_customer"],
                fg="green"
            )
            totals_label.config(text="")
            visits_label.config(text="")
    else:
        name_var.set("")
        status_label.config(text="")
        totals_label.config(text="")
        visits_label.config(text="")

# ================== LANGUAGE SYSTEM ==================

current_language = "en"

translations = {
    "en": {
        "phone": "Phone Number (10 digits)",
        "name": "Customer Name",
        "weight": "Weight of Clothes (lbs)",
        "price": "Price ($)",
        "new_customer": "New Customer",
        "visits": "Visits",
        "total_weight": "Total Weight",
        "total_price": "Total Price",
        "save": "SAVE ENTRY & PRINT RECEIPT",
        "order": "Order Number",
        "language_button": "Switch to Vietnamese"
    },
    "vi": {
        "phone": "Số Điện Thoại (10 số)",
        "name": "Tên Khách Hàng",
        "weight": "Cân Nặng Quần Áo (lbs)",
        "price": "Giá ($)",
        "new_customer": "Khách Mới",
        "visits": "Số Lần",
        "total_weight": "Tổng Cân",
        "total_price": "Tổng Tiền",
        "save": "LƯU & IN HÓA ĐƠN",
        "order": "Số Đơn Hàng",
        "language_button": "Switch to English"
    }
}

def update_language():
    t = translations[current_language]
    phone_label.config(text=t["phone"])
    name_label.config(text=t["name"])
    weight_label.config(text=t["weight"])
    price_label.config(text=t["price"])
    save_button.config(text=t["save"])
    language_button.config(text=t["language_button"])

def toggle_language():
    global current_language
    current_language = "vi" if current_language == "en" else "en"
    update_language()

# ================== GUI (ALIGNED GRID LAYOUT) ==================

root = tk.Tk()
root.title("Laundromat Kiosk")
root.geometry("1000x900")

BIG = ("Arial", 22)
ENTRY = ("Arial", 24)
BOLD = ("Arial", 26, "bold")

frame = tk.Frame(root, padx=60, pady=40)
frame.pack(fill="both", expand=True)

frame.columnconfigure(0, weight=1)
frame.columnconfigure(1, weight=2)

language_button = tk.Button(frame, font=("Arial", 16), command=toggle_language)
language_button.grid(row=0, column=1, sticky="e", pady=(0,20))

# Phone
phone_label = tk.Label(frame, font=BIG)
phone_label.grid(row=1, column=0, sticky="w", pady=10)

phone_var = tk.StringVar()
phone_var.trace_add("write", on_phone_change)
phone_entry = tk.Entry(frame, font=ENTRY, textvariable=phone_var)
phone_entry.grid(row=1, column=1, sticky="ew", pady=10, ipady=10)

# Name
name_label = tk.Label(frame, font=BIG)
name_label.grid(row=2, column=0, sticky="w", pady=10)

name_var = tk.StringVar()
name_entry = tk.Entry(frame, font=ENTRY, textvariable=name_var)
name_entry.grid(row=2, column=1, sticky="ew", pady=10, ipady=10)

status_label = tk.Label(frame, text="", font=BOLD, fg="green")
status_label.grid(row=3, column=0, columnspan=2, pady=10)

totals_label = tk.Label(frame, text="", font=BIG, fg="blue")
totals_label.grid(row=4, column=0, columnspan=2)

visits_label = tk.Label(frame, text="", font=BIG, fg="purple")
visits_label.grid(row=5, column=0, columnspan=2, pady=(0,15))

# Weight
weight_label = tk.Label(frame, font=BIG)
weight_label.grid(row=6, column=0, sticky="w", pady=10)

weight_var = tk.StringVar()
weight_var.trace_add("write", lambda *args:
    money_var.set(f"{float(weight_var.get())*1.5:.2f}")
    if weight_var.get().replace('.', '', 1).isdigit()
    else money_var.set("")
)

weight_entry = tk.Entry(frame, font=ENTRY, textvariable=weight_var)
weight_entry.grid(row=6, column=1, sticky="ew", pady=10, ipady=10)

# Price
price_label = tk.Label(frame, font=BIG)
price_label.grid(row=7, column=0, sticky="w", pady=10)

money_var = tk.StringVar()
price_entry = tk.Entry(frame, font=ENTRY, textvariable=money_var, state="readonly")
price_entry.grid(row=7, column=1, sticky="ew", pady=10, ipady=10)

order_label = tk.Label(frame, text="", font=BOLD, fg="red")
order_label.grid(row=8, column=0, columnspan=2, pady=15)

dropoff_label = tk.Label(frame, text="", font=BIG, fg="blue")
dropoff_label.grid(row=9, column=0, columnspan=2)

pickup_label = tk.Label(frame, text="", font=BIG, fg="purple")
pickup_label.grid(row=10, column=0, columnspan=2)

save_button = tk.Button(
    frame,
    font=("Arial", 24, "bold"),
    bg="#4CAF50",
    fg="white",
    height=2,
    command=save_entry
)
save_button.grid(row=11, column=0, columnspan=2, sticky="ew", pady=30)

update_language()
root.mainloop()