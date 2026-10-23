"""Tests for the deposit auto-invoice flow."""

from app import database
from app.routers import payments as payments_router
from app.services import flutterwave
from app.services import invoice as invoice_service


def _pay_deposit(client, monkeypatch, booking_id, amount=20.0, currency="GBP"):
    monkeypatch.setattr(
        flutterwave,
        "verify_transaction",
        lambda transaction_id: {
            "status": "successful",
            "tx_ref": f"WB-BK-{booking_id}-abcd",
            "amount": amount,
            "id": "tx-deposit",
            "currency": currency,
        },
    )
    monkeypatch.setattr(payments_router, "send_booking_confirmation_sms", lambda *a, **k: {"status": "skipped"})
    return client.get(f"/api/payments/verify?tx_ref=WB-BK-{booking_id}-abcd&transaction_id=tx-deposit")


def _invoice_rows(booking_id):
    conn = database.get_connection()
    try:
        return conn.execute(
            "SELECT * FROM invoices WHERE booking_id = ?", (booking_id,)
        ).fetchall()
    finally:
        conn.close()


def test_deposit_payment_creates_invoice_row_and_pdf(
    client, make_business, make_booking, monkeypatch, tmp_path
):
    invoice_service.UPLOAD_DIR = tmp_path
    biz = make_business("invco", deposit=20.0)
    booking_id = make_booking(biz["id"], customer_email="jane@wavebook.com", status="pending", service_price=50.0)

    res = _pay_deposit(client, monkeypatch, booking_id)
    assert res.status_code == 200, res.text

    rows = _invoice_rows(booking_id)
    assert len(rows) == 1
    inv = rows[0]
    assert inv["number"].startswith("INV-")
    assert inv["total"] == 50.0
    assert inv["deposit_paid"] == 20.0
    assert inv["balance_due"] == 30.0
    assert inv["status"] == "partial"
    assert inv["currency"] == "GBP"

    # PDF was written to disk
    pdf = tmp_path / "invoices" / f"{inv['number']}.pdf"
    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")


def test_invoice_numbers_sequence_per_business(client, make_business, make_booking, monkeypatch, tmp_path):
    invoice_service.UPLOAD_DIR = tmp_path
    biz = make_business("invseq", deposit=10.0)
    b1 = make_booking(biz["id"], customer_email="a@wavebook.com", status="pending", service_price=40.0)
    b2 = make_booking(biz["id"], customer_email="b@wavebook.com", status="pending", service_price=60.0)

    _pay_deposit(client, monkeypatch, b1, amount=10.0)
    _pay_deposit(client, monkeypatch, b2, amount=10.0)

    rows = _invoice_rows(b1) + _invoice_rows(b2)
    numbers = sorted(r["number"] for r in rows)
    assert numbers[0].endswith("-0001")
    assert numbers[1].endswith("-0002")
    assert numbers[0] != numbers[1]


def test_full_deposit_marks_invoice_paid(client, make_business, make_booking, monkeypatch, tmp_path):
    invoice_service.UPLOAD_DIR = tmp_path
    biz = make_business("invfull", deposit=50.0)
    booking_id = make_booking(biz["id"], customer_email="jane@wavebook.com", status="pending", service_price=50.0)

    res = _pay_deposit(client, monkeypatch, booking_id, amount=50.0)
    assert res.status_code == 200, res.text

    rows = _invoice_rows(booking_id)
    assert len(rows) == 1
    assert rows[0]["balance_due"] == 0.0
    assert rows[0]["status"] == "paid"


def test_verify_twice_does_not_duplicate_invoice(client, make_business, make_booking, monkeypatch, tmp_path):
    invoice_service.UPLOAD_DIR = tmp_path
    biz = make_business("invdup", deposit=20.0)
    booking_id = make_booking(biz["id"], customer_email="jane@wavebook.com", status="pending", service_price=50.0)

    _pay_deposit(client, monkeypatch, booking_id)
    _pay_deposit(client, monkeypatch, booking_id)

    assert len(_invoice_rows(booking_id)) == 1
