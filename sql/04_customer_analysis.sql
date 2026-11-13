WITH customers AS (
 SELECT customer_unique_id,COUNT(*) AS frequency,SUM(revenue) AS monetary,
 MIN(order_purchase_timestamp) AS first_purchase,MAX(order_purchase_timestamp) AS last_purchase
 FROM olist.sales_orders GROUP BY customer_unique_id
), snapshot AS (
 SELECT MAX(order_purchase_timestamp)::date+1 AS as_of FROM olist.orders
)
SELECT c.*,s.as_of-c.last_purchase::date AS recency,
 ROW_NUMBER() OVER(ORDER BY monetary DESC,customer_unique_id) AS monetary_rank
FROM customers c CROSS JOIN snapshot s ORDER BY monetary_rank;

WITH customers AS (
 SELECT customer_unique_id,COUNT(*) AS frequency FROM olist.sales_orders GROUP BY customer_unique_id
)
SELECT COUNT(*) AS customers,COUNT(*) FILTER(WHERE frequency>=2) AS repeat_customers,
 100.0*COUNT(*) FILTER(WHERE frequency>=2)/NULLIF(COUNT(*),0) AS repeat_customer_pct FROM customers;

WITH sequenced AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY customer_unique_id ORDER BY order_purchase_timestamp,order_id) AS purchase_number
 FROM olist.sales_orders
)
SELECT CASE WHEN purchase_number=1 THEN 'First observed order' ELSE 'Repeat order' END AS buyer_type,
 COUNT(*) AS orders,SUM(revenue) AS revenue,AVG(revenue) AS aov
FROM sequenced GROUP BY 1 ORDER BY 1;
