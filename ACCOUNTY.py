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

loaded_order_id = None

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
        queen_qty INTEGER DEFAULT 0,
        king_qty INTEGER DEFAULT 0,
        price REAL,
        separate INTEGER DEFAULT 0,
        dropoff_time TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= CLEAN INPUT =================

def clean_phone_number(v):
    return "".join(filter(str.isdigit,v))[:10]

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

# ================= CUSTOMER LOOKUP =================

def get_customer_info(number):

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "SELECT name FROM entries WHERE number=? ORDER BY id DESC LIMIT 1",
        (number,)
    )

    name_row=c.fetchone()

    c.execute("""
        SELECT COUNT(*),
               COALESCE(SUM(weight),0),
               COALESCE(SUM(price),0)
        FROM entries WHERE number=?
    """,(number,))

    visits,total_weight,total_price=c.fetchone()

    conn.close()

    return (name_row[0] if name_row else None),visits,total_weight,total_price

# ================= PRICE =================

def update_price(*args):

    if weight_var.get().replace('.','',1).isdigit():
        weight=float(weight_var.get())
    else:
        weight=0

    rate=2.0 if separate_var.get() else 1.5

    laundry=weight*rate
    queen=queen_qty.get()*20
    king=king_qty.get()*25

    total=laundry+queen+king

    money_var.set(f"{total:.2f}")

# ================= COMFORTER BUTTONS =================

def change_queen(delta):

    q=queen_qty.get()+delta
    if q<0:q=0
    queen_qty.set(q)

    update_price()

def change_king(delta):

    k=king_qty.get()+delta
    if k<0:k=0
    king_qty.set(k)

    update_price()

# ================= AUTO CUSTOMER LOOKUP =================

def on_phone_change(*args):

    number=clean_phone_number(phone_var.get())

    if phone_var.get()!=number:
        phone_var.set(number)

    if len(number)==10:

        name,visits,total_weight,total_price=get_customer_info(number)

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

# ================= LOAD ORDER =================

def load_order(*args):

    global loaded_order_id

    order_text = order_lookup_var.get()

    # If field is empty → clear everything
    if order_text == "":

        loaded_order_id = None

        totals_label.config(text="")
        visits_label.config(text="")
        status_label.config(text="")

        phone_var.set("")
        name_var.set("")
        weight_var.set("")
        money_var.set("")

        queen_qty.set(0)
        king_qty.set(0)

        separate_var.set(False)

        order_label.config(text="")

        return

    if not order_text.isdigit():
        return

    order_id = int(order_text)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT number,name,weight,queen_qty,king_qty,price,separate
        FROM entries
        WHERE id=?
    """,(order_id,))

    row = c.fetchone()
    conn.close()

    if row:

        number,name,weight,queen_q,king_q,price,separate = row

        phone_var.set(number)
        name_var.set(name)
        weight_var.set(str(weight))

        queen_qty.set(queen_q)
        king_qty.set(king_q)

        separate_var.set(bool(separate))

        money_var.set(f"{price:.2f}")

        loaded_order_id = order_id

        # Clear totals since this is an order lookup
        totals_label.config(text="")
        visits_label.config(text="")
        status_label.config(text="")

        order_label.config(text=f"Loaded Order #{order_id}")

# ================= DASHBOARD =================

def show_dashboard():

    today=datetime.now().strftime("%Y-%m-%d")

    conn=sqlite3.connect(DB_PATH)
    c=conn.cursor()

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

    orders,pounds,queens,kings,revenue=c.fetchone()

    conn.close()

    win=tk.Toplevel(root)
    win.title("Daily Dashboard")
    win.geometry("500x400")

    tk.Label(win,text="TODAY'S BUSINESS",font=("Arial",28,"bold")).pack(pady=20)

    tk.Label(win,text=f"Orders Today: {orders}",font=("Arial",22)).pack()
    tk.Label(win,text=f"Total Pounds: {pounds:.2f} lb",font=("Arial",22)).pack()
    tk.Label(win,text=f"Queen Comforters: {queens}",font=("Arial",22)).pack()
    tk.Label(win,text=f"King Comforters: {kings}",font=("Arial",22)).pack()

    tk.Label(win,text=f"Revenue: ${revenue:.2f}",
             font=("Arial",24,"bold"),fg="green").pack(pady=15)

# ================= PRINT RECEIPT =================

def print_receipt(order,number,name,weight,rate,
                  queen_q,king_q,total,drop,pick,copies):

    laundry=weight*rate

    c=canvas.Canvas(RECEIPT_FILE,pagesize=A4)
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

    c.drawString(x,y,f"PICKUP: {pick}")
    y-=70

    c.drawString(x,y,f"Phone: {number}")
    y-=50

    c.drawString(x,y,f"Name: {name}")
    y-=70

    line=f"Laundry {weight:.2f} lb @ ${rate:.2f}/lb"

    size=32
    while size>16:
        c.setFont("Courier",size)
        w=c.stringWidth(line,"Courier",size)

        if w<(width-180):
            break

        size-=1

    c.drawString(x,y,line)
    c.drawRightString(width-50,y,f"${laundry:.2f}")

    y-=45

    if rate==2.0:

        c.setFont("Courier-Oblique",28)
        c.drawString(x,y,"Separate Whites & Colors")
        y-=40
        c.setFont("Courier",32)

    if queen_q>0:

        price=queen_q*20

        c.drawString(x,y,f"Queen Comforter x{queen_q}")
        c.drawRightString(width-50,y,f"${price:.2f}")

        y-=45

    if king_q>0:

        price=king_q*25

        c.drawString(x,y,f"King Comforter x{king_q}")
        c.drawRightString(width-50,y,f"${price:.2f}")

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

    global loaded_order_id

    number=clean_phone_number(phone_var.get())
    name=clean_name(name_var.get())

    if len(number)!=10:

        messagebox.showerror("Error","Phone must be 10 digits")
        return

    try:
        weight=float(weight_var.get())
    except:

        messagebox.showerror("Error","Invalid weight")
        return

    rate=2.0 if separate_var.get() else 1.5

    laundry=weight*rate
    queen=queen_qty.get()*20
    king=king_qty.get()*25

    price=laundry+queen+king

    now=datetime.now()
    pickup=calculate_pickup_time(now)

    drop_db=now.strftime("%Y-%m-%d %H:%M:%S")
    drop=now.strftime("%m/%d %I:%M%p")
    pick=pickup.strftime("%m/%d %I:%M%p")

    copies=int(copies_text.get())

    if loaded_order_id:

        order=loaded_order_id

    else:

        conn=sqlite3.connect(DB_PATH)
        c=conn.cursor()

        c.execute("""
        INSERT INTO entries(number,name,weight,queen_qty,king_qty,price,separate,dropoff_time)
        VALUES(?,?,?,?,?,?,?,?)
        """,(number,name,weight,queen_qty.get(),king_qty.get(),
             price,separate_var.get(),drop_db))

        order=c.lastrowid

        conn.commit()
        conn.close()

    threading.Thread(
        target=print_receipt,
        args=(order,number,name,weight,rate,
              queen_qty.get(),king_qty.get(),
              price,drop,pick,copies),
        daemon=True
    ).start()

    loaded_order_id=None
    order_lookup_var.set("")

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
order_lookup_var=tk.StringVar()

separate_var=tk.BooleanVar()
queen_qty=tk.IntVar(value=0)
king_qty=tk.IntVar(value=0)

frame=tk.Frame(root,padx=60,pady=40)
frame.pack(fill="both",expand=True)

frame.columnconfigure(0,weight=1)
frame.columnconfigure(1,weight=2)

tk.Label(frame,text="Find Order #",font=BIG)\
.grid(row=0,column=0,sticky="w")

tk.Entry(frame,font=ENTRY,textvariable=order_lookup_var)\
.grid(row=0,column=1,sticky="ew",ipady=12)

order_lookup_var.trace_add("write",load_order)

tk.Label(frame,text="Phone Number",font=BIG)\
.grid(row=1,column=0,sticky="w")

tk.Entry(frame,font=ENTRY,textvariable=phone_var)\
.grid(row=1,column=1,sticky="ew",ipady=12)

phone_var.trace_add("write",on_phone_change)

tk.Label(frame,text="Customer Name",font=BIG)\
.grid(row=2,column=0,sticky="w")

tk.Entry(frame,font=ENTRY,textvariable=name_var)\
.grid(row=2,column=1,sticky="ew",ipady=12)

status_label=tk.Label(frame,text="",font=BOLD,fg="green")
status_label.grid(row=3,column=0,columnspan=2)

totals_label=tk.Label(frame,text="",font=BIG,fg="blue")
totals_label.grid(row=4,column=0,columnspan=2)

visits_label=tk.Label(frame,text="",font=BIG,fg="purple")
visits_label.grid(row=5,column=0,columnspan=2)

tk.Label(frame,text="Weight (lbs)",font=BIG)\
.grid(row=6,column=0,sticky="w")

weight_var.trace_add("write",update_price)

tk.Entry(frame,font=ENTRY,textvariable=weight_var)\
.grid(row=6,column=1,ipady=12)

tk.Checkbutton(
frame,
text="Separate Whites & Colors ($2/lb)",
variable=separate_var,
command=update_price,
font=("Arial",22)
).grid(row=7,column=0,columnspan=2,sticky="w")

tk.Label(frame,text="Queen Comforter (+$20)",font=BIG)\
.grid(row=8,column=0)

qframe=tk.Frame(frame)
qframe.grid(row=8,column=1)

tk.Button(qframe,text="-",font=("Arial",22),
command=lambda:change_queen(-1)).pack(side="left")

tk.Label(qframe,textvariable=queen_qty,
font=("Arial",24),width=3).pack(side="left")

tk.Button(qframe,text="+",font=("Arial",22),
command=lambda:change_queen(1)).pack(side="left")

tk.Label(frame,text="King Comforter (+$25)",font=BIG)\
.grid(row=9,column=0)

kframe=tk.Frame(frame)
kframe.grid(row=9,column=1)

tk.Button(kframe,text="-",font=("Arial",22),
command=lambda:change_king(-1)).pack(side="left")

tk.Label(kframe,textvariable=king_qty,
font=("Arial",24),width=3).pack(side="left")

tk.Button(kframe,text="+",font=("Arial",22),
command=lambda:change_king(1)).pack(side="left")

tk.Label(frame,text="Price ($)",font=BIG)\
.grid(row=10,column=0)

tk.Entry(frame,font=ENTRY,textvariable=money_var,
state="readonly").grid(row=10,column=1,ipady=12)

tk.Label(frame,text="Receipt Copies",font=BIG)\
.grid(row=11,column=0)

tk.Entry(frame,font=ENTRY,width=5,
textvariable=copies_text)\
.grid(row=11,column=1)

order_label=tk.Label(frame,text="",font=BOLD,fg="red")
order_label.grid(row=12,column=0,columnspan=2)

dropoff_label=tk.Label(frame,text="",font=BIG)
dropoff_label.grid(row=13,column=0,columnspan=2)

pickup_label=tk.Label(frame,text="",font=BIG)
pickup_label.grid(row=14,column=0,columnspan=2)

tk.Button(
frame,
text="SAVE ENTRY & PRINT RECEIPT",
font=("Arial",34,"bold"),
bg="#4CAF50",
fg="white",
height=2,
command=save_entry
).grid(row=15,column=0,columnspan=2,sticky="ew",pady=30)

tk.Button(
frame,
text="DAILY DASHBOARD",
font=("Arial",26,"bold"),
bg="#2196F3",
fg="white",
command=show_dashboard
).grid(row=16,column=0,columnspan=2,sticky="ew",pady=10)

root.mainloop()