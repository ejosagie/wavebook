import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from ..config import settings
from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import business_tier_features, get_current_business, require_owner
from ..schemas import OrderUpdate, ProductCreate, ProductUpdate, StorefrontCheckout
from ..services import flutterwave, gcs
from ..services.uploads import image_content_type

router = APIRouter(tags=["storefront"])

UPLOAD_DIR = None  # set in main via app.state


def _upload_dir():
    return UPLOAD_DIR


# ---- Owner product management (app) ----


@router.get("/api/products")
def list_products(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM products WHERE business_id = ? ORDER BY sort_order, id",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows


@router.post("/api/products", status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        max_products = business_tier_features(business)["max_products"]
        if max_products is not None:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM products WHERE business_id = ?",
                (business["id"],),
            ).fetchone()["c"]
            if count >= max_products:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your plan allows up to {max_products} products. Upgrade for unlimited products.",
                )
        cur = conn.execute(
            "INSERT INTO products (business_id, name, description, price, sort_order) VALUES (?, ?, ?, ?, ?)",
            (business["id"], data.name.strip(), data.description.strip(), data.price, data.sort_order),
        )
        conn.commit()
        product = row_to_dict(
            conn.execute("SELECT * FROM products WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    finally:
        conn.close()
    return product


@router.patch("/api/products/{product_id}")
def update_product(
    product_id: int,
    data: ProductUpdate,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    updates = data.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return {"ok": True}
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT id FROM products WHERE id = ? AND business_id = ?",
            (product_id, business["id"]),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Product not found")
        fields = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE products SET {fields} WHERE id = ? AND business_id = ?",
            (*updates.values(), product_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/api/products/{product_id}")
def delete_product(
    product_id: int,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT image_path FROM products WHERE id = ? AND business_id = ?",
            (product_id, business["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        if row["image_path"]:
            if row["image_path"].startswith("http"):
                # Stored in GCS — remove from the bucket
                try:
                    gcs.delete_shop_image(business["id"], product_id)
                except Exception:
                    pass
            else:
                # Stored on the local disk
                try:
                    (_upload_dir() / row["image_path"].split("/")[-1]).unlink(missing_ok=True)
                except OSError:
                    pass
        conn.execute("DELETE FROM products WHERE id = ? AND business_id = ?", (product_id, business["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/api/products/{product_id}/image")
def upload_product_image(
    product_id: int,
    file: UploadFile,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    if image_content_type(file) is None:
        raise HTTPException(status_code=400, detail="Use JPG, PNG, GIF or WebP")

    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT id FROM products WHERE id = ? AND business_id = ?",
            (product_id, business["id"]),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Product not found")
    finally:
        conn.close()

    import uuid

    data = file.file.read()
    if gcs.gcs_enabled():
        # Upload to the public GCS bucket (auto-resized to 800px JPEG)
        try:
            url = gcs.upload_shop_image(business["id"], product_id, data)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        path = url
    else:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
        filename = f"product_{business['id']}_{product_id}_{uuid.uuid4().hex[:8]}.{ext}"
        uploads = _upload_dir()
        uploads.mkdir(parents=True, exist_ok=True)
        dest = uploads / filename
        dest.write_bytes(data)
        path = f"/uploads/{filename}"

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE products SET image_path = ? WHERE id = ? AND business_id = ?",
            (path, product_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"path": path}


# ---- Public storefront (customer booking website) ----


@router.get("/api/storefront/{slug}")
def public_storefront(slug: str):
    """Public product listing for a business's booking website."""
    conn = get_connection()
    try:
        business = conn.execute("SELECT * FROM businesses WHERE slug = ?", (slug,)).fetchone()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        if not business["storefront_enabled"]:
            raise HTTPException(status_code=404, detail="Storefront not enabled")
        products = rows_to_dicts(
            conn.execute(
                "SELECT * FROM products WHERE business_id = ? AND active = 1 ORDER BY sort_order, id",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return {
        "business": {
            "name": business["name"],
            "slug": business["slug"],
            "currency": business["currency"],
            "contact_phone": business["contact_phone"],
        },
        "products": products,
    }


@router.post("/api/storefront/checkout")
def storefront_checkout(data: StorefrontCheckout):
    """Create an order and a Flutterwave payment link for storefront products."""
    conn = get_connection()
    try:
        business = conn.execute("SELECT * FROM businesses WHERE slug = ?", (data.slug,)).fetchone()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        if not business["storefront_enabled"]:
            raise HTTPException(status_code=400, detail="Storefront not enabled")

        items = []
        total = 0.0
        for item in data.items:
            product = conn.execute(
                "SELECT * FROM products WHERE id = ? AND business_id = ? AND active = 1",
                (item.product_id, business["id"]),
            ).fetchone()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
            qty = max(1, item.quantity)
            line_total = float(product["price"]) * qty
            total += line_total
            items.append(
                {
                    "product_id": product["id"],
                    "name": product["name"],
                    "price": product["price"],
                    "quantity": qty,
                }
            )
        if total <= 0:
            raise HTTPException(status_code=400, detail="Your basket is empty")

        cur = conn.execute(
            "INSERT INTO orders (business_id, customer_name, customer_email, customer_phone, items, total, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (
                business["id"],
                data.customer_name.strip(),
                data.customer_email.strip(),
                data.customer_phone.strip(),
                json.dumps(items),
                round(total, 2),
            ),
        )
        order_id = cur.lastrowid
        conn.commit()

        tx_ref = f"WB-ORD-{order_id}-{secrets.token_hex(4)}"
        payment_link = flutterwave.create_payment_link(
            tx_ref=tx_ref,
            amount=round(total, 2),
            currency=settings.FLW_CURRENCY,
            redirect_url=f"{settings.API_PUBLIC_URL}/pay/verify",
            customer_email=data.customer_email.strip(),
            meta={
                "order_id": str(order_id),
                "business_id": str(business["id"]),
                "type": "storefront",
            },
            title=f"{business['name']} Store",
            description=f"Order #{order_id} from {business['name']}",
        )
        conn.execute(
            "UPDATE orders SET payment_ref = ? WHERE id = ?", (tx_ref, order_id)
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "order_id": order_id,
        "payment_link": payment_link,
        "amount": round(total, 2),
        "currency": settings.FLW_CURRENCY.upper(),
    }


# ---- Owner order management (app) ----


@router.get("/api/orders")
def list_orders(business: dict = Depends(get_current_business)):
    """List storefront orders for the business, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE business_id = ? ORDER BY id DESC",
            (business["id"],),
        ).fetchall()
    finally:
        conn.close()
    orders = []
    for row in rows:
        order = row_to_dict(row)
        try:
            order["items"] = json.loads(order.get("items") or "[]")
        except json.JSONDecodeError:
            order["items"] = []
        orders.append(order)
    return orders


@router.patch("/api/orders/{order_id}")
def update_order_status(
    order_id: int,
    data: OrderUpdate,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    """Update a storefront order status (confirm, mark shipped, cancel)."""
    if data.status not in settings.ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid order status")

    conn = get_connection()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND business_id = ?",
            (order_id, business["id"]),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ? AND business_id = ?",
            (data.status, order_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "status": data.status}
