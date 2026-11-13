-- PK/FK/check constraints enforce hard contracts; these queries audit soft issues.
SELECT order_status,COUNT(*) AS orders FROM olist.orders GROUP BY order_status ORDER BY orders DESC;

SELECT 'orders_without_items' AS check_name,COUNT(*) AS n FROM olist.order_facts WHERE item_count IS NULL
UNION ALL SELECT 'orders_without_payments',COUNT(*) FROM olist.order_facts WHERE payment_total IS NULL
UNION ALL SELECT 'payment_mismatch_gt_1_cent',COUNT(*) FROM olist.order_facts WHERE ABS(payment_total-gross_value)>0.01
UNION ALL SELECT 'delivered_missing_timestamp',COUNT(*) FROM olist.orders WHERE order_status='delivered' AND order_delivered_customer_date IS NULL
UNION ALL SELECT 'delivery_before_purchase',COUNT(*) FROM olist.orders WHERE order_delivered_customer_date<order_purchase_timestamp
UNION ALL SELECT 'review_before_receipt',COUNT(*) FROM olist.order_facts WHERE review_answer_timestamp<order_delivered_customer_date;

-- review_id is reused across orders: composite PK is necessary.
SELECT review_id,COUNT(*) AS rows FROM olist.order_reviews GROUP BY review_id HAVING COUNT(*)>1 ORDER BY rows DESC,review_id;

SELECT p.product_category_name,COUNT(*) AS products
FROM olist.products p LEFT JOIN olist.category_translation t USING(product_category_name)
WHERE t.product_category_name IS NULL GROUP BY p.product_category_name ORDER BY products DESC;

-- All three counts must agree; joined order facts must retain raw order grain.
SELECT (SELECT COUNT(*) FROM olist.orders) AS raw_orders,COUNT(*) AS facts_rows,
 COUNT(DISTINCT order_id) AS unique_orders FROM olist.order_facts;
