from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime
import subprocess

FILE = "receipt_a4.pdf"

# --- CREATE PDF ---
c = canvas.Canvas(FILE, pagesize=A4)
width, height = A4

c.setFont("Courier-Bold", 16)
c.drawCentredString(width / 2, height - 50, "SENTER LAUNDROMAT")

c.setFont("Courier", 10)
c.drawCentredString(width / 2, height - 70, "2266 Senter Road")
c.drawCentredString(width / 2, height - 85, "")

y = height - 120
c.drawString(50, y, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
y -= 20

c.line(50, y, width - 50, y)
y -= 20

items = [
    ("Item A", 2, 5.00),
    ("Item B", 1, 3.00),
]

c.drawString(50, y, "Item")
c.drawString(350, y, "Qty")
c.drawString(420, y, "Price")
y -= 15

total = 0
for name, qty, price in items:
    c.drawString(50, y, name)
    c.drawRightString(390, y, str(qty))
    c.drawRightString(500, y, f"${price * qty:.2f}")
    total += price * qty
    y -= 15

y -= 10
c.line(50, y, width - 50, y)
y -= 25

c.setFont("Courier-Bold", 12)
c.drawRightString(500, y, f"TOTAL: ${total:.2f}")

y -= 40
c.setFont("Courier", 10)
c.drawCentredString(width / 2, y, "Thank you for your purchase!")

c.save()

# --- PRINT PDF ---
subprocess.run(["lp", "-d", "HP_LaserJet_MFP_M28_M31", FILE], check=True)

print("✅ Receipt printed on A4 paper")

