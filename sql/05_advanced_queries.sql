-- Pareto curve for category GMV, including a cumulative window with explicit frame.
WITH category AS (
 SELECT COALESCE(t.product_category_name_english,p.product_category_name,'unknown') AS category,SUM(i.price) AS revenue
 FROM olist.order_items i JOIN olist.sales_orders s USING(order_id)
 JOIN olist.products p USING(product_id)
 LEFT JOIN olist.category_translation t USING(product_category_name) GROUP BY 1
)
SELECT *,100*SUM(revenue) OVER(ORDER BY revenue DESC,category ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
 /NULLIF(SUM(revenue) OVER(),0) AS cumulative_pct FROM category ORDER BY revenue DESC,category;

-- Descriptive delivery/review sample: review response after receipt, nonnegative transit.
-- One earliest eligible order per customer matches the inferential Python sample.
WITH eligible AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY customer_unique_id ORDER BY order_purchase_timestamp,order_id) AS rn
 FROM olist.sales_orders WHERE delivery_days>=0 AND is_late IS NOT NULL
 AND review_score IS NOT NULL AND review_answer_timestamp>=order_delivered_customer_date
)
SELECT is_late,COUNT(*) AS n,AVG(review_score) AS mean_score,
 PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY review_score) AS median_score,
 AVG((review_score<=2)::integer) AS low_score_rate
FROM eligible WHERE rn=1 GROUP BY is_late ORDER BY is_late;

-- Reconciliation: difference is diagnostic, not an instruction to replace product GMV.
SELECT order_id,revenue,freight,payment_total,payment_total-gross_value AS discrepancy
FROM olist.order_facts WHERE ABS(payment_total-gross_value)>0.01
ORDER BY ABS(payment_total-gross_value) DESC,order_id LIMIT 20;
