SELECT COUNT(*) AS orders,COALESCE(SUM(revenue),0) AS product_gmv_brl,
 AVG(revenue) AS aov_brl,AVG(item_count) AS mean_items_per_order,
 COUNT(DISTINCT customer_unique_id) AS customers FROM olist.sales_orders;

-- Include zero-order internal months so LAG means previous calendar month.
WITH base AS (
 SELECT DATE_TRUNC('month',order_purchase_timestamp)::date AS month,
 SUM(revenue) AS revenue,COUNT(*) AS orders,SUM(item_count) AS items
 FROM olist.sales_orders GROUP BY 1
), calendar AS (
 SELECT GENERATE_SERIES(MIN(month),MAX(month),INTERVAL '1 month')::date AS month FROM base
), monthly AS (
 SELECT c.month,COALESCE(b.revenue,0) AS revenue,COALESCE(b.orders,0) AS orders,
 b.revenue/NULLIF(b.orders,0) AS aov,b.items::numeric/NULLIF(b.orders,0) AS items_per_order
 FROM calendar c LEFT JOIN base b USING(month)
)
SELECT *,100*(revenue/NULLIF(LAG(revenue) OVER(ORDER BY month),0)-1) AS revenue_mom_pct,
 100*(orders::numeric/NULLIF(LAG(orders) OVER(ORDER BY month),0)-1) AS orders_mom_pct
FROM monthly ORDER BY month;

-- Item grain: sums are safe; category order counts are NOT additive across categories.
SELECT COALESCE(t.product_category_name_english,p.product_category_name,'unknown') AS category,
 SUM(i.price) AS revenue,COUNT(*) AS items,COUNT(DISTINCT i.order_id) AS orders
FROM olist.order_items i JOIN olist.sales_orders s USING(order_id)
JOIN olist.products p USING(product_id)
LEFT JOIN olist.category_translation t USING(product_category_name)
GROUP BY 1 ORDER BY revenue DESC,category;
