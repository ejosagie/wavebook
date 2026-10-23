"""Invoice generation for bookings with a deposit.

When a customer pays a deposit, WaveBook creates an invoice showing the
total, the deposit paid and the remaining balance, renders it as a PDF and
emails the customer a link to it.
"""

from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from ..config import settings
from ..database import row_to_dict
from ..services import emailer

# Set by main.py (like business.UPLOAD_DIR) so tests can redirect it.
UPLOAD_DIR: Path | None = None

CURRENCY_SYMBOLS = {
    "GBP": "£",
    "USD": "$",
    "CAD": "C$",
    "EUR": "€",
    "AUD": "A$",
    "NZD": "NZ$",
    "NGN": "₦",
    "KES": "KSh",
    "ZAR": "R",
}


def _format_price(amount: float, currency: str = "GBP") -> str:
    code = (currency or "GBP").upper()
    symbol = CURRENCY_SYMBOLS.get(code, f"{code} ")
    return f"{symbol}{amount:,.2f}"


def create_invoice(conn, booking: dict, business: dict, deposit_paid: float) -> dict:
    """Create an invoice row for a booking and return it as a dict."""
    total = float(booking["service_price"] or 0)
    balance = max(total - deposit_paid, 0.0)
    year = date.today().year
    seq = conn.execute(
        "SELECT COUNT(*) AS n FROM invoices WHERE business_id = ?", (business["id"],)
    ).fetchone()["n"] + 1
    number = f"INV-{year}-{seq:04d}"
    cur = conn.execute(
        """INSERT INTO invoices (business_id, booking_id, number, total, deposit_paid, balance_due, currency, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            business["id"],
            booking["id"],
            number,
            total,
            deposit_paid,
            balance,
            business["currency"] or "GBP",
            "paid" if balance <= 0 else "partial",
        ),
    )
    conn.commit()
    return row_to_dict(conn.execute("SELECT * FROM invoices WHERE id = ?", (cur.lastrowid,)).fetchone())


def _invoices_dir() -> Path:
    base = UPLOAD_DIR or (Path(__file__).resolve().parent.parent.parent / "uploads")
    return base / "invoices"


def build_invoice_pdf(invoice: dict, booking: dict, business: dict) -> bytes:
    """Render a formal A4 PDF invoice and return the bytes."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 18 * mm
    currency = invoice.get("currency") or business.get("currency") or "GBP"

    # Header band
    c.setFillColor(colors.HexColor("#ec4899"))
    c.rect(0, height - 24 * mm, width, 24 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, height - 16 * mm, (business.get("name") or "WaveBook Business")[:40])
    c.setFont("Helvetica", 9)
    c.drawString(margin, height - 21 * mm, "INVOICE")

    # Invoice meta on the right
    c.setFillColor(colors.HexColor("#334155"))
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(width - margin, height - 14 * mm, invoice.get("number") or "")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawRightString(width - margin, height - 19 * mm, f"Issued {invoice.get('created_at', '')[:10]}")

    y = height - 34 * mm

    # From / Bill to blocks
    c.setFillColor(colors.HexColor("#334155"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "From")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#475569"))
    lines = [business.get("name") or ""]
    if business.get("contact_email"):
        lines.append(business["contact_email"])
    if business.get("contact_phone"):
        lines.append(business["contact_phone"])
    for i, line in enumerate(lines[:4]):
        c.drawString(margin, y - 4.5 * mm - i * 4.5 * mm, line[:60])

    x_right = width - margin - 60 * mm
    c.setFillColor(colors.HexColor("#334155"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_right, y, "Bill to")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#475569"))
    bill_lines = [
        booking.get("customer_name") or "",
        booking.get("customer_email") or "",
        booking.get("customer_phone") or "",
    ]
    for i, line in enumerate(bill_lines[:4]):
        c.drawString(x_right, y - 4.5 * mm - i * 4.5 * mm, line[:60])

    y -= 30 * mm

    # Line items table
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=12)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    rows = [
        [Paragraph("Service", head), Paragraph("Date", head), Paragraph("Time", head), Paragraph("Amount", head)],
        [
            Paragraph(booking.get("service_name") or "", cell),
            Paragraph(str(booking.get("date") or ""), cell),
            Paragraph(str(booking.get("time") or ""), cell),
            Paragraph(_format_price(float(booking.get("service_price") or 0), currency), cell),
        ],
    ]
    table = Table(rows, colWidths=[70 * mm, 34 * mm, 30 * mm, 34 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ec4899")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    table.wrapOn(c, width - 2 * margin, height)
    table.drawOn(c, margin, y - 14 * mm)

    y -= 40 * mm

    # Totals
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(margin, y, "Total")
    c.drawRightString(width - margin, y, _format_price(invoice.get("total") or 0, currency))
    y -= 5.5 * mm
    c.drawString(margin, y, "Deposit paid")
    c.drawRightString(width - margin, y, f"- {_format_price(invoice.get('deposit_paid') or 0, currency)}")
    y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin, y, "Balance due")
    c.drawRightString(width - margin, y, _format_price(invoice.get("balance_due") or 0, currency))

    # Footer
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.drawCentredString(width / 2, 14 * mm, f"Booking reference: {booking.get('reference', '')}  ·  {business.get('name', '')}  ·  Powered by WaveBook")

    c.showPage()
    c.save()
    return buf.getvalue()


def save_invoice_pdf(invoice: dict, booking: dict, business: dict) -> str:
    """Write the invoice PDF to disk and return its public URL."""
    pdf = build_invoice_pdf(invoice, booking, business)
    folder = _invoices_dir()
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{invoice['number']}.pdf"
    (folder / filename).write_bytes(pdf)
    return f"{settings.API_PUBLIC_URL}/uploads/invoices/{filename}"


def send_invoice_email(invoice: dict, booking: dict, business: dict) -> dict:
    """Email the customer their invoice with a link to the PDF."""
    to = (booking.get("customer_email") or "").strip()
    if not to:
        return {"provider": "none", "status": "skipped", "reason": "no recipient"}
    url = save_invoice_pdf(invoice, booking, business)
    currency = invoice.get("currency") or business.get("currency") or "GBP"
    body = (
        f"Hi {booking.get('customer_name', '')},\n\n"
        f"Thanks for your deposit with {business.get('name', '')}.\n\n"
        f"  Service: {booking.get('service_name', '')}\n"
        f"  Date: {booking.get('date', '')} at {booking.get('time', '')}\n"
        f"  Booking reference: {booking.get('reference', '')}\n"
        f"  Invoice: {invoice.get('number', '')}\n\n"
        f"  Total: {_format_price(invoice.get('total') or 0, currency)}\n"
        f"  Deposit paid: {_format_price(invoice.get('deposit_paid') or 0, currency)}\n"
        f"  Balance due: {_format_price(invoice.get('balance_due') or 0, currency)}\n\n"
        f"Your invoice is available here:\n{url}\n\n"
        "The balance is payable at your appointment unless agreed otherwise.\n\n"
        f"Thanks,\n{business.get('name', '')}"
    )
    return emailer.send_email(to, f"Invoice {invoice.get('number', '')} — {booking.get('service_name', '')}", body)
