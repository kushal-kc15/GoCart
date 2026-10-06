from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from django.contrib.auth import get_user_model

from config.views import server_error
from orders.models import Order, OrderItem
from products.models import Category, Product
from products.popular import popular_products


class HomePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Category.objects.create(name="Fruits & Veg", slug="fruits-veg")
        sub = Category.objects.create(name="Fruits", slug="fruits", parent=cls.dept)
        Product.objects.create(
            category=sub, name="Sweet Mango", slug="sweet-mango", price=120, unit="1 kg", stock=5, is_featured=True,
        )
        Product.objects.create(category=sub, name="Plain Apple", slug="plain-apple", price=90, stock=5)
        Product.objects.create(
            category=sub, name="Sold Out Pear", slug="sold-out-pear", price=80, stock=0, is_featured=True,
        )
        Product.objects.create(
            category=sub, name="Hidden Kiwi", slug="hidden-kiwi", price=80, stock=4,
            is_featured=True, is_available=False,
        )

    def test_categories_and_featured_products_render_from_database(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fruits &amp; Veg")
        self.assertContains(response, "Sweet Mango")
        self.assertContains(response, "Rs. 120")
        self.assertEqual(list(response.context["categories"]), [self.dept])  # only top-level departments

    def test_non_featured_out_of_stock_and_unavailable_products_are_hidden(self):
        response = self.client.get(reverse("home"))
        for name in ("Plain Apple", "Sold Out Pear", "Hidden Kiwi"):
            self.assertNotContains(response, name)

    def test_empty_states(self):
        Product.objects.all().delete()
        Category.objects.all().delete()
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No categories yet.")
        self.assertContains(response, "No featured products yet.")


class MostPopularTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        dept = Category.objects.create(name="Fruits & Veg", slug="fruits-veg")
        sub = Category.objects.create(name="Fruits", slug="fruits", parent=dept)

        def make(name, **extra):
            fields = {"price": 100, "stock": 5, **extra}
            return Product.objects.create(category=sub, name=name, slug=name.lower(), **fields)

        cls.apple = make("Apple")
        cls.banana = make("Banana")
        cls.cherry = make("Cherry")
        cls.dates = make("Dates", stock=0)               # out of stock
        cls.elder = make("Elderberry", is_available=False)  # unavailable
        cls.fig = make("Fig", is_featured=True)
        cls.user = get_user_model().objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )

    def _order(self, status, *lines):
        """Create an order with (product, quantity) lines."""
        order = Order.objects.create(user=self.user, status=status, total=0, address="Kathmandu")
        for product, quantity in lines:
            OrderItem.objects.create(order=order, product=product, quantity=quantity, price=product.price)

    def _popular_names(self):
        response = self.client.get(reverse("home"))
        return [p.name for p in response.context["popular_products"]]

    def test_ordered_by_quantity_sold(self):
        self._order(Order.Status.PENDING, (self.apple, 5))
        self._order(Order.Status.DELIVERED, (self.banana, 2))
        self.assertEqual(self._popular_names(), ["Apple", "Banana"])

    def test_cancelled_orders_are_not_counted(self):
        self._order(Order.Status.PENDING, (self.apple, 2))
        self._order(Order.Status.CANCELLED, (self.apple, 9))
        self._order(Order.Status.PENDING, (self.banana, 3))
        self._order(Order.Status.CANCELLED, (self.cherry, 10))  # only cancelled sales
        self.assertEqual(self._popular_names(), ["Banana", "Apple"])

    def test_out_of_stock_and_unavailable_are_excluded(self):
        self._order(Order.Status.PENDING, (self.dates, 50), (self.elder, 40), (self.apple, 1))
        self.assertEqual(self._popular_names(), ["Apple"])

    def test_falls_back_to_featured_when_no_sales(self):
        self.assertEqual(self._popular_names(), ["Fig"])

    def test_falls_back_to_newest_when_no_sales_and_no_featured(self):
        Product.objects.filter(pk=self.fig.pk).update(is_featured=False)
        # Newest first, in-stock and available only
        self.assertEqual(self._popular_names(), ["Fig", "Cherry", "Banana", "Apple"])

    def test_at_most_eight(self):
        sub = self.apple.category
        for i in range(10):
            product = Product.objects.create(
                category=sub, name=f"Extra {i}", slug=f"extra-{i}", price=10, stock=5
            )
            self._order(Order.Status.PENDING, (product, 1))
        self.assertEqual(len(self._popular_names()), 8)

    def test_exclude_ids_skips_given_products(self):
        # The cart page leaves out what is already in the cart
        self._order(Order.Status.PENDING, (self.apple, 5))
        self._order(Order.Status.PENDING, (self.banana, 2))
        names = [p.name for p in popular_products(exclude_ids=[self.apple.id])]
        self.assertEqual(names, ["Banana"])

    def test_cards_have_buy_now_inside_the_cart_form(self):
        html = self.client.get(reverse("home")).content.decode()
        form = html.split('class="add-to-cart-form"', 1)[1].split("</form>", 1)[0]
        self.assertIn('name="buy_now"', form)
        self.assertIn(">Add to Cart<", form)


# The test runner already uses DEBUG=False; it is explicit here because
# with DEBUG=True Django shows its own debug 404 page instead of ours.
@override_settings(DEBUG=False)
class ErrorPageTests(TestCase):
    def test_unknown_url_uses_custom_404(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "dev/404.html")
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, reverse("products:product_list"), status_code=404)

    def test_missing_product_uses_custom_404(self):
        # get_object_or_404 in the product detail view goes through the same handler
        response = self.client.get(reverse("products:product_detail", args=["nope"]))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "dev/404.html")

    def test_500_page_is_standalone_and_uses_no_queries(self):
        # Call the handler directly: the test client re-raises real errors.
        request = RequestFactory().get("/")
        with self.assertNumQueries(0):
            response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, 'href="/"', status_code=500)
        self.assertNotIn("<header", response.content.decode())  # does not use base.html
