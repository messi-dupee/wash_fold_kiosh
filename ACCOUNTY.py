import sqlite3
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import subprocess
import threading
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "store.db"
RECEIPT_FILE = str(BASE_DIR / "receipt_a4.pdf")
PRINTER_NAME = "POS-80"

# ================= DATABASE =================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS entries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT,
        name TEXT,
        weight REAL,
        price REAL,
        dropoff_time TEXT
    )
    """)

    conn.commit()
    conn.close()

def upgrade_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        c.execute("ALTER TABLE entries ADD COLUMN queen_qty INTEGER DEFAULT 0")
    except:
        pass

    try:
        c.execute("ALTER TABLE entries ADD COLUMN king_qty INTEGER DEFAULT 0")
    except:
        pass

    conn.commit()
    conn.close()

init_db()
upgrade_db()

# ================= CLEAN INPUT =================

def clean_phone_number(v):
    return "".join(filter(str.isdigit, v))[:10]

def clean_name(v):
    allowed="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "
    return "".join(c for c in v if c in allowed)

# ================= PICKUP =================

def calculate_pickup_time(dropoff):
    pickup = dropoff + timedelta(hours=8)

    if pickup.weekday()==2:
        pickup += timedelta(days=1)

    if pickup.hour < 12:
        pickup = pickup.replace(hour=12,minute=0,second=0)

    return pickup

# ================= ORDER NUMBER =================

def get_today_order_number():

    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "SELECT COUNT(*) FROM entries WHERE dropoff_time LIKE ?",
        (today+"%",)
    )

    count = c.fetchone()[0]
    conn.close()

    return count+1

# ================= CUSTOMER LOOKUP =================

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
        FROM entries WHERE number=?
    """,(number,))

    visits,total_weight,total_price = c.fetchone()

    conn.close()

    return (name_row[0] if name_row else None),visits,total_weight,total_price

# ================= PRICE CALC =================

def update_price(*args):

    if weight_var.get().replace('.','',1).isdigit():
        weight=float(weight_var.get())
    else:
        weight=0

    price_per_lb = 2.0 if separate_var.get() else 1.5

    laundry = weight * price_per_lb
    queen = queen_qty.get()*20
    king = king_qty.get()*25

    total = laundry + queen + king

    money_var.set(f"{total:.2f}")

# ================= COMFORTER BUTTONS =================

def change_queen(delta):
    q=queen_qty.get()+delta
    if q<0: q=0
    queen_qty.set(q)
    update_price()

def change_king(delta):
    k=king_qty.get()+delta
    if k<0: k=0
    king_qty.set(k)
    update_price()

# ================= AUTO LOOKUP =================

def on_phone_change(*args):

    number = clean_phone_number(phone_var.get())

    if phone_var.get()!=number:
        phone_var.set(number)

    if len(number)==10:

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
            status_label.config(text="New Customer",fg="green")

# ================= DASHBOARD =================

def show_dashboard():

    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT
            COUNT(*),
            COALESCE(SUM(weight),0),
            COALESCE(SUM(queen_qty),0),
            COALESCE(SUM(king_qty),0),
            COALESCE(SUM(price),0)
        FROM entries
        WHERE dropoff_time LIKE ?
    """,(today+"%",))

    orders,pounds,queens,kings,revenue = c.fetchone()

    conn.close()

    win = tk.Toplevel(root)
    win.title("Daily Dashboard")
    win.geometry("500x400")

    tk.Label(win,text="TODAY'S BUSINESS",font=("Arial",28,"bold")).pack(pady=20)

    tk.Label(win,text=f"Orders Today: {orders}",font=("Arial",22)).pack(pady=5)
    tk.Label(win,text=f"Total Pounds: {pounds:.2f} lb",font=("Arial",22)).pack(pady=5)
    tk.Label(win,text=f"Queen Comforters: {queens}",font=("Arial",22)).pack(pady=5)
    tk.Label(win,text=f"King Comforters: {kings}",font=("Arial",22)).pack(pady=5)

    tk.Label(win,text=f"Total Revenue: ${revenue:.2f}",
             font=("Arial",24,"bold"),fg="green").pack(pady=15)

# ================= PRINT RECEIPT =================

def print_receipt(order,number,name,weight,price_per_lb,
                  queen_q,king_q,total,drop,pick,copies):

    laundry = weight * price_per_lb

    c = canvas.Canvas(RECEIPT_FILE,pagesize=A4)
    width,height=A4

    c.setFont("Courier-Bold",50)
    c.drawCentredString(width/2,height-60,"SENTER LAUNDROMAT")

    c.setFont("Courier-Bold",40)
    c.drawCentredString(width/2,height-120,f"ORDER #{order}")

    c.setFont("Courier",32)

    x=50
    y=height-220

    c.drawString(x,y,f"DROP: {drop}")
    y-=50

    c.setFont("Courier-Bold",32)

    c.drawString(x,y,f"PICKUP: {pick}")
    y-=70

    c.setFont("Courier",32)

    c.drawString(x,y,f"Phone: {number}")
    y-=50

    c.drawString(x,y,f"Name: {name}")
    y-=70

    c.setFont("Courier",25)

    c.drawString(x,y,f"Laundry {weight:.2f} lb")
    c.drawRightString(width-50,y,f"${laundry:.2f}")
    y-=45

    if price_per_lb==2.0:
        c.setFont("Courier-Oblique",28)
        c.drawString(x,y,"Separate Whites & Colors")
        y-=40
        c.setFont("Courier",32)

    if queen_q>0:
        qprice=queen_q*20
        c.drawString(x,y,f"Queen Comforter x{queen_q}")
        c.drawRightString(width-50,y,f"${qprice:.2f}")
        y-=45

    if king_q>0:
        kprice=king_q*25
        c.drawString(x,y,f"King Comforter x{king_q}")
        c.drawRightString(width-50,y,f"${kprice:.2f}")
        y-=45

    y-=20
    c.line(x,y,width-50,y)
    y-=50

    c.setFont("Courier-Bold",34)

    c.drawString(x,y,"TOTAL")
    c.drawRightString(width-50,y,f"${total:.2f}")

    c.save()

    for i in range(copies):
        subprocess.run(
            ["lp","-d",PRINTER_NAME,RECEIPT_FILE],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

# ================= SAVE ENTRY =================

def save_entry():

    number=clean_phone_number(phone_var.get())
    name=clean_name(name_var.get())

    if len(number)!=10:
        messagebox.showerror("Error","Phone number must be 10 digits")
        return

    try:
        weight=float(weight_var.get())
    except:
        messagebox.showerror("Error","Invalid weight")
        return

    price_per_lb = 2.0 if separate_var.get() else 1.5

    laundry=weight*price_per_lb
    queen=queen_qty.get()*20
    king=king_qty.get()*25

    price=laundry+queen+king

    now=datetime.now()
    pickup=calculate_pickup_time(now)

    order=get_today_order_number()

    drop_db=now.strftime("%Y-%m-%d %H:%M:%S")
    drop=now.strftime("%m/%d %I:%M%p")
    pick=pickup.strftime("%m/%d %I:%M%p")

    copies=int(copies_text.get())

    conn=sqlite3.connect(DB_PATH)
    c=conn.cursor()

    c.execute(
        "INSERT INTO entries(number,name,weight,queen_qty,king_qty,price,dropoff_time) VALUES(?,?,?,?,?,?,?)",
        (number,name,weight,queen_qty.get(),king_qty.get(),price,drop_db)
    )

    conn.commit()
    conn.close()

    threading.Thread(
        target=print_receipt,
        args=(order,number,name,weight,price_per_lb,
              queen_qty.get(),king_qty.get(),price,
              drop,pick,copies),
        daemon=True
    ).start()

    order_label.config(text=f"Order Number: {order}")
    dropoff_label.config(text=f"Drop-Off: {drop}")
    pickup_label.config(text=f"Pickup: {pick}")

    phone_var.set("")
    name_var.set("")
    weight_var.set("")
    money_var.set("")

    queen_qty.set(0)
    king_qty.set(0)
    separate_var.set(False)

# ================= GUI =================

root=tk.Tk()
root.title("Laundromat Kiosk")
root.geometry("1000x900")

BIG=("Arial",28)
ENTRY=("Arial",30)
BOLD=("Arial",34,"bold")

phone_var=tk.StringVar()
name_var=tk.StringVar()
weight_var=tk.StringVar()
money_var=tk.StringVar()

copies_text=tk.StringVar(value="1")

separate_var=tk.BooleanVar()
queen_qty=tk.IntVar(value=0)
king_qty=tk.IntVar(value=0)

frame=tk.Frame(root,padx=60,pady=40)
frame.pack(fill="both",expand=True)

frame.columnconfigure(0,weight=1)
frame.columnconfigure(1,weight=2)

tk.Label(frame,text="Phone Number",font=BIG).grid(row=0,column=0,sticky="w")
tk.Entry(frame,font=ENTRY,textvariable=phone_var).grid(row=0,column=1,sticky="ew",ipady=12)

phone_var.trace_add("write",on_phone_change)

tk.Label(frame,text="Customer Name",font=BIG).grid(row=1,column=0,sticky="w")
tk.Entry(frame,font=ENTRY,textvariable=name_var).grid(row=1,column=1,sticky="ew",ipady=12)

status_label=tk.Label(frame,text="",font=BOLD,fg="green")
status_label.grid(row=2,column=0,columnspan=2)

totals_label=tk.Label(frame,text="",font=BIG,fg="blue")
totals_label.grid(row=3,column=0,columnspan=2)

visits_label=tk.Label(frame,text="",font=BIG,fg="purple")
visits_label.grid(row=4,column=0,columnspan=2)

tk.Label(frame,text="Weight (lbs)",font=BIG).grid(row=5,column=0,sticky="w")
weight_var.trace_add("write",update_price)
tk.Entry(frame,font=ENTRY,textvariable=weight_var).grid(row=5,column=1,ipady=12)

tk.Checkbutton(
    frame,
    text="Separate Whites & Colors ($2/lb)",
    variable=separate_var,
    command=update_price,
    font=("Arial",22)
).grid(row=6,column=0,columnspan=2,sticky="w")

tk.Label(frame,text="Queen Comforter (+$20)",font=BIG).grid(row=7,column=0)

qframe=tk.Frame(frame)
qframe.grid(row=7,column=1)

tk.Button(qframe,text="-",font=("Arial",22),command=lambda:change_queen(-1)).pack(side="left")
tk.Label(qframe,textvariable=queen_qty,font=("Arial",24),width=3).pack(side="left")
tk.Button(qframe,text="+",font=("Arial",22),command=lambda:change_queen(1)).pack(side="left")

tk.Label(frame,text="King Comforter (+$25)",font=BIG).grid(row=8,column=0)

kframe=tk.Frame(frame)
kframe.grid(row=8,column=1)

tk.Button(kframe,text="-",font=("Arial",22),command=lambda:change_king(-1)).pack(side="left")
tk.Label(kframe,textvariable=king_qty,font=("Arial",24),width=3).pack(side="left")
tk.Button(kframe,text="+",font=("Arial",22),command=lambda:change_king(1)).pack(side="left")

tk.Label(frame,text="Price ($)",font=BIG).grid(row=9,column=0)
tk.Entry(frame,font=ENTRY,textvariable=money_var,state="readonly").grid(row=9,column=1,ipady=12)

tk.Label(frame,text="Receipt Copies",font=BIG).grid(row=10,column=0)
tk.Entry(frame,font=ENTRY,width=5,textvariable=copies_text).grid(row=10,column=1)

order_label=tk.Label(frame,text="",font=BOLD,fg="red")
order_label.grid(row=11,column=0,columnspan=2)

dropoff_label=tk.Label(frame,text="",font=BIG)
dropoff_label.grid(row=12,column=0,columnspan=2)

pickup_label=tk.Label(frame,text="",font=BIG)
pickup_label.grid(row=13,column=0,columnspan=2)

tk.Button(
    frame,
    text="SAVE ENTRY & PRINT RECEIPT",
    font=("Arial",34,"bold"),
    bg="#4CAF50",
    fg="white",
    height=2,
    command=save_entry
).grid(row=14,column=0,columnspan=2,sticky="ew",pady=30)

tk.Button(
    frame,
    text="DAILY DASHBOARD",
    font=("Arial",26,"bold"),
    bg="#2196F3",
    fg="white",
    command=show_dashboard
).grid(row=15,column=0,columnspan=2,sticky="ew",pady=10)

root.mainloop()