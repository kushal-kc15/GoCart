from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


class ProductListPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Category.objects.create(name="Fruits & Veg", slug="fruits-veg")
        cls.sub = Category.objects.create(name="Fruits", slug="fruits", parent=cls.dept)
        # 25 products; prices repeat (100, 200, 300) so sorting by price has ties.
        for i in range(1, 26):
            Product.objects.create(
                category=cls.sub, name=f"Product {i:02d}", slug=f"product-{i:02d}",
                price=100 * (i % 3 + 1), stock=5,
            )
        cls.url = reverse("products:product_list")

    def _ids(self, response):
        return [p.id for p in response.context["page_obj"]]

    def _pagination_html(self, response):
        # Only the part of the page from the pagination nav onwards.
        return response.content.decode().split('class="pl-pagination"', 1)[1]

    def test_page_one_has_twenty_items(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"]), 20)
        self.assertEqual(response.context["page_obj"].number, 1)

    def test_page_two_has_the_rest(self):
        response = self.client.get(self.url, {"page": 2})
        self.assertEqual(len(response.context["page_obj"]), 5)

    def test_invalid_page_shows_page_one(self):
        response = self.client.get(self.url, {"page": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 1)

    def test_out_of_range_page_shows_last_page(self):
        response = self.client.get(self.url, {"page": 999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)

    def test_price_sort_is_stable_across_pages(self):
        page1 = self._ids(self.client.get(self.url, {"sort": "price_low", "page": 1}))
        page2 = self._ids(self.client.get(self.url, {"sort": "price_low", "page": 2}))
        all_ids = page1 + page2
        self.assertEqual(len(all_ids), 25)
        self.assertEqual(len(set(all_ids)), 25)  # no repeats, none missing

    def test_page_links_keep_filters(self):
        response = self.client.get(self.url, {
            "category": "fruits-veg", "sub": "fruits", "sort": "price_low", "q": "Product",
        })
        nav = self._pagination_html(response)
        for part in ("category=fruits-veg", "sub=fruits", "sort=price_low", "q=Product", "page=2"):
            self.assertIn(part, nav)

    def test_controls_hidden_when_one_page(self):
        response = self.client.get(self.url, {"q": "Product 01"})
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 1)
        self.assertNotContains(response, 'class="pl-pagination"')

    def test_previous_and_next_only_where_they_make_sense(self):
        first = self.client.get(self.url).content.decode()
        self.assertNotIn(">Previous<", first)
        self.assertIn(">Next<", first)

        last = self.client.get(self.url, {"page": 2}).content.decode()
        self.assertIn(">Previous<", last)
        self.assertNotIn(">Next<", last)


class ProductListPolishTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Category.objects.create(name="Fruits & Veg", slug="fruits-veg")
        cls.sub = Category.objects.create(name="Fruits", slug="fruits", parent=cls.dept)
        cls.apple = Product.objects.create(
            category=cls.sub, name="Apple", slug="apple", price=100, stock=20,
        )
        cls.url = reverse("products:product_list")

    # ---- step 1: return to the same card ----
    def test_card_has_anchor_id_and_next_points_back_to_it(self):
        response = self.client.get(self.url, {"page": 1})
        self.assertContains(response, f'id="product-{self.apple.id}"')
        self.assertContains(
            response,
            f'name="next" value="{self.url}?page=1#product-{self.apple.id}"',
        )

    # ---- step 2: cards ----
    def test_low_stock_hint(self):
        Product.objects.create(category=self.sub, name="Kiwi", slug="kiwi", price=50, stock=3)
        response = self.client.get(self.url)
        self.assertContains(response, "Only 3 left")
        self.assertContains(response, "In Stock")  # Apple has 20

    # ---- step 3: header area ----
    def test_product_count_singular_and_plural(self):
        html = self.client.get(self.url).content.decode()
        self.assertRegex(html, r"\b1 product\b(?!s)")  # singular, not "1 products"
        Product.objects.create(category=self.sub, name="Pear", slug="pear", price=60, stock=9)
        self.assertContains(self.client.get(self.url), "2 products")

    def test_breadcrumb_links_department_when_subcategory_selected(self):
        response = self.client.get(self.url, {"category": "fruits-veg", "sub": "fruits"})
        html = response.content.decode()
        crumb = html.split('class="pl-breadcrumb"', 1)[1].split("</nav>", 1)[0]
        self.assertIn('href="/"', crumb)
        self.assertIn(f'href="{self.url}?category=fruits-veg"', crumb)
        self.assertIn('<span class="current">Fruits</span>', crumb)
        self.assertContains(response, '<h1 class="pl-title">')

    def test_search_breadcrumb(self):
        html = self.client.get(self.url, {"q": "apple"}).content.decode()
        crumb = html.split('class="pl-breadcrumb"', 1)[1].split("</nav>", 1)[0]
        self.assertIn('<span class="current">Search</span>', crumb)

    # ---- step 6: pagination, sort anchor, empty states ----
    def test_page_links_jump_to_the_grid(self):
        for i in range(25):
            Product.objects.create(category=self.sub, name=f"Item {i:02d}", slug=f"item-{i}", price=10, stock=9)
        html = self.client.get(self.url).content.decode()
        nav = html.split('class="pl-pagination"', 1)[1].split("</nav>", 1)[0]
        self.assertIn("page=2#products", nav)
        self.assertIn('aria-current="page"', nav)
        self.assertIn('id="products"', html)

    def test_sort_form_jumps_to_the_grid_and_has_no_page_field(self):
        html = self.client.get(self.url, {"page": 1}).content.decode()
        form = html.split('class="pl-sort"', 1)[0].rsplit("<form", 1)[1]
        self.assertIn('action="#products"', form)
        sort_form = html.split('action="#products"', 1)[1].split("</form>", 1)[0]
        self.assertNotIn('name="page"', sort_form)

    def test_empty_state_uses_shared_style(self):
        response = self.client.get(self.url, {"q": "zzz"})
        self.assertContains(response, 'class="pl-empty gc-empty"')


class ProductDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        dept = Category.objects.create(name="Fruits & Veg", slug="fruits-veg")
        sub = Category.objects.create(name="Fruits", slug="fruits", parent=dept)
        cls.product = Product.objects.create(
            category=sub, name="Sweet Mango", slug="sweet-mango", price=120, stock=5,
        )
        cls.url = reverse("products:product_detail", args=["sweet-mango"])

    def test_buy_now_is_a_submit_button_in_the_cart_form(self):
        html = self.client.get(self.url).content.decode()
        form = html.split('class="add-to-cart-form"', 1)[1].split("</form>", 1)[0]
        self.assertIn('name="buy_now"', form)
        self.assertIn(">Buy Now<", form)
        self.assertIn(">Add to Cart<", form)

    def test_slim_breadcrumb_links_department_and_subcategory(self):
        response = self.client.get(self.url)
        self.assertContains(response, "?category=fruits-veg&sub=fruits")
        self.assertNotContains(response, "<h1>SHOP</h1>")
        self.assertContains(response, "<h1>Sweet Mango</h1>")

    def test_ratings_and_reviews_section_is_kept(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Rating and Reviews")
        self.assertContains(response, "Write a review")


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        drinks = Category.objects.create(name="Beverages", slug="beverages")
        hot = Category.objects.create(name="Hot Drinks", slug="hot-drinks", parent=drinks)
        snacks = Category.objects.create(name="Snacks", slug="snacks")
        biscuits = Category.objects.create(name="Biscuits", slug="biscuits", parent=snacks)

        def make(category, name, **extra):
            fields = {"price": 100, "stock": 5, **extra}
            return Product.objects.create(
                category=category, name=name, slug=name.lower().replace(" ", "-"), **fields
            )

        make(hot, "Green Tea")
        make(hot, "Black Tea")
        make(biscuits, "Tea Biscuit")          # other department
        make(biscuits, "Digestive")            # found only via its category names
        make(hot, "Lemon Tea", stock=0)        # out of stock: never shown
        make(hot, "Milk Tea", is_available=False)  # unavailable: never shown

        cls.url = reverse("products:product_list")
        cls.suggest_url = reverse("products:search_suggest")

    def _names(self, response):
        return sorted(p.name for p in response.context["page_obj"])

    # ---- results page ----
    def test_search_finds_products_across_departments(self):
        response = self.client.get(self.url, {"q": "tea"})
        self.assertEqual(self._names(response), ["Black Tea", "Green Tea", "Tea Biscuit"])
        self.assertContains(response, 'Results for "tea"')
        self.assertContains(response, "3 results")

    def test_search_matches_subcategory_and_department_names(self):
        by_sub = self.client.get(self.url, {"q": "biscuits"})
        self.assertEqual(self._names(by_sub), ["Digestive", "Tea Biscuit"])

        by_dept = self.client.get(self.url, {"q": "snacks"})
        self.assertEqual(self._names(by_dept), ["Digestive", "Tea Biscuit"])

    def test_search_ignores_category_filter(self):
        response = self.client.get(self.url, {"q": "tea", "category": "snacks"})
        self.assertEqual(len(response.context["page_obj"]), 3)

    def test_search_hides_strip_and_sidebar(self):
        response = self.client.get(self.url, {"q": "tea"})
        self.assertNotContains(response, 'class="pl-strip"')
        self.assertNotContains(response, 'class="pl-sidebar"')

    def test_empty_search_shows_normal_list(self):
        response = self.client.get(self.url, {"q": "   "})
        self.assertContains(response, 'class="pl-strip"')
        # First department alphabetically is Beverages: only its in-stock products
        self.assertEqual(self._names(response), ["Black Tea", "Green Tea"])

    def test_no_results_shows_message_and_link(self):
        response = self.client.get(self.url, {"q": "zzz"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No products found for "zzz".')
        self.assertContains(response, f'href="{self.url}">Browse all products')

    # ---- suggestions endpoint ----
    def test_suggest_ignores_one_character_query(self):
        response = self.client.get(self.suggest_url, {"q": "t"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})

    def test_suggest_without_query_returns_empty_list(self):
        self.assertEqual(self.client.get(self.suggest_url).json(), {"results": []})

    def test_suggest_returns_at_most_six_sorted_names(self):
        apples = Category.objects.get(slug="hot-drinks")
        for i in range(1, 9):
            Product.objects.create(
                category=apples, name=f"Apple {i}", slug=f"apple-{i}", price=50, stock=3
            )
        names = self.client.get(self.suggest_url, {"q": "apple"}).json()["results"]
        self.assertEqual(names, [f"Apple {i}" for i in range(1, 7)])

    def test_suggest_skips_unavailable_and_out_of_stock(self):
        names = self.client.get(self.suggest_url, {"q": "tea"}).json()["results"]
        self.assertEqual(names, ["Black Tea", "Green Tea", "Tea Biscuit"])
