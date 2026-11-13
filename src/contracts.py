"""CSV contracts retain Olist's original field names, including 'lenght'."""

FILES = {
    t: f"olist_{t}_dataset.csv"
    for t in [
        "customers",
        "sellers",
        "orders",
        "products",
        "order_items",
        "order_payments",
        "order_reviews",
    ]
}
FILES["category_translation"] = "product_category_name_translation.csv"
COLUMNS = {
    "customers": "customer_id customer_unique_id customer_zip_code_prefix customer_city customer_state".split(),
    "sellers": "seller_id seller_zip_code_prefix seller_city seller_state".split(),
    "orders": "order_id customer_id order_status order_purchase_timestamp order_approved_at order_delivered_carrier_date order_delivered_customer_date order_estimated_delivery_date".split(),
    "products": "product_id product_category_name product_name_lenght product_description_lenght product_photos_qty product_weight_g product_length_cm product_height_cm product_width_cm".split(),
    "order_items": "order_id order_item_id product_id seller_id shipping_limit_date price freight_value".split(),
    "order_payments": "order_id payment_sequential payment_type payment_installments payment_value".split(),
    "order_reviews": "review_id order_id review_score review_comment_title review_comment_message review_creation_date review_answer_timestamp".split(),
    "category_translation": "product_category_name product_category_name_english".split(),
}
KEYS = {
    "customers": ["customer_id"],
    "sellers": ["seller_id"],
    "orders": ["order_id"],
    "products": ["product_id"],
    "order_items": ["order_id", "order_item_id"],
    "order_payments": ["order_id", "payment_sequential"],
    "order_reviews": ["order_id", "review_id"],
    "category_translation": ["product_category_name"],
}
DATES = {
    "orders": COLUMNS["orders"][3:],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}
NUMERIC = {
    "products": COLUMNS["products"][2:],
    "order_items": ["order_item_id", "price", "freight_value"],
    "order_payments": ["payment_sequential", "payment_installments", "payment_value"],
    "order_reviews": ["review_score"],
}
MONEY = {"order_items": ["price", "freight_value"], "order_payments": ["payment_value"]}
REQUIRED = {t: set(KEYS[t]) for t in FILES}
REQUIRED["orders"].update(
    [
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_estimated_delivery_date",
    ]
)
REQUIRED["customers"].add("customer_unique_id")
REQUIRED["order_items"].update(
    ["product_id", "seller_id", "shipping_limit_date", "price", "freight_value"]
)
REQUIRED["order_payments"].update(NUMERIC["order_payments"] + ["payment_type"])
REQUIRED["order_reviews"].update(
    ["review_score", "review_creation_date", "review_answer_timestamp"]
)
RELATIONS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("order_payments", "order_id", "orders", "order_id"),
    ("order_reviews", "order_id", "orders", "order_id"),
]
STATUSES = {
    "created",
    "approved",
    "invoiced",
    "processing",
    "shipped",
    "delivered",
    "unavailable",
    "canceled",
}
