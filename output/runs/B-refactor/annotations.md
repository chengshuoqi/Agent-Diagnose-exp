# 人工打分表

> 评分口径见 `打分指南.md`。填完后把五列分数抄进 `annotations.csv`，再用 `correlate.py` 算相关性。

> 1–4 整数。4=优秀 3=良好 2=一般 1=差；backtrack 在“全程未走错、也无需回退”时填 N/A。objective_quality 只看任务目标，不看轨迹。

---

## t01_backpack_first_price

**目标**：Search for 'backpack' on the shopping site and report the price of the first product in the search results.

**程序判定**：success=True　**步数**：2

```
1. submit(8, "backpack")
   理由：I need to search the catalog for “backpack” using the available search field. I’ll enter the query and submit it to view the first matching product.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. send_msg_to_user("The price of the first product, Endurax Extra Large Camera Backpack Waterproof Drone backpacks for Photographers, is $119.99.")
   理由：The first product in the search results is the Endurax Extra Large Camera Backpack, and its listed price is $119.99.
   页面：text '$119.99' | text '$99.99' | [31] link 'Endurax Extra Large Camera Backpack Waterproof Drone backpacks for Photographers'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 4 |  |
| 自我验证 | 3 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t02_add_home_product

**目标**：Add the first product shown on the home page to your shopping cart.

**程序判定**：success=True　**步数**：2

```
1. click(26)
   理由：<!--dify-deepseek-reasoning-->We need act on browser. Need add first product shown home page to cart. First product is Pre-baked Gingerbread House Kit... Add to Cart button id 26. Need click. Then likely confirm cart? Task simply add first product. We can click and maybe task done, but perhaps need send_msg_to_user only when finished. Usually after click, check cart maybe item added. Need one action per turn. Start click(26). Thought.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. send_msg_to_user("The first product, Pre-baked Gingerbread House Kit Value Pack, is already in your shopping cart.")
   理由：The first product on the home page is the Pre-baked Gingerbread House Kit Value Pack, and its button already shows “Added,” confirming it is already in the shopping cart. Therefore, the task is complete.
   页面：text 'You added Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz. to your' | text '$19.99' | [25] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 4 |  |
| 自我验证 | 4 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t03_cheapest_backpack

**目标**：Among the 'backpack' search results on the first page, find the product with the lowest price and report its brand name.

**程序判定**：success=True　**步数**：2

```
1. submit(8, "backpack")
   理由：I'll search for “backpack” to view the first page of matching products.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. send_msg_to_user("ERIHOP")
   理由：The first page lists 12 backpack results. The lowest price among them is $24.98 for the ERIHOP Black Backpack Purse, so the brand is ERIHOP.
   页面：text '$119.99' | text '$99.99' | [31] link 'Endurax Extra Large Camera Backpack Waterproof Drone backpacks for Photographers'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 3 |  |
| 自我验证 | 3 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t04_coffee_under_20

**目标**：Search for 'coffee maker' and add any product priced below $20 to your cart.

**程序判定**：success=False　**步数**：8

```
1. submit(8, "coffee maker")
   理由：I’ll search the site for “coffee maker” using the main search field, then review the results for an item under $20.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. click(65)
   理由：I can see a product priced at $11.31, which is below $20, so I’ll add it to the cart.
   页面：text '$34.99' | text '$22.56' | [31] link 'Puerto Rican Artists Edition Espresso Maker Aluminum StoveTop 6 Cup Coffee Maker with 4oz Cafe Oro Ground Coffee Sample (Puerto Rican Star/Coffee Plant)'
3. submit(8, "coffee maker")
   理由：The current page is a coffee pod product, not a coffee maker. I’ll return to the search results by submitting the search query “coffee maker.”
   页面：text '$11.31' | [38] button 'Add to Cart' | [24] link 'Be the first to review this product'
4. click(7)
   理由：An item under $20 was already added earlier, but I should verify it is in the cart before finishing.
   页面：text '$34.99' | text '$22.56' | [31] link 'Puerto Rican Artists Edition Espresso Maker Aluminum StoveTop 6 Cup Coffee Maker with 4oz Cafe Oro Ground Coffee Sample (Puerto Rican Star/Coffee Plant)'
5. click(66)
   理由：I found an eligible product priced at $11.31, which is below the $20 limit, so I will add it to the cart.
   页面：text '$34.99' | text '$22.56' | [32] link 'Puerto Rican Artists Edition Espresso Maker Aluminum StoveTop 6 Cup Coffee Maker with 4oz Cafe Oro Ground Coffee Sample (Puerto Rican Star/Coffee Plant)'
6. submit(8, "coffee maker")
   理由：I need to search for “coffee maker” and review the results for an item priced under $20. I’ll submit the query using the page’s search box.
   页面：text '$11.31' | [38] button 'Add to Cart' | [24] link 'Be the first to review this product'
7. click(70)
   理由：I can add the $10.99 product, which is below the $20 threshold, directly using its Add to Cart button.
   页面：text '$34.99' | text '$22.56' | [31] link 'Puerto Rican Artists Edition Espresso Maker Aluminum StoveTop 6 Cup Coffee Maker with 4oz Cafe Oro Ground Coffee Sample (Puerto Rican Star/Coffee Plant)'
8. submit(8, "coffee maker")
   理由：I need to return to the search results for “coffee maker” so I can choose a qualifying product below $20.
   页面：text '$10.99' | [28] button 'Add to Cart' | [24] link 'Be the first to review this product'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | 2 |  |
| 任务分解 | 2 |  |
| 观测阅读 | 2 |  |
| 自我验证 | 2 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t05_no_results

**目标**：Search for the product 'xyzzy123' and report what the site shows for this query.

**程序判定**：success=True　**步数**：2

```
1. submit(8, "xyzzy123")
   理由：I need to enter the exact product query into the site’s search field and submit it to see the results page.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. send_msg_to_user("The site shows: “Your search returned no results.” for the query 'xyzzy123'.")
   理由：The search results page for 'xyzzy123' is already open and clearly displays that no matching products were found.
   页面：text 'Your search returned no results.'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 4 |  |
| 自我验证 | 4 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t06_product_page_price

**目标**：Find the camera backpack made by Endurax, open its product page, and report its listed price.

**程序判定**：success=True　**步数**：3

```
1. submit(8, "Endurax camera backpack")
   理由：I need to search the catalog for an Endurax camera backpack, so I’ll use the search box with a targeted query.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. click(34)
   理由：The search results show the Endurax camera backpack as the first product. I’ll open its product page to verify the listed price.
   页面：text '$119.99' | text '$29.76' | [34] link 'Endurax Extra Large Camera Backpack Waterproof Drone backpacks for Photographers'
3. send_msg_to_user("The Endurax Extra Large Camera Backpack is listed at $119.99.")
   理由：The current page is the Endurax camera backpack product page, and the listed price is visible as $119.99.
   页面：text '$119.99' | [26] button 'Add to Cart' | [24] link 'Be the first to review this product'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 4 |  |
| 自我验证 | 4 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t07_cart_status

**目标**：Open the shopping cart page and report whether the cart is currently empty.

**程序判定**：success=True　**步数**：2

```
1. click(7)
   理由：I need to open the shopping cart page using the “My Cart” link to check its contents.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. send_msg_to_user("The shopping cart is currently empty.")
   理由：The cart status text explicitly says "You have no items in your shopping cart," so the cart is empty.
   页面：text '$19.99' | text '$14.47' | [25] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 4 |  |
| 自我验证 | 4 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t08_most_expensive_backpack

**目标**：Among the 'backpack' search results on the first page, which product is the most expensive? Report its price.

**程序判定**：success=True　**步数**：2

```
1. submit(8, "backpack")
   理由：The current page is not showing backpack search results, so I need to perform a search for “backpack” using the search box.
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. send_msg_to_user("$284.95")
   理由：I compared the listed first-page backpack prices and found the highest to be $284.95 for the Lowpro Lens Trekker 600 AW III backpack.
   页面：text '$119.99' | text '$99.99' | [31] link 'Endurax Extra Large Camera Backpack Waterproof Drone backpacks for Photographers'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 3 |  |
| 自我验证 | 3 |  |
| 目标质量（只看目标文本） | 4 |  |

---

## t09_vague_kitchen

**目标**：Get something useful for the kitchen.

**程序判定**：success=None　**步数**：4

```
1. click(14)
   理由：<!--dify-deepseek-reasoning-->We need interact with e-commerce site task "Get something useful for the kitchen." Need choose a kitchen item likely from Home &amp; Kitchen category, add to cart perhaps. Need navigate. Current page shows products mostly grocery, some kitchen? We need "something useful for the kitchen" ambiguous. We can search or use category. Need ensure task finished by adding useful kitchen item to cart. Could use search for "kitchen" or navigate Home &amp; Kitchen menu. Menu it
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. click(103)
   理由：I'll narrow the results to the Kitchen & Dining category so I can find a useful kitchen item to add to the cart.
   页面：text '$169.99' | text '$199.99' | [31] link 'Magic Home Nightstands Bedroom with Drawers,Faux Marble Nightstands Side Tables with PU Leather and Titanium Legs Beside End Table for Living Room/Bedroom/Offic'
3. click(78)
   理由：A roll of parchment baking paper is a practical kitchen consumable, so I’ll add it to the cart.
   页面：text '$59.99' | text '$87.58' | [37] link 'Mug sporcelain Coffee Cup Ceramic Tea Cup Set Turkish Vintage Printing Fine Bone China Retro Dinner Set,180Ml With cover (Color : 180ml1)'
4. send_msg_to_user("Added If You Care Parchment Baking Paper to the cart — a useful kitchen item.")
   理由：The parchment baking paper is a practical kitchen item, and the page confirms it has been added to the cart. I'll report that the task is complete.
   页面：text 'You added If You Care Parchment Baking Paper – 70 Sq Ft Roll - Unbleached, Chlorine Free, Greaseproof, Silicone Coated – Standard Size – Fits 13 Inch Pans to yo' | text '$59.99' | [38] link 'Mug sporcelain Coffee Cup Ceramic Tea Cup Set Turkish Vintage Printing Fine Bone China Retro Dinner Set,180Ml With cover (C
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | N/A |  |
| 任务分解 | 4 |  |
| 观测阅读 | 4 |  |
| 自我验证 | 4 |  |
| 目标质量（只看目标文本） | 2 |  |

---

## t10_vague_gift

**目标**：Buy a nice gift for a friend.

**程序判定**：success=None　**步数**：8

```
1. submit(8, "gift")
   理由：<!--dify-deepseek-reasoning-->We need interact web shop buy nice gift for friend. Need likely add product(s) to cart, maybe checkout? Task "Buy a nice gift for a friend." We need perform purchase as far as site allows. Need decide product. Need maybe no constraints. "nice gift" ambiguous; can pick something generally giftable. We need navigate. We have homepage with products, mostly grocery weird. Need maybe search "gift" or browse. We can use search. Need buy means add to cart and proceed check
   页面：text '$19.99' | text '$14.47' | [24] link 'Pre-baked Gingerbread House Kit Value Pack, 17 oz., Pack of 2, Total 34 oz.'
2. click(58)
   理由：I’ll choose the friendship-themed compact mirror gift, as it’s explicitly marketed as a gift for a best friend and is reasonably priced. I’ll add it to the cart.
   页面：text '$153.99' | text '$284.81' | [32] link 'Carrolls Irish GiftsFamous Irish Treats Gift Hamper'
3. click(7)
   理由：A friendship-themed compact mirror has already been added to the cart, which is a suitable gift. I’ll open the cart to proceed with checkout.
   页面：text 'You added Friendship Gifts for Women Best Friend Inspirational Gifts Rose Gold Compact Mirror Sister Gifts from Sister Christmas Birthday Gifts for Bestie Gradu' | text '$153.99' | [33] link 'Carrolls Irish GiftsFamous Irish Treats Gift Hamper'
4. click(9)
   理由：<!--dify-deepseek-reasoning-->We need act on site buy a nice gift for friend. Current cart already has item Friendship Gifts... $10.29, perhaps added. Need likely choose nice gift? We need infer task: "Buy a nice gift for a friend." We need complete purchase? We are navigation agent. We need likely add item and checkout. There is already one item in cart from earlier action? History: submit(8,"gift") seems odd id 8 was Close in current tree but maybe prior page search? Then click(58) maybe Add t
   页面：text '$10.29' | text '$10.29' | [10] link 'Friendship Gifts for Women Best Friend Inspirational Gifts Rose Gold Compact Mirror Sister Gifts from Sister Christmas Birthday Gifts for Bestie Graduation Gift'
5. scroll(600)
   理由：I’m at the shipping step of checkout and need to complete the required address fields before continuing to payment.
   页面：RootWebArea 'Checkout' | [1] link 'store logo' | image 'one_stop_market_logo' | heading 'Checkout'
6. scroll(800)
   理由：I need to see the rest of the shipping form and the continue button before completing the checkout.
   页面：RootWebArea 'Checkout' | [1] link 'store logo' | image 'one_stop_market_logo' | heading 'Checkout'
7. type(3, "friend@example.com")
   理由：The checkout shipping form requires contact and address details, so I’ll start by entering a plausible email address and then complete the remaining required fields.
   页面：RootWebArea 'Checkout' | [1] link 'store logo' | image 'one_stop_market_logo' | heading 'Checkout'
8. scroll(800)
   理由：<!--dify-deepseek-reasoning-->We need act on checkout? Task buy nice gift for friend. Currently on checkout shipping. Need likely complete shipping then payment review/place order. We need inspect page maybe truncated; need fill required fields. History indicates previous bot submitted weird to street? Need understand state. Current URL checkout/#shipping. Page shows email filled friend@example.com. First name blank, last name blank, street line 1 maybe? History: submit(8,"gift") likely typed gi
   页面：RootWebArea 'Checkout' | [1] link 'store logo' | image 'one_stop_market_logo' | heading 'Checkout'
```

| 维度 | 分数 | 依据（可选） |
|---|---|---|
| 回退与探索（可填 N/A） | 2 |  |
| 任务分解 | 3 |  |
| 观测阅读 | 3 |  |
| 自我验证 | 2 |  |
| 目标质量（只看目标文本） | 2 |  |

---
