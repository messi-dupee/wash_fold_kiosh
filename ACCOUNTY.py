# ==========================================================
# LAUNDROMAT KIOSK SYSTEM
# PART 1 — FOUNDATION
# ==========================================================

import sqlite3
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import subprocess
import threading
from datetime import datetime, timedelta


# ==========================================================
# PATH CONFIGURATION
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "store.db"
RECEIPT_FILE = str(BASE_DIR / "receipt_a4.pdf")

PRINTER_NAME = "POS-80"


# ==========================================================
# PRICE CONFIGURATION
# ==========================================================

BASE_RATE = 1.5

SEPARATE_MULTIPLIER = 1.10
EXPRESS_MULTIPLIER = 1.15

QUEEN_PRICE = 20
KING_PRICE = 25


# ==========================================================
# GLOBAL STATE
# ==========================================================

loaded_order_id = None
last_order_cache = None


# ==========================================================
# LANGUAGE SYSTEM
# ==========================================================

current_language = "en"

translations = {

"en":{
"phone":"Phone",
"name":"Name",
"weight":"Weight",
"separate":"Separate Whites (+10%)",
"express":"Express (+15%)",
"queen":"Queen Comforter",
"king":"King Comforter",
"price":"Price",
"copies":"Copies",
"save":"SAVE ENTRY & PRINT RECEIPT",
"dashboard":"DAILY DASHBOARD",
"reprint":"REPRINT LAST RECEIPT",
"lookup":"Find Order #"
},

"vi":{
"phone":"Số Điện Thoại",
"name":"Tên Khách",
"weight":"Cân Nặng",
"separate":"Giặt Riêng (+10%)",
"express":"Nhanh (+15%)",
"queen":"Mền Queen",
"king":"Mền King",
"price":"Giá",
"copies":"Số Bản In",
"save":"LƯU & IN HÓA ĐƠN",
"dashboard":"BẢNG DOANH THU",
"reprint":"IN LẠI HÓA ĐƠN",
"lookup":"Tìm Số Đơn"
}

}


# ==========================================================
# DATABASE INITIALIZATION
# ==========================================================

def init_db():

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS entries(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        number TEXT,
        name TEXT,

        weight REAL,

        queen_qty INTEGER,
        king_qty INTEGER,

        price REAL,

        separate INTEGER,
        express INTEGER,

        dropoff_time TEXT

    )
    """)

    conn.commit()
    conn.close()


init_db()


# ==========================================================
# INPUT CLEANING
# ==========================================================

def clean_phone_number(value):

    digits = "".join(filter(str.isdigit,value))

    return digits[:10]


def clean_name(value):

    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "

    return "".join(c for c in value if c in allowed)


# ==========================================================
# PICKUP TIME RULES
# ==========================================================

def calculate_pickup_time(dropoff,express):

    # RULE 1
    pickup = dropoff + timedelta(hours = 4 if express else 8)

    # RULE 2
    if pickup.time() > datetime.strptime("20:00","%H:%M").time():
        pickup += timedelta(hours = 11)

    # RULE 3
    if pickup.hour < 12:
        pickup = pickup.replace(hour=12,minute=0,second=0,microsecond=0)

    # RULE 4
    if pickup.weekday() == 2:
        pickup += timedelta(days=1)

    return pickup


# ==========================================================
# PRICE ENGINE
# ==========================================================

def calculate_price(weight,separate,express,queen_qty,king_qty):

    rate = BASE_RATE

    if separate:
        rate *= SEPARATE_MULTIPLIER

    if express:
        rate *= EXPRESS_MULTIPLIER

    laundry_cost = weight * rate

    queen_cost = queen_qty * QUEEN_PRICE
    king_cost = king_qty * KING_PRICE

    total = laundry_cost + queen_cost + king_cost

    return rate,laundry_cost,queen_cost,king_cost,total

# ==========================================================
# RECEIPT BUILDER
# ==========================================================

def build_receipt(order,number,name,weight,rate,
                  queen_qty,king_qty,total,
                  drop,pick,separate,express):

    c = canvas.Canvas(RECEIPT_FILE,pagesize=A4)

    width,height = A4

    x = 50
    y = height - 200

    c.setFont("Courier-Bold",40)
    c.drawCentredString(width/2,height-60,"SENTER LAUNDROMAT")

    c.setFont("Courier-Bold",30)
    c.drawCentredString(width/2,height-110,f"ORDER #{order}")

    c.setFont("Courier",26)

    c.drawString(x,y,f"DROP: {drop}")
    y -= 40

    c.drawString(x,y,f"PICKUP: {pick}")
    y -= 60

    c.drawString(x,y,f"Phone: {number}")
    y -= 40

    c.drawString(x,y,f"Name: {name}")
    y -= 60

    laundry = weight * rate

    c.drawString(x,y,f"Laundry {weight:.2f} lb")
    c.drawRightString(width-50,y,f"${laundry:.2f}")
    y -= 40

    if separate:
        c.drawString(x,y,"Separate Whites (+10%)")
        y -= 30

    if express:
        c.drawString(x,y,"Express (+15%)")
        y -= 30

    if queen_qty > 0:
        c.drawString(x,y,f"Queen Comforter x{queen_qty}")
        c.drawRightString(width-50,y,f"${queen_qty * QUEEN_PRICE:.2f}")
        y -= 40

    if king_qty > 0:
        c.drawString(x,y,f"King Comforter x{king_qty}")
        c.drawRightString(width-50,y,f"${king_qty * KING_PRICE:.2f}")
        y -= 40

    c.line(x,y,width-50,y)
    y -= 40

    c.setFont("Courier-Bold",28)

    c.drawString(x,y,"TOTAL")
    c.drawRightString(width-50,y,f"${total:.2f}")

    c.save()


# ==========================================================
# PRINT RECEIPT
# ==========================================================

def print_receipt(order,number,name,weight,rate,
                  queen_qty,king_qty,total,
                  drop,pick,copies,
                  separate,express):

    global last_order_cache

    build_receipt(order,number,name,weight,rate,
                  queen_qty,king_qty,total,
                  drop,pick,separate,express)

    for i in range(copies):

        subprocess.run(
            ["lp","-d",PRINTER_NAME,RECEIPT_FILE]
        )

    last_order_cache = (
        order,number,name,weight,rate,
        queen_qty,king_qty,total,
        drop,pick,copies,separate,express
    )


# ==========================================================
# REPRINT LAST RECEIPT
# ==========================================================

def reprint_last_receipt():

    global last_order_cache

    if last_order_cache is None:

        messagebox.showerror(
            "Error",
            "No receipt available to reprint"
        )

        return

    print_receipt(*last_order_cache)


# ==========================================================
# CUSTOMER LOOKUP
# ==========================================================

def get_customer_info(number):

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "SELECT name FROM entries WHERE number=? ORDER BY id DESC LIMIT 1",
        (number,)
    )

    name_row = c.fetchone()

    c.execute("""
        SELECT COUNT(*),
               COALESCE(SUM(weight),0),
               COALESCE(SUM(price),0)
        FROM entries
        WHERE number=?
    """,(number,))

    visits,total_weight,total_price = c.fetchone()

    conn.close()

    return (
        name_row[0] if name_row else None,
        visits,
        total_weight,
        total_price
    )


# ==========================================================
# PHONE AUTOFILL
# ==========================================================

def on_phone_change(*args):

    number = clean_phone_number(phone_var.get())

    if phone_var.get() != number:
        phone_var.set(number)

    if len(number) == 10:

        name,visits,total_weight,total_price = get_customer_info(number)

        if name:

            name_var.set(name)

            totals_label.config(
                text=f"Total Weight: {total_weight:.2f} lbs | Total Price: ${total_price:.2f}",
                fg="blue"
            )

            visits_label.config(
                text=f"Visits: {visits}",
                fg="purple"
            )

            status_label.config(text="")

        else:

            status_label.config(
                text="New Customer",
                fg="green"
            )


# ==========================================================
# ORDER LOOKUP
# ==========================================================

def load_order(*args):

    global loaded_order_id

    order = order_lookup_var.get()

    if order == "":
        loaded_order_id = None
        return

    if not order.isdigit():
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT number,name,weight,queen_qty,king_qty,price,separate,express
        FROM entries
        WHERE id=?
    """,(int(order),))

    row = c.fetchone()

    conn.close()

    if row:

        number,name,weight,queen,king,price,separate,express = row

        phone_var.set(number)
        name_var.set(name)
        weight_var.set(str(weight))

        queen_qty.set(queen)
        king_qty.set(king)

        separate_var.set(bool(separate))
        express_var.set(bool(express))

        money_var.set(f"{price:.2f}")

        loaded_order_id = int(order)

        order_label.config(text=f"Loaded Order #{order}")

# ==========================================================
# PRICE UPDATE
# ==========================================================

def update_price(*args):

    try:
        weight = float(weight_var.get())
    except:
        weight = 0

    rate,laundry,queen_cost,king_cost,total = calculate_price(
        weight,
        separate_var.get(),
        express_var.get(),
        queen_qty.get(),
        king_qty.get()
    )

    money_var.set(f"{total:.2f}")


# ==========================================================
# COMFORTER BUTTONS
# ==========================================================

def change_queen(delta):

    q = queen_qty.get() + delta

    if q < 0:
        q = 0

    queen_qty.set(q)

    update_price()


def change_king(delta):

    k = king_qty.get() + delta

    if k < 0:
        k = 0

    king_qty.set(k)

    update_price()


# ==========================================================
# SAVE ENTRY
# ==========================================================

# ==========================================================
# SAVE ENTRY
# ==========================================================

def save_entry():

    global loaded_order_id

    number = clean_phone_number(phone_var.get())
    name = clean_name(name_var.get())

    try:
        weight = float(weight_var.get())
    except:
        messagebox.showerror("Error","Invalid weight")
        return

    rate,laundry,queen_cost,king_cost,total = calculate_price(
        weight,
        separate_var.get(),
        express_var.get(),
        queen_qty.get(),
        king_qty.get()
    )

    now = datetime.now()

    pickup = calculate_pickup_time(now,express_var.get())

    drop_db = now.strftime("%Y-%m-%d %H:%M:%S")

    drop = now.strftime("%m/%d %I:%M %p")
    pick = pickup.strftime("%m/%d %I:%M %p")

    copies = min(10,max(1,int(copies_text.get())))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ----------------------------------
    # UPDATE EXISTING ORDER
    # ----------------------------------

    if loaded_order_id:

        c.execute("""
        UPDATE entries
        SET number=?,
            name=?,
            weight=?,
            queen_qty=?,
            king_qty=?,
            price=?,
            separate=?,
            express=?
        WHERE id=?
        """,(
            number,
            name,
            weight,
            queen_qty.get(),
            king_qty.get(),
            total,
            separate_var.get(),
            express_var.get(),
            loaded_order_id
        ))

        order = loaded_order_id

    # ----------------------------------
    # CREATE NEW ORDER
    # ----------------------------------

    else:

        c.execute("""
        INSERT INTO entries
        (number,name,weight,queen_qty,king_qty,price,separate,express,dropoff_time)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,(
            number,
            name,
            weight,
            queen_qty.get(),
            king_qty.get(),
            total,
            separate_var.get(),
            express_var.get(),
            drop_db
        ))

        order = c.lastrowid

    conn.commit()
    conn.close()

    # ----------------------------------
    # PRINT RECEIPT
    # ----------------------------------

    threading.Thread(
        target=print_receipt,
        args=(order,number,name,weight,rate,
              queen_qty.get(),king_qty.get(),
              total,drop,pick,copies,
              separate_var.get(),express_var.get()),
        daemon=True
    ).start()

    order_label.config(text=f"Order Number: {order}")
    dropoff_label.config(text=f"Drop-Off: {drop}")
    pickup_label.config(text=f"Pickup: {pick}")

# ==========================================================
# DASHBOARD
# ==========================================================

def show_dashboard():

    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    SELECT COUNT(*),
           COALESCE(SUM(weight),0),
           COALESCE(SUM(price),0)
    FROM entries
    WHERE dropoff_time LIKE ?
    """,(today+"%",))

    orders,pounds,revenue = c.fetchone()

    conn.close()

    win = tk.Toplevel(root)
    win.title("Daily Dashboard")
    win.geometry("500x350")

    tk.Label(win,text="TODAY",font=("Arial",30,"bold")).pack(pady=15)

    tk.Label(win,text=f"Orders: {orders}",font=("Arial",22)).pack()
    tk.Label(win,text=f"Pounds: {pounds:.2f}",font=("Arial",22)).pack()

    tk.Label(
        win,
        text=f"Revenue: ${revenue:.2f}",
        font=("Arial",24,"bold"),
        fg="green"
    ).pack(pady=20)


# ==========================================================
# LANGUAGE SWITCH
# ==========================================================

def toggle_language():

    global current_language

    if current_language == "en":
        current_language = "vi"
    else:
        current_language = "en"

    update_language()


def update_language():

    t = translations[current_language]

    phone_label.config(text=t["phone"])
    name_label.config(text=t["name"])
    weight_label.config(text=t["weight"])
    separate_box.config(text=t["separate"])
    express_box.config(text=t["express"])
    queen_label.config(text=t["queen"])
    king_label.config(text=t["king"])
    price_label.config(text=t["price"])
    copies_label.config(text=t["copies"])
    save_button.config(text=t["save"])
    dashboard_button.config(text=t["dashboard"])
    reprint_button.config(text=t["reprint"])
    lookup_label.config(text=t["lookup"])


# ==========================================================
# GUI
# ==========================================================

root = tk.Tk()
root.title("Laundromat Kiosk")

root.geometry("1200x1000")

BIG=("Arial",28)
ENTRY=("Arial",30)
BOLD=("Arial",34,"bold")

phone_var=tk.StringVar()
name_var=tk.StringVar()
weight_var=tk.StringVar()
money_var=tk.StringVar()

order_lookup_var=tk.StringVar()
copies_text=tk.StringVar(value="1")

queen_qty=tk.IntVar(value=0)
king_qty=tk.IntVar(value=0)

separate_var=tk.BooleanVar()
express_var=tk.BooleanVar()

frame=tk.Frame(root,padx=40,pady=30)
frame.pack(fill="both",expand=True)


# LANGUAGE BUTTON

tk.Button(
    frame,
    text="EN / VI",
    font=("Arial",20,"bold"),
    command=toggle_language
).grid(row=0,column=2)


# ORDER LOOKUP

lookup_label=tk.Label(frame,text="Find Order #",font=BIG)
lookup_label.grid(row=0,column=0)

tk.Entry(frame,textvariable=order_lookup_var,font=ENTRY)\
.grid(row=0,column=1)

order_lookup_var.trace_add("write",load_order)


# PHONE

phone_label=tk.Label(frame,text="Phone",font=BIG)
phone_label.grid(row=1,column=0)

tk.Entry(frame,textvariable=phone_var,font=ENTRY)\
.grid(row=1,column=1)

phone_var.trace_add("write",on_phone_change)


# NAME

name_label=tk.Label(frame,text="Name",font=BIG)
name_label.grid(row=2,column=0)

tk.Entry(frame,textvariable=name_var,font=ENTRY)\
.grid(row=2,column=1)


status_label=tk.Label(frame,text="",font=BOLD)
status_label.grid(row=3,column=0,columnspan=2)

totals_label=tk.Label(frame,text="",font=BIG)
totals_label.grid(row=4,column=0,columnspan=2)

visits_label=tk.Label(frame,text="",font=BIG)
visits_label.grid(row=5,column=0,columnspan=2)


# WEIGHT

weight_label=tk.Label(frame,text="Weight",font=BIG)
weight_label.grid(row=6,column=0)

weight_var.trace_add("write",update_price)

tk.Entry(frame,textvariable=weight_var,font=ENTRY)\
.grid(row=6,column=1)


# OPTIONS

separate_box=tk.Checkbutton(
frame,
text="Separate Whites (+10%)",
variable=separate_var,
command=update_price,
font=BIG)

separate_box.grid(row=7,column=0,columnspan=2)

express_box=tk.Checkbutton(
frame,
text="Express (+15%)",
variable=express_var,
command=update_price,
font=BIG)

express_box.grid(row=8,column=0,columnspan=2)


# COMFORTERS

queen_label=tk.Label(frame,text="Queen Comforter",font=BIG)
queen_label.grid(row=9,column=0)

tk.Button(frame,text="-",
command=lambda:change_queen(-1)).grid(row=9,column=1,sticky="w")

tk.Label(frame,textvariable=queen_qty,font=BIG).grid(row=9,column=1)

tk.Button(frame,text="+",
command=lambda:change_queen(1)).grid(row=9,column=1,sticky="e")


king_label=tk.Label(frame,text="King Comforter",font=BIG)
king_label.grid(row=10,column=0)

tk.Button(frame,text="-",
command=lambda:change_king(-1)).grid(row=10,column=1,sticky="w")

tk.Label(frame,textvariable=king_qty,font=BIG).grid(row=10,column=1)

tk.Button(frame,text="+",
command=lambda:change_king(1)).grid(row=10,column=1,sticky="e")


# PRICE

price_label=tk.Label(frame,text="Price",font=BIG)
price_label.grid(row=11,column=0)

tk.Entry(frame,textvariable=money_var,font=ENTRY,state="readonly")\
.grid(row=11,column=1)


# COPIES

copies_label=tk.Label(frame,text="Copies",font=BIG)
copies_label.grid(row=12,column=0)

tk.Entry(frame,textvariable=copies_text,font=ENTRY,width=5)\
.grid(row=12,column=1)


# ORDER INFO

order_label=tk.Label(frame,text="",font=BOLD)
order_label.grid(row=13,column=0,columnspan=2)

dropoff_label=tk.Label(frame,text="",font=BIG)
dropoff_label.grid(row=14,column=0,columnspan=2)

pickup_label=tk.Label(frame,text="",font=BIG)
pickup_label.grid(row=15,column=0,columnspan=2)


# SAVE BUTTON

save_button=tk.Button(
frame,
text="SAVE ENTRY & PRINT RECEIPT",
font=("Arial",28,"bold"),
bg="green",
fg="white",
command=save_entry)

save_button.grid(row=16,column=0,columnspan=2,pady=20)


# DASHBOARD

dashboard_button=tk.Button(
frame,
text="DAILY DASHBOARD",
font=("Arial",24,"bold"),
bg="blue",
fg="white",
command=show_dashboard)

dashboard_button.grid(row=17,column=0,columnspan=2)


# REPRINT

reprint_button=tk.Button(
frame,
text="REPRINT LAST RECEIPT",
font=("Arial",22,"bold"),
bg="orange",
command=reprint_last_receipt)

reprint_button.grid(row=18,column=0,columnspan=2,pady=10)


update_language()

root.mainloop()