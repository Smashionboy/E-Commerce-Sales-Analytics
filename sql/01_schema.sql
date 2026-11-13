-- Dedicated schema only. DDL and reload run in one transaction in src.load_data.
CREATE SCHEMA IF NOT EXISTS olist;
CREATE TABLE IF NOT EXISTS olist.customers (
 customer_id text PRIMARY KEY, customer_unique_id text NOT NULL,
 customer_zip_code_prefix text, customer_city text, customer_state text
);
CREATE INDEX IF NOT EXISTS idx_customer_unique ON olist.customers(customer_unique_id);
CREATE TABLE IF NOT EXISTS olist.sellers (
 seller_id text PRIMARY KEY, seller_zip_code_prefix text, seller_city text, seller_state text
);
CREATE TABLE IF NOT EXISTS olist.category_translation (
 product_category_name text PRIMARY KEY, product_category_name_english text
);
-- Some real categories have no translation: intentionally no FK to translation.
CREATE TABLE IF NOT EXISTS olist.products (
 product_id text PRIMARY KEY, product_category_name text,
 product_name_lenght integer, product_description_lenght integer, product_photos_qty integer,
 product_weight_g integer, product_length_cm integer, product_height_cm integer, product_width_cm integer
);
CREATE TABLE IF NOT EXISTS olist.orders (
 order_id text PRIMARY KEY, customer_id text NOT NULL REFERENCES olist.customers,
 order_status text NOT NULL CHECK(order_status IN
 ('created','approved','invoiced','processing','shipped','delivered','unavailable','canceled')),
 order_purchase_timestamp timestamp NOT NULL, order_approved_at timestamp,
 order_delivered_carrier_date timestamp, order_delivered_customer_date timestamp,
 order_estimated_delivery_date timestamp NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_purchase ON olist.orders(order_purchase_timestamp);
CREATE TABLE IF NOT EXISTS olist.order_items (
 order_id text REFERENCES olist.orders, order_item_id integer CHECK(order_item_id>0),
 product_id text NOT NULL REFERENCES olist.products, seller_id text NOT NULL REFERENCES olist.sellers,
 shipping_limit_date timestamp NOT NULL, price numeric(14,2) NOT NULL CHECK(price>=0),
 freight_value numeric(14,2) NOT NULL CHECK(freight_value>=0), PRIMARY KEY(order_id,order_item_id)
);
CREATE TABLE IF NOT EXISTS olist.order_payments (
 order_id text REFERENCES olist.orders, payment_sequential integer CHECK(payment_sequential>0),
 payment_type text NOT NULL, payment_installments integer NOT NULL CHECK(payment_installments>=0),
 payment_value numeric(14,2) NOT NULL CHECK(payment_value>=0), PRIMARY KEY(order_id,payment_sequential)
);
-- review_id alone is not unique in the actual release.
CREATE TABLE IF NOT EXISTS olist.order_reviews (
 review_id text NOT NULL, order_id text REFERENCES olist.orders,
 review_score integer NOT NULL CHECK(review_score BETWEEN 1 AND 5),
 review_comment_title text, review_comment_message text,
 review_creation_date timestamp NOT NULL, review_answer_timestamp timestamp NOT NULL,
 PRIMARY KEY(order_id,review_id)
);
CREATE OR REPLACE VIEW olist.order_facts AS
WITH items AS (
 SELECT order_id,SUM(price) AS revenue,SUM(freight_value) AS freight,COUNT(*) AS item_count
 FROM olist.order_items GROUP BY order_id
), payments AS (
 SELECT order_id,SUM(payment_value) AS payment_total,COUNT(*) AS payment_rows
 FROM olist.order_payments GROUP BY order_id
), reviews AS (
 SELECT order_id,review_score,review_answer_timestamp,
 ROW_NUMBER() OVER(PARTITION BY order_id ORDER BY review_answer_timestamp DESC,
   review_creation_date DESC,review_id DESC) AS rn
 FROM olist.order_reviews
)
SELECT o.*,c.customer_unique_id,c.customer_state,
 i.revenue,i.freight,i.revenue+i.freight AS gross_value,i.item_count,
 p.payment_total,p.payment_rows,r.review_score,r.review_answer_timestamp,
 EXTRACT(EPOCH FROM (o.order_delivered_customer_date-o.order_purchase_timestamp))/86400.0 AS delivery_days,
 o.order_delivered_customer_date::date-o.order_estimated_delivery_date::date AS late_days,
 o.order_delivered_customer_date::date>o.order_estimated_delivery_date::date AS is_late
FROM olist.orders o
JOIN olist.customers c USING(customer_id)
LEFT JOIN items i USING(order_id)
LEFT JOIN payments p USING(order_id)
LEFT JOIN reviews r ON r.order_id=o.order_id AND r.rn=1;
CREATE OR REPLACE VIEW olist.sales_orders AS
SELECT * FROM olist.order_facts WHERE order_status='delivered' AND item_count>0;
