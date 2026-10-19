import json
import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import date, datetime, time, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime
from urllib.parse import parse_qs, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo
from pathlib import Path

from gestionale.gestionale import (
    AppError,
    OrderItem,
    ParsedOrder,
    _message_body,
    _next_recurring_date,
    build_calendar_url,
    build_maps_urls,
    check_mail,
    confirm_order,
        disable_recurring_schedule,
        get_delivery_load_config,
    initialize_database,
    list_stock,
    list_mail_folders,
    mark_order_delivered,
    open_database,
    parse_order_email,
    prepare_order,
    set_stock,
    save_delivery_load_config,
    sync_catalog,
    OrderNotReady,
    voucher_validation_status,
)
from gestionale.gestionale_web import (
    _allocate_vehicle_loads,
    _group_route_orders_by_city,
    _plan_single_vehicle_tours,
    create_server,
)


ROME = ZoneInfo("Europe/Rome")


class GestionaleTests(unittest.TestCase):
    def setUp(self):
        self.products = {
            "carta-igienica": {
                "id": "carta-igienica",
                "name": "Carta igienica lavanda",
                "available": True,
            }
        }
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        initialize_database(self.connection)
        sync_catalog(self.connection, list(self.products.values()))
        self.site = {
            "brand": "Cartaway",
            "tech_voucher": {"percent": 25, "maximum_amount": 25, "validity_days": 60},
            "recurring_order": {
                "tech_voucher_percent": 50,
                "tech_voucher_validity_days": 90,
            },
        }

    def tearDown(self):
        self.connection.close()

    def test_initialize_database_migrates_existing_orders_table(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute(
                "CREATE TABLE orders (order_id TEXT PRIMARY KEY, voucher_code TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE products (product_id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                "catalog_available INTEGER NOT NULL, quantity INTEGER, updated_at TEXT NOT NULL)"
            )
            initialize_database(connection)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(orders)")}
            product_columns = {row[1] for row in connection.execute("PRAGMA table_info(products)")}
        finally:
            connection.close()
        self.assertIn("preferred_delivery_date", columns)
        self.assertIn("preferred_delivery_time", columns)
        self.assertIn("request_details_json", columns)
        self.assertIn("confirmation_status", columns)
        self.assertIn("delivery_date", columns)
        self.assertIn("delivery_status", columns)
        self.assertIn("delivered_at", columns)
        self.assertIn("recurring_enabled", columns)
        self.assertIn("recurring_frequency_days", columns)
        self.assertIn("recurring_fixed_day", columns)
        self.assertIn("next_recurring_delivery_date", columns)
        self.assertIn("last_delivered_date", columns)
        self.assertIn("stock_group", product_columns)
        self.assertIn("stock_units_per_package", product_columns)
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertIn("delivery_load_volumes", tables)
        self.assertIn("delivery_vehicles", tables)
        self.assertIn("shared_stock", tables)

    def test_delivery_load_config_persists_volumes_and_vehicle_capacities(self):
        saved = save_delivery_load_config(
            self.connection,
            {"carta-igienica": 2.5},
            [{"name": "Furgone 1", "capacity_liters": 1200}],
        )

        self.assertEqual(
            saved,
            {
                "product_volumes": {"carta-igienica": 2.5},
                "vehicles": [{"name": "Furgone 1", "capacity_liters": 1200.0}],
            },
        )
        self.assertEqual(get_delivery_load_config(self.connection), saved)
        with self.assertRaisesRegex(AppError, "duplicato"):
            save_delivery_load_config(
                self.connection,
                {"carta-igienica": 2.5},
                [
                    {"name": "Furgone 1", "capacity_liters": 1000},
                    {"name": "furgone 1", "capacity_liters": 900},
                ],
            )
        self.assertEqual(get_delivery_load_config(self.connection), saved)

    def test_stock_is_shared_across_product_pack_sizes(self):
        product_variants = [
            {
                "id": "splash-2-rolls",
                "name": "Asciugatutto Splash · 2 rotoli",
                "unit": {"quantity": 2, "measure": "rotoli"},
            },
            {
                "id": "splash-6-rolls",
                "name": "Asciugatutto Splash · 6 rotoli",
                "unit": {"quantity": 6, "measure": "rotoli"},
            },
        ]
        sync_catalog(self.connection, product_variants)
        set_stock(self.connection, "splash-2-rolls", 3)
        set_stock(self.connection, "splash-6-rolls", 2)
        sync_catalog(
            self.connection,
            [{**product, "stock_group": "splash-rolls"} for product in product_variants],
        )
        set_stock(self.connection, "splash-2-rolls", 1, add=True)

        stock = {row["product_id"]: row for row in list_stock(self.connection)}
        self.assertEqual(stock["splash-2-rolls"]["quantity"], 10)
        self.assertEqual(stock["splash-6-rolls"]["quantity"], 3)
        self.assertEqual(stock["splash-2-rolls"]["shared_quantity"], 20)
        self.assertEqual(stock["splash-6-rolls"]["shared_unit"], "rotoli")

        order = self._order("ORD-SHARED-STOCK-6", "cliente@example.org", "+39 333 1234567")
        order.items = [
            OrderItem("splash-2-rolls", "Asciugatutto Splash · 2 rotoli", 1),
            OrderItem("splash-6-rolls", "Asciugatutto Splash · 6 rotoli", 1),
        ]
        prepared = prepare_order(self.connection, order, self.site)
        self.assertEqual(prepared["status"], "disponibile")
        with patch("gestionale.gestionale.send_email"):
            confirm_order(self.connection, order.order_id, self.site)
        mark_order_delivered(self.connection, order.order_id)

        stock = {row["product_id"]: row for row in list_stock(self.connection)}
        self.assertEqual(stock["splash-2-rolls"]["shared_quantity"], 12)
        self.assertEqual(stock["splash-2-rolls"]["quantity"], 6)
        self.assertEqual(stock["splash-6-rolls"]["quantity"], 2)

        shortage_order = self._order("ORD-SHARED-STOCK-SHORT", "altro@example.org", "+39 333 7654321")
        shortage_order.items = [OrderItem("splash-6-rolls", "Asciugatutto Splash · 6 rotoli", 3)]
        shortage = prepare_order(self.connection, shortage_order, self.site)
        self.assertEqual(shortage["status"], "disponibilita_insufficiente")

    def test_delivery_uses_confirmed_package_size_after_catalog_change(self):
        product_variants = [
            {
                "id": "splash-2-rolls",
                "name": "Asciugatutto Splash · 2 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 2, "measure": "rotoli"},
            },
            {
                "id": "splash-6-rolls",
                "name": "Asciugatutto Splash · 6 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 6, "measure": "rotoli"},
            },
        ]
        sync_catalog(self.connection, product_variants)
        set_stock(self.connection, "splash-2-rolls", 3)
        order = self._order("ORD-SHARED-FACTOR-SNAPSHOT", "cliente@example.org", "+39 333 1234567")
        order.items = [OrderItem("splash-2-rolls", "Asciugatutto Splash · 2 rotoli", 1)]
        prepare_order(self.connection, order, self.site)
        with patch("gestionale.gestionale.send_email"):
            confirm_order(self.connection, order.order_id, self.site)

        sync_catalog(
            self.connection,
            [{**product, "unit": {**product["unit"], "quantity": 4}}
             if product["id"] == "splash-2-rolls" else product
             for product in product_variants],
        )
        mark_order_delivered(self.connection, order.order_id)

        remaining = self.connection.execute(
            "SELECT quantity FROM shared_stock WHERE stock_group = ?", ("splash-rolls",)
        ).fetchone()["quantity"]
        self.assertEqual(remaining, 4)

    def test_catalog_cannot_change_stock_group_with_remaining_quantity(self):
        product_variants = [
            {
                "id": "splash-2-rolls",
                "name": "Asciugatutto Splash · 2 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 2, "measure": "rotoli"},
            },
            {
                "id": "splash-6-rolls",
                "name": "Asciugatutto Splash · 6 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 6, "measure": "rotoli"},
            },
        ]
        sync_catalog(self.connection, product_variants)
        set_stock(self.connection, "splash-2-rolls", 3)

        with self.assertRaisesRegex(AppError, "imposta prima la giacenza condivisa a 0"):
            sync_catalog(
                self.connection,
                [{**product_variants[0], "stock_group": ""}, product_variants[1]],
            )
        with self.assertRaisesRegex(AppError, "imposta prima la giacenza a 0"):
            sync_catalog(
                self.connection,
                [
                    {
                        **product,
                        "unit": {**product["unit"], "measure": "confezioni"},
                    }
                    for product in product_variants
                ],
            )

        stock = {row["product_id"]: row for row in list_stock(self.connection)}
        self.assertEqual(stock["splash-2-rolls"]["shared_quantity"], 6)
        self.assertEqual(stock["splash-2-rolls"]["stock_group"], "splash-rolls")

    def test_delivery_refuses_stock_group_changed_after_order_confirmation(self):
        product_variants = [
            {
                "id": "splash-2-rolls",
                "name": "Asciugatutto Splash · 2 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 2, "measure": "rotoli"},
            },
            {
                "id": "splash-6-rolls",
                "name": "Asciugatutto Splash · 6 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 6, "measure": "rotoli"},
            },
        ]
        sync_catalog(self.connection, product_variants)
        set_stock(self.connection, "splash-2-rolls", 3)
        order = self._order("ORD-SHARED-GROUP-CHANGED", "cliente@example.org", "+39 333 1234567")
        order.items = [OrderItem("splash-2-rolls", "Asciugatutto Splash · 2 rotoli", 1)]
        prepare_order(self.connection, order, self.site)
        with patch("gestionale.gestionale.send_email"):
            confirm_order(self.connection, order.order_id, self.site)

        set_stock(self.connection, "splash-2-rolls", 0)
        changed_unit_variants = [
            {
                **product,
                "unit": {**product["unit"], "measure": "confezioni"},
            }
            for product in product_variants
        ]
        sync_catalog(self.connection, changed_unit_variants)

        with self.assertRaisesRegex(OrderNotReady, "unità di giacenza è cambiata"):
            mark_order_delivered(self.connection, order.order_id)

        sync_catalog(
            self.connection,
            [
                {**changed_unit_variants[0], "stock_group": "splash-rolls-new"},
                changed_unit_variants[1],
            ],
        )

        with self.assertRaisesRegex(OrderNotReady, "gruppo di giacenza è cambiato"):
            mark_order_delivered(self.connection, order.order_id)

        quantities = {
            row["stock_group"]: row["quantity"]
            for row in self.connection.execute("SELECT stock_group, quantity FROM shared_stock")
        }
        self.assertEqual(quantities["splash-rolls"], 0)
        self.assertEqual(quantities["splash-rolls-new"], 0)

    def test_adding_standalone_stock_to_existing_group_preserves_quantity(self):
        shared_products = [
            {
                "id": "splash-2-rolls",
                "name": "Asciugatutto Splash · 2 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 2, "measure": "rotoli"},
            },
            {
                "id": "splash-6-rolls",
                "name": "Asciugatutto Splash · 6 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 6, "measure": "rotoli"},
            },
        ]
        standalone_product = {
            "id": "splash-3-rolls",
            "name": "Asciugatutto Splash · 3 rotoli",
            "unit": {"quantity": 3, "measure": "rotoli"},
        }
        sync_catalog(self.connection, [*shared_products, standalone_product])
        set_stock(self.connection, "splash-2-rolls", 3)
        set_stock(self.connection, "splash-3-rolls", 2)

        sync_catalog(
            self.connection,
            [*shared_products, {**standalone_product, "stock_group": "splash-rolls"}],
        )

        stock = {row["product_id"]: row for row in list_stock(self.connection)}
        self.assertEqual(stock["splash-2-rolls"]["shared_quantity"], 12)
        self.assertEqual(stock["splash-3-rolls"]["quantity"], 4)

    def test_parses_order_rows_and_customer_fields_from_template_email(self):
        email = EmailMessage()
        email["From"] = "noreply@cartaway.it"
        email["To"] = "cliente@example.org"
        email["Subject"] = "Riepilogo richiesta #ORD-1234 - Cartaway"
        email["Date"] = format_datetime(datetime(2026, 7, 8, 10, 0, tzinfo=ROME))
        email.add_alternative(
            """
            <h2>Prodotti</h2>
            <table><tr>
              <td><a href="https://cartaway.it/prodotto.html?id=carta-igienica"><strong>Carta igienica lavanda</strong></a></td>
              <td>Carta igienica lavanda<div>Quantità: 2</div></td>
              <td><strong>€ 6,00</strong><div>€ 3,00 / unità</div></td>
            </tr></table>
            <table>
              <tr><td>Nome</td><td>Mario Bianchi</td></tr>
              <tr><td>Email</td><td>cliente@example.org</td></tr>
              <tr><td>Telefono</td><td>+39 333 1234567</td></tr>
              <tr><td>Indirizzo</td><td>Via Roma 4, Montoro</td></tr>
              <tr><td>Data preferita</td><td>09/07/2026</td></tr>
              <tr><td>Preferenza di consegna</td><td>Una data e una fascia oraria specifiche: dalle 10:00 alle 12:00</td></tr>
              <tr><td>Note</td><td>Citofono Bianchi</td></tr>
              <tr><td>Zona</td><td>Zona 01 · Montoro</td></tr>
              <tr><td>Tempo indicativo</td><td>Entro circa 2 ore</td></tr>
              <tr><td>Richiesta fattura</td><td>Sì</td></tr>
              <tr><td>Ragione sociale</td><td>Cartaway SRL</td></tr>
              <tr><td>Partita IVA</td><td>01234567890</td></tr>
              <tr><td>Codice SDI o PEC</td><td>ABC1234</td></tr>
              <tr><td>Attivo</td><td>No</td></tr>
              <tr><td>Frequenza</td><td>Mensile</td></tr>
              <tr><td>Giorno richiesto</td><td>10</td></tr>
              <tr><td>Prezzo bloccato</td><td>3 mesi</td></tr>
              <tr><td>Codice</td><td>BT-12345678-ABCD</td></tr>
              <tr><td>Valore stimato</td><td>€ 5,00</td></tr>
            </table>
                        <table>
                            <tr><td></td><td>Prodotti (IVA incl.)</td><td>€ 20,00</td></tr>
                            <tr><td></td><td>Sconto ricorrente</td><td>Nessuno</td></tr>
                            <tr><td></td><td>Consegna</td><td>€ 3,00</td></tr>
                            <tr><td></td><td>IVA prodotti</td><td>Inclusa</td></tr>
                            <tr><td></td><td>Totale</td><td>€ 23,00</td></tr>
                        </table>
            <p data-order-field="payment_information">Nessun pagamento richiesto; totale e modalità saranno confermati prima dell'ordine.</p>
            """,
            subtype="html",
        )
        parsed = parse_order_email(
            BytesParser(policy=policy.default).parsebytes(email.as_bytes()),
            self.products,
            ["negozio@example.org"],
        )

        self.assertEqual(parsed.order_id, "ORD-1234")
        self.assertEqual(parsed.items, [OrderItem("carta-igienica", "Carta igienica lavanda", 2)])
        self.assertEqual(parsed.customer_email, "cliente@example.org")
        self.assertEqual(parsed.customer_phone, "+39 333 1234567")
        self.assertEqual(parsed.voucher_candidate, "BT-12345678-ABCD")
        self.assertEqual(parsed.products_subtotal, "€ 20,00")
        self.assertEqual(parsed.recurring_discount, "Nessuno")
        self.assertEqual(parsed.delivery_address, "Via Roma 4")
        self.assertEqual(parsed.delivery_city, "Montoro")
        self.assertEqual(parsed.preferred_delivery_date, "2026-07-09")
        self.assertEqual(parsed.preferred_delivery_time, "Una data e una fascia oraria specifiche: dalle 10:00 alle 12:00")
        self.assertEqual(parsed.delivery_notes, "Citofono Bianchi")
        self.assertEqual(parsed.request_details["billing_business_name"], "Cartaway SRL")
        self.assertEqual(parsed.request_details["delivery_zone"], "Zona 01 · Montoro")
        self.assertEqual(parsed.request_details["recurring_frequency"], "Mensile")
        self.assertEqual(parsed.request_details["cost_total"], "€ 23,00")
        self.assertEqual(
            parsed.request_details["payment_information"],
            "Nessun pagamento richiesto; totale e modalità saranno confermati prima dell'ordine.",
        )
        self.assertEqual(parsed.request_details["product_lines"][0]["line_total"], "€ 6,00")
        self.assertEqual(parsed.request_details["product_lines"][0]["unit_price"], "€ 3,00")

    def test_validates_only_the_first_monthly_order_for_shared_email_or_phone(self):
        set_stock(self.connection, "carta-igienica", 10)
        first = self._order("ORD-1001", "cliente@example.org", "+39 333 1234567")
        first_result = prepare_order(self.connection, first, self.site)
        second = self._order("ORD-1002", "cliente@example.org", "+39 333 7654321")
        second_result = prepare_order(self.connection, second, self.site)
        third = self._order("ORD-1004", "altro@example.org", "+39 333 1234567")
        third_result = prepare_order(self.connection, third, self.site)
        fourth = self._order("ORD-1008", "terzo@example.org", "+39 333 9876543")
        fourth_result = prepare_order(self.connection, fourth, self.site)

        self.assertEqual(first_result["voucher_valid"], 1)
        self.assertEqual(first_result["voucher_code"], "BT-12345678-ABCD")
        self.assertEqual(second_result["voucher_valid"], 0)
        self.assertEqual(second_result["first_month_order"], 0)
        self.assertEqual(third_result["voucher_valid"], 0)
        self.assertEqual(third_result["first_month_order"], 0)
        self.assertEqual(fourth_result["voucher_valid"], 0)
        self.assertEqual(fourth_result["first_month_order"], 1)
        self.assertEqual(self.connection.execute("SELECT quantity FROM products").fetchone()[0], 10)

    def test_plain_text_email_body_is_used_when_html_is_absent(self):
        email = EmailMessage()
        email.set_content("Riepilogo richiesta #ORD-1005")
        self.assertIn("ORD-1005", _message_body(email))

    def test_unknown_stock_is_not_reported_as_unavailable(self):
        order = self._order("ORD-1003", "cliente@example.org", "+39 333 1234567")
        order.voucher_candidate = ""
        result = prepare_order(self.connection, order, self.site)
        self.assertEqual(result["status"], "da_verificare")
        self.assertEqual(result["response_required"], 0)
        self.assertIn('"state": "da_verificare"', result["availability_json"])

    def test_maps_route_splits_long_runs_and_keeps_manual_waypoint_order(self):
        stops = [f"Via {index}, Montoro" for index in range(1, 12)]
        urls = build_maps_urls("Piazza Roma, Montoro", stops)
        self.assertEqual(len(urls), 2)
        first = parse_qs(urlsplit(urls[0]).query)
        self.assertEqual(first["origin"], ["Piazza Roma, Montoro"])
        self.assertEqual(first["destination"], ["Via 10, Montoro"])
        self.assertEqual(first["waypoints"][0].split("|"), stops[:9])

    def test_vehicle_load_allocator_keeps_orders_whole_and_reports_overflow(self):
        orders = [
            {
                "order_id": "ORD-LOAD-1",
                "availability": [{"product_id": "roll", "name": "Rotoloni", "requested": 2}],
            },
            {
                "order_id": "ORD-LOAD-2",
                "availability": [{"product_id": "paper", "name": "Carta A4", "requested": 1}],
            },
        ]

        result = _allocate_vehicle_loads(
            orders,
            [{"name": "Furgone 1", "capacity_liters": 10}],
            {"roll": 4, "paper": 5},
        )

        self.assertEqual([order["order_id"] for order in result["vehicles"][0]["orders"]], ["ORD-LOAD-1"])
        self.assertEqual(result["vehicles"][0]["used_volume_liters"], 8)
        self.assertEqual(result["vehicles"][0]["remaining_liters"], 2)
        self.assertEqual(result["unassigned_orders"][0]["order"]["order_id"], "ORD-LOAD-2")
        self.assertIn("5.000 L", result["unassigned_orders"][0]["reason"])
        self.assertEqual(sum(product["quantity"] for product in result["products"]), 3)

    def test_vehicle_load_allocator_distributes_whole_orders_across_vans(self):
        orders = [
            {
                "order_id": "ORD-LARGE",
                "availability": [{"product_id": "roll", "name": "Rotoloni", "requested": 2}],
            },
            {
                "order_id": "ORD-SMALL",
                "availability": [{"product_id": "paper", "name": "Carta A4", "requested": 1}],
            },
        ]

        result = _allocate_vehicle_loads(
            orders,
            [
                {"name": "Furgone piccolo", "capacity_liters": 8},
                {"name": "Furgone grande", "capacity_liters": 10},
            ],
            {"roll": 4, "paper": 5},
        )

        self.assertEqual(
            [[order["order_id"] for order in vehicle["orders"]] for vehicle in result["vehicles"]],
            [["ORD-LARGE"], ["ORD-SMALL"]],
        )
        self.assertEqual(result["vehicles"][0]["used_volume_liters"], 8)
        self.assertEqual(result["vehicles"][1]["used_volume_liters"], 5)
        self.assertEqual(result["unassigned_orders"], [])

    def test_single_vehicle_plans_sequential_tours_with_estimated_availability(self):
        site = {
            "delivery_zones": [
                {
                    "locations": [
                        {"name": "Montoro", "lat": 40.8328763, "lon": 14.7917765},
                        {"name": "Solofra", "lat": 40.8291308, "lon": 14.8456516},
                    ]
                }
            ]
        }
        orders = [
            {
                "order_id": "ORD-TOUR-EARLY",
                "customer_name": "Cliente Montoro",
                "destination": "Via Roma 1, Montoro",
                "delivery_city": "Montoro",
                "delivery_address": "Via Roma 1",
                "availability": [{"product_id": "roll", "name": "Rotoli", "requested": 1}],
                "preferred_delivery_time": "Dalle 10:00 alle 10:30",
                "delivery_notes": "",
            },
            {
                "order_id": "ORD-TOUR-LATE",
                "customer_name": "Cliente Solofra",
                "destination": "Via Solofra 2, Solofra",
                "delivery_city": "Solofra",
                "delivery_address": "Via Solofra 2",
                "availability": [{"product_id": "roll", "name": "Rotoli", "requested": 1}],
                "preferred_delivery_time": "Dalle 12:00 alle 12:30",
                "delivery_notes": "",
            },
        ]

        result = _plan_single_vehicle_tours(
            orders,
            {"name": "Furgone 1", "capacity_liters": 5},
            {"roll": 3},
            "Piazza Roma, Montoro",
            site,
            date(2026, 10, 19),
            time(9, 0),
            time(14, 0),
            True,
        )

        self.assertEqual([tour["display_name"] for tour in result["tours"]], [
            "Furgone 1 · Giro 1/2",
            "Furgone 1 · Giro 2/2",
        ])
        self.assertEqual(
            [[order["order_id"] for order in tour["orders"]] for tour in result["tours"]],
            [["ORD-TOUR-EARLY"], ["ORD-TOUR-LATE"]],
        )
        first_tour, second_tour = result["tours"]
        first_departure = datetime.fromisoformat(first_tour["departure_at"])
        first_return = datetime.fromisoformat(first_tour["estimated_return_at"])
        next_available = datetime.fromisoformat(first_tour["next_available_at"])
        second_departure = datetime.fromisoformat(second_tour["departure_at"])
        self.assertLessEqual(first_departure.time(), time(10, 0))
        self.assertLessEqual(first_tour["orders"][0]["estimated_arrival_at"], "2026-10-19T10:30:00+02:00")
        self.assertEqual(next_available, first_return + timedelta(minutes=20))
        self.assertGreaterEqual(second_departure, next_available)
        self.assertLessEqual(second_tour["orders"][0]["estimated_arrival_at"], "2026-10-19T12:30:00+02:00")
        self.assertTrue(first_tour["maps_urls"])
        self.assertIn("ORD-TOUR-EARLY", parse_qs(urlsplit(first_tour["calendar_url"]).query)["details"][0])
        self.assertEqual(result["unassigned_orders"], [])

    def test_single_vehicle_warns_when_estimated_arrival_misses_delivery_window(self):
        order = {
            "order_id": "ORD-TOUR-MISSED-WINDOW",
            "customer_name": "Cliente con finestra breve",
            "destination": "Via Roma 1, Comune senza coordinate",
            "delivery_city": "Comune senza coordinate",
            "delivery_address": "Via Roma 1",
            "availability": [{"product_id": "roll", "name": "Rotoli", "requested": 1}],
            "preferred_delivery_time": "Dalle 09:00 alle 09:05",
            "delivery_notes": "",
        }

        result = _plan_single_vehicle_tours(
            [order],
            {"name": "Furgone 1", "capacity_liters": 5},
            {"roll": 3},
            "Piazza Roma, Comune senza coordinate",
            {"delivery_zones": []},
            date(2026, 10, 19),
            time(9, 0),
            time(12, 0),
            True,
        )

        tour = result["tours"][0]
        estimated_arrival = datetime.fromisoformat(tour["orders"][0]["estimated_arrival_at"])
        self.assertGreater(estimated_arrival.time(), time(9, 5))
        self.assertTrue(any("oltre la finestra richiesta" in warning for warning in tour["schedule_warnings"]))
        self.assertEqual(result["unassigned_orders"], [])

    def test_shortage_requires_a_customer_response_and_does_not_confirm_order(self):
        set_stock(self.connection, "carta-igienica", 1)
        result = prepare_order(
            self.connection,
            self._order("ORD-1006", "cliente@example.org", "+39 333 1234567"),
            self.site,
        )
        self.assertEqual(result["status"], "disponibilita_insufficiente")
        self.assertEqual(result["response_required"], 1)
        self.assertIn("richiesti 2, disponibili 1", result["response_text"])
        self.assertIn("non è una conferma d'ordine", result["response_text"])

    def test_confirm_order_rechecks_stock_and_does_not_send_duplicate_emails(self):
        set_stock(self.connection, "carta-igienica", 10)
        order = self._order("ORD-1011", "cliente@example.org", "+39 333 1234567")
        prepare_order(self.connection, order, self.site)

        with patch("gestionale.gestionale.send_email") as send_email:
            result = confirm_order(self.connection, order.order_id, self.site)
            repeated = confirm_order(self.connection, order.order_id, self.site)

        self.assertTrue(result["confirmed"])
        self.assertFalse(result["already_confirmed"])
        self.assertTrue(repeated["already_confirmed"])
        self.assertEqual(result["delivery_date"], datetime.now(ROME).date().isoformat())
        send_email.assert_called_once()
        message = send_email.call_args.args[0]
        self.assertIn("Conferma ordine #ORD-1011", str(message["Subject"]))
        confirmation_text = message.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("confermato", confirmation_text)
        self.assertIn("2 × Carta igienica lavanda", confirmation_text)
        self.assertIn("Il tuo Buono Tech è stato attivato", confirmation_text)
        self.assertIn("BT-12345678-ABCD", confirmation_text)
        self.assertIn("€ 5,00", confirmation_text)
        row = self.connection.execute(
            "SELECT confirmation_status, email_status, voucher_valid FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ("confirmed", "inviata", 1))

    def test_confirming_recurring_order_activates_its_next_delivery(self):
        set_stock(self.connection, "carta-igienica", 10)
        recurring_settings = dict(self.site["recurring_order"])
        recurring_settings["frequency_days"] = [
            {"days": 7, "label": "Ogni settimana"},
            {"days": 14, "label": "Ogni 2 settimane"},
            {"days": 30, "label": "Ogni mese"},
            {"days": 60, "label": "Ogni 2 mesi"},
        ]
        self.site["recurring_order"] = recurring_settings
        order = self._order("ORD-RECURRING-1", "cliente@example.org", "+39 333 1234567")
        order.recurring = True
        order.request_details = {
            "recurring_frequency": "Ogni settimana",
            "recurring_day": "Lunedì",
        }
        prepare_order(self.connection, order, self.site)

        with patch("gestionale.gestionale.send_email") as send_email:
            result = confirm_order(self.connection, order.order_id, self.site)

        self.assertTrue(result["recurring_scheduled"])
        self.assertEqual(result["recurring_frequency_days"], 7)
        today = datetime.now(ROME).date()
        expected_delivery_date = today + timedelta(days=(0 - today.weekday()) % 7)
        self.assertEqual(result["delivery_date"], expected_delivery_date.isoformat())
        expected_next_date = expected_delivery_date + timedelta(days=7)
        expected_next_date += timedelta(days=(0 - expected_next_date.weekday()) % 7)
        self.assertEqual(result["next_recurring_delivery_date"], expected_next_date.isoformat())
        scheduled_email = send_email.call_args.args[0].get_body(preferencelist=("plain",)).get_content()
        self.assertIn("programmazione ricorrente", scheduled_email)
        self.assertIn(expected_next_date.strftime("%d/%m/%Y"), scheduled_email)
        row = self.connection.execute(
            "SELECT recurring_enabled, recurring_frequency_days, next_recurring_delivery_date "
            "FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(tuple(row), (1, 7, expected_next_date.isoformat()))

    def test_recurring_date_calculation_supports_fixed_and_flexible_cadences(self):
        self.assertEqual(
            _next_recurring_date(date(2026, 1, 31), 30, "15", True),
            date(2026, 2, 15),
        )
        self.assertEqual(
            _next_recurring_date(date(2026, 1, 31), 60, "15", True),
            date(2026, 3, 15),
        )
        self.assertEqual(
            _next_recurring_date(date(2026, 1, 5), 14, "Lunedì", True),
            date(2026, 1, 19),
        )
        self.assertEqual(
            _next_recurring_date(date(2026, 1, 31), 30, "Non indicato", False),
            date(2026, 3, 2),
        )

    def test_confirming_recurring_order_requires_a_valid_schedule(self):
        set_stock(self.connection, "carta-igienica", 10)
        self.site["recurring_order"] = {
            **self.site["recurring_order"],
            "frequency_days": [{"days": 7, "label": "Ogni settimana"}],
            "fixed_delivery_day": True,
        }
        order = self._order("ORD-RECURRING-INVALID", "cliente@example.org", "+39 333 1234567")
        order.recurring = True
        order.request_details = {
            "recurring_frequency": "Ogni settimana",
            "recurring_day": "Non indicato",
        }
        prepare_order(self.connection, order, self.site)

        with patch("gestionale.gestionale.send_email") as send_email:
            with self.assertRaisesRegex(OrderNotReady, "verifica il giorno richiesto"):
                confirm_order(self.connection, order.order_id, self.site)

        send_email.assert_not_called()
        status = self.connection.execute(
            "SELECT confirmation_status FROM orders WHERE order_id = ?", (order.order_id,)
        ).fetchone()[0]
        self.assertEqual(status, "pending")

    def _prepare_weekly_recurring_order(self, order_id):
        set_stock(self.connection, "carta-igienica", 10)
        self.site["recurring_order"] = {
            **self.site["recurring_order"],
            "frequency_days": [{"days": 7, "label": "Ogni settimana"}],
            "fixed_delivery_day": True,
        }
        order = self._order(order_id, "cliente@example.org", "+39 333 1234567")
        order.recurring = True
        order.request_details = {
            "recurring_frequency": "Ogni settimana",
            "recurring_day": "Lunedì",
        }
        prepare_order(self.connection, order, self.site)
        return order

    def test_delivering_recurring_order_advances_date_and_deducts_stock_once(self):
        order = self._prepare_weekly_recurring_order("ORD-RECURRING-DELIVERY")
        with patch("gestionale.gestionale.send_email"):
            confirmed = confirm_order(self.connection, order.order_id, self.site)

        first_date = confirmed["delivery_date"]
        second_date = confirmed["next_recurring_delivery_date"]
        with self.assertRaisesRegex(OrderNotReady, "Indicare la data della consegna"):
            mark_order_delivered(self.connection, order.order_id)
        first_delivery = mark_order_delivered(self.connection, order.order_id, first_date)
        repeated_delivery = mark_order_delivered(self.connection, order.order_id, first_date)

        self.assertFalse(first_delivery["already_delivered"])
        self.assertTrue(repeated_delivery["already_delivered"])
        row = self.connection.execute(
            "SELECT delivery_status, delivery_date, next_recurring_delivery_date, last_delivered_date "
            "FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(row["delivery_status"], "pending")
        self.assertEqual(row["delivery_date"], second_date)
        self.assertEqual(row["last_delivered_date"], first_date)

        second_delivery = mark_order_delivered(self.connection, order.order_id, second_date)
        self.assertFalse(second_delivery["already_delivered"])
        following_date = date.fromisoformat(second_date) + timedelta(days=7)
        following_date += timedelta(days=(0 - following_date.weekday()) % 7)
        third_date = following_date + timedelta(days=7)
        third_date += timedelta(days=(0 - third_date.weekday()) % 7)
        updated = self.connection.execute(
            "SELECT delivery_date, next_recurring_delivery_date FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(tuple(updated), (following_date.isoformat(), third_date.isoformat()))
        quantity = self.connection.execute(
            "SELECT quantity FROM products WHERE product_id = ?", ("carta-igienica",)
        ).fetchone()[0]
        self.assertEqual(quantity, 6)

    def test_disabling_recurring_keeps_current_delivery_scheduled(self):
        order = self._prepare_weekly_recurring_order("ORD-RECURRING-DISABLE")
        with patch("gestionale.gestionale.send_email"):
            confirmed = confirm_order(self.connection, order.order_id, self.site)
        mark_order_delivered(self.connection, order.order_id, confirmed["delivery_date"])

        current_date = self.connection.execute(
            "SELECT delivery_date FROM orders WHERE order_id = ?", (order.order_id,)
        ).fetchone()[0]
        result = disable_recurring_schedule(self.connection, order.order_id)
        scheduled = self.connection.execute(
            "SELECT recurring_enabled, delivery_date, next_recurring_delivery_date "
            "FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertTrue(result["disabled"])
        self.assertEqual(tuple(scheduled), (0, current_date, ""))

        final_delivery = mark_order_delivered(self.connection, order.order_id, current_date)
        self.assertFalse(final_delivery["already_delivered"])
        final_state = self.connection.execute(
            "SELECT delivery_status, recurring_enabled FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(tuple(final_state), ("delivered", 0))
        quantity = self.connection.execute(
            "SELECT quantity FROM products WHERE product_id = ?", ("carta-igienica",)
        ).fetchone()[0]
        self.assertEqual(quantity, 6)

    def test_confirm_order_refuses_to_send_when_stock_is_no_longer_sufficient(self):
        set_stock(self.connection, "carta-igienica", 10)
        order = self._order("ORD-1012", "cliente@example.org", "+39 333 1234567")
        prepare_order(self.connection, order, self.site)
        set_stock(self.connection, "carta-igienica", 1)

        with patch("gestionale.gestionale.send_email") as send_email:
            with self.assertRaisesRegex(OrderNotReady, "richiesti 2, disponibili 1"):
                confirm_order(self.connection, order.order_id, self.site)

        send_email.assert_not_called()
        row = self.connection.execute(
            "SELECT confirmation_status, status FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ("pending", "disponibilita_insufficiente"))

    def test_mark_order_delivered_requires_confirmation(self):
        set_stock(self.connection, "carta-igienica", 10)
        order = self._order("ORD-DELIVERY-PENDING", "cliente@example.org", "+39 333 1234567")
        prepare_order(self.connection, order, self.site)

        with self.assertRaisesRegex(OrderNotReady, "Solo un ordine confermato"):
            mark_order_delivered(self.connection, order.order_id)

        self.assertEqual(
            self.connection.execute("SELECT quantity FROM products WHERE product_id = ?", ("carta-igienica",)).fetchone()[0],
            10,
        )

    def test_mark_order_delivered_deducts_stock_once(self):
        set_stock(self.connection, "carta-igienica", 10)
        order = self._order("ORD-DELIVERY-ONCE", "cliente@example.org", "+39 333 1234567")
        prepare_order(self.connection, order, self.site)
        with patch("gestionale.gestionale.send_email"):
            confirm_order(self.connection, order.order_id, self.site)

        result = mark_order_delivered(self.connection, order.order_id)
        repeated = mark_order_delivered(self.connection, order.order_id)

        self.assertTrue(result["delivered"])
        self.assertFalse(result["already_delivered"])
        self.assertTrue(repeated["already_delivered"])
        self.assertEqual(
            self.connection.execute("SELECT quantity FROM products WHERE product_id = ?", ("carta-igienica",)).fetchone()[0],
            8,
        )
        row = self.connection.execute(
            "SELECT delivery_status, delivered_at FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(row["delivery_status"], "delivered")
        self.assertTrue(row["delivered_at"])

    def test_mark_order_delivered_refuses_shortage_without_changing_order_state(self):
        set_stock(self.connection, "carta-igienica", 10)
        order = self._order("ORD-DELIVERY-SHORT", "cliente@example.org", "+39 333 1234567")
        prepare_order(self.connection, order, self.site)
        with patch("gestionale.gestionale.send_email"):
            confirm_order(self.connection, order.order_id, self.site)
        set_stock(self.connection, "carta-igienica", 1)

        with self.assertRaisesRegex(OrderNotReady, "richiesti 2, disponibili 1"):
            mark_order_delivered(self.connection, order.order_id)

        self.assertEqual(
            self.connection.execute("SELECT quantity FROM products WHERE product_id = ?", ("carta-igienica",)).fetchone()[0],
            1,
        )
        row = self.connection.execute(
            "SELECT delivery_status, delivered_at FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ("pending", ""))

    def test_mail_import_does_not_send_customer_emails(self):
        client = Mock()
        client.login.return_value = ("OK", [b"authenticated"])
        client.select.return_value = ("OK", [b"1"])
        raw_message = b"Subject: Riepilogo richiesta #ORD-1013\r\n\r\nRiepilogo ordine"

        def uid(command, *args):
            if command == "search":
                return "OK", [b"77"]
            if command == "fetch":
                return "OK", [(b"77 RFC822", raw_message)]
            return "OK", [b""]

        client.uid.side_effect = uid
        order = self._order("ORD-1013", "cliente@example.org", "+39 333 1234567")
        environment = {
            "IMAP_HOST": "imap.example.org",
            "IMAP_USER": "shop@example.org",
            "IMAP_PASSWORD": "test-only",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("gestionale.gestionale.imaplib.IMAP4_SSL", return_value=client):
                with patch("gestionale.gestionale.parse_order_email", return_value=order):
                    with patch("gestionale.gestionale.send_email") as send_email:
                        processed = check_mail(self.connection, self.products, self.site, 50)

        self.assertEqual(processed, 1)
        send_email.assert_not_called()
        row = self.connection.execute(
            "SELECT confirmation_status, response_sent FROM orders WHERE order_id = ?",
            (order.order_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ("pending", 0))

    def test_catalog_unavailable_product_requires_customer_response(self):
        self.connection.execute("UPDATE products SET catalog_available = 0 WHERE product_id = ?", ("carta-igienica",))
        self.connection.commit()
        result = prepare_order(
            self.connection,
            self._order("ORD-1010", "cliente@example.org", "+39 333 1234567"),
            self.site,
        )
        self.assertEqual(result["response_required"], 1)
        self.assertIn("segnalato come non disponibile nel catalogo", result["response_text"])

    def test_voucher_amount_must_match_the_checkout_calculation(self):
        order = self._order("ORD-1007", "cliente@example.org", "+39 333 1234567")
        order.voucher_value = "€ 6,00"
        result = prepare_order(self.connection, order, self.site)
        self.assertEqual(result["voucher_valid"], 0)

    def test_valid_voucher_is_listed_and_missing_amounts_are_explained(self):
        valid_order = self._order("ORD-1014", "cliente@example.org", "+39 333 1234567")
        valid_result = prepare_order(self.connection, valid_order, self.site)
        vouchers = self.connection.execute("SELECT code, order_id FROM valid_vouchers").fetchall()
        self.assertEqual([tuple(row) for row in vouchers], [("BT-12345678-ABCD", "ORD-1014")])
        self.assertEqual(valid_result["voucher_valid"], 1)

        incomplete_order = self._order("ORD-1015", "altro@example.org", "+39 333 9876543")
        incomplete_order.voucher_candidate = "BT-87654321-EFGH"
        incomplete_order.voucher_value = ""
        incomplete_order.products_subtotal = ""
        incomplete_result = prepare_order(self.connection, incomplete_order, self.site)
        status = voucher_validation_status(self.connection, incomplete_result, self.site)
        self.assertTrue(status["first_month_order"])
        self.assertEqual(status["label"], "Da verificare")
        self.assertIn("non acquisiti", status["reason"])
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM valid_vouchers").fetchone()[0],
            1,
        )

    def test_recurring_voucher_uses_subtotal_after_checkout_discount(self):
        order = self._order("ORD-1009", "cliente@example.org", "+39 333 1234567")
        order.recurring = True
        order.recurring_discount = "−€ 4,00"
        order.voucher_value = "€ 8,00"
        result = prepare_order(self.connection, order, self.site)
        self.assertEqual(result["voucher_valid"], 1)
        self.assertEqual(result["voucher_validity_days"], 90)

    def test_calendar_link_uses_rome_timezone_and_requested_schedule(self):
        url = build_calendar_url(
            "Giro consegne",
            date(2026, 7, 8),
            time(9, 0),
            time(13, 30),
            "Montoro",
            "Link Maps",
        )
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["ctz"], ["Europe/Rome"])
        self.assertEqual(query["dates"], ["20260708T090000/20260708T133000"])

    def test_check_mail_always_uses_inbox_and_unseen(self):
        client = Mock()
        client.login.return_value = ("OK", [b"authenticated"])
        client.select.return_value = ("OK", [b"0"])
        client.uid.return_value = ("OK", [b""])
        environment = {
            "IMAP_HOST": "imap.example.org",
            "IMAP_USER": "shop@example.org",
            "IMAP_PASSWORD": "test-only",
            "IMAP_FOLDER": "INBOX.Sent",
            "IMAP_SEARCH": "ALL",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("gestionale.gestionale.imaplib.IMAP4_SSL", return_value=client) as client_factory:
                processed = check_mail(self.connection, self.products, self.site, 50)
                client_factory.assert_called_once()
                self.assertEqual(client_factory.call_args.kwargs["timeout"], 15)
        self.assertEqual(processed, 0)
        client.select.assert_called_once_with("INBOX")
        client.uid.assert_called_once_with("search", None, "UNSEEN")

    def test_mail_folders_lists_provider_folders_without_reading_messages(self):
        client = Mock()
        client.login.return_value = ("OK", [b"authenticated"])
        client.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "[Gmail]/Sent Mail"'],
        )
        environment = {
            "IMAP_HOST": "imap.example.org",
            "IMAP_USER": "shop@example.org",
            "IMAP_PASSWORD": "test-only",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("gestionale.gestionale.imaplib.IMAP4_SSL", return_value=client) as client_factory:
                folders = list_mail_folders()
        client_factory.assert_called_once()
        self.assertEqual(len(folders), 2)
        self.assertIn("INBOX", folders[0])
        self.assertIn("[Gmail]/Sent Mail", folders[1])
        client.select.assert_not_called()
        client.uid.assert_not_called()

    def test_smtp_aruba_host_is_rejected_with_imap_settings(self):
        environment = {
            "IMAP_HOST": "smtps.aruba.it",
            "IMAP_USER": "shop@example.org",
            "IMAP_PASSWORD": "test-only",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("gestionale.gestionale.imaplib.IMAP4_SSL") as client_factory:
                with self.assertRaisesRegex(AppError, "IMAP_HOST=imaps.aruba.it"):
                    list_mail_folders()
        client_factory.assert_not_called()

    def test_imap_timeout_must_be_within_allowed_bounds(self):
        environment = {
            "IMAP_HOST": "imap.example.org",
            "IMAP_USER": "shop@example.org",
            "IMAP_PASSWORD": "test-only",
            "IMAP_TIMEOUT": "0",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(Exception, "IMAP_TIMEOUT"):
                list_mail_folders()

    def _order(self, order_id, email, phone):
        return ParsedOrder(
            order_id=order_id,
            items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
            customer_name="Mario Bianchi",
            customer_email=email,
            customer_phone=phone,
            delivery_address="Via Roma 4",
            delivery_city="Montoro",
            recurring=False,
            voucher_candidate="BT-12345678-ABCD",
            voucher_value="€ 5,00",
            products_subtotal="€ 20,00",
            recurring_discount="Nessuno",
            order_datetime=datetime(2026, 7, 8, 10, 0, tzinfo=ROME),
            message_id=f"<{order_id.lower()}@example.org>",
        )


class GestionaleWebTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "gestionale.sqlite3"
        self.products = {
            "carta-igienica": {
                "id": "carta-igienica",
                "name": "Carta igienica lavanda",
                "available": True,
            }
        }
        self.site = {
            "brand": "Cartaway",
            "address": "Piazza Roma, Montoro",
            "tech_voucher": {"percent": 25, "maximum_amount": 25, "validity_days": 60},
        }
        connection = open_database(self.database)
        sync_catalog(connection, list(self.products.values()))
        connection.close()
        self.server = create_server(self.database, self.site, self.products, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary_directory.cleanup()

    def _post(self, path, payload, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        return urlopen(request, timeout=3)

    def test_vehicle_route_endpoint_assigns_load_and_returns_van_maps_link(self):
        order_id = "ORD-VEHICLE-LOAD"
        connection = open_database(self.database)
        try:
            set_stock(connection, "carta-igienica", 10)
            order = ParsedOrder(
                order_id=order_id,
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Mario Bianchi",
                customer_email="mario@example.org",
                customer_phone="+39 333 1234567",
                delivery_address="Via Roma 4",
                delivery_city="Montoro",
                recurring=False,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 6,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME),
                message_id=f"<{order_id.lower()}@example.org>",
            )
            prepare_order(connection, order, self.site)
            with patch("gestionale.gestionale.send_email"):
                confirm_order(connection, order_id, self.site)
        finally:
            connection.close()

        with self._post(
            "/api/load-config",
            {
                "product_volumes": {"carta-igienica": 2.5},
                "vehicles": [{"name": "Furgone 1", "capacity_liters": 5}],
            },
            origin=self.base_url,
        ) as response:
            self.assertEqual(response.status, 200)

        delivery_date = datetime.now(ROME).date().isoformat()
        with self._post(
            "/api/vehicle-routes",
            {
                "origin": "Piazza Roma, Montoro",
                "date": delivery_date,
                "start": "09:00",
                "end": "13:00",
                "return_to_origin": False,
            },
            origin=self.base_url,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))

        vehicle = result["vehicles"][0]
        self.assertEqual(vehicle["name"], "Furgone 1")
        self.assertEqual(vehicle["used_volume_liters"], 5)
        self.assertEqual([order["order_id"] for order in vehicle["orders"]], [order_id])
        self.assertEqual(vehicle["products"][0]["quantity"], 2)
        self.assertEqual(len(vehicle["maps_urls"]), 1)
        self.assertIn("ORD-VEHICLE-LOAD", parse_qs(urlsplit(vehicle["calendar_url"]).query)["details"][0])
        maps_query = parse_qs(urlsplit(vehicle["maps_urls"][0]).query)
        self.assertEqual(maps_query["destination"], ["Via Roma 4, Montoro"])

    def test_delivery_preview_shares_stock_between_package_variants(self):
        product_variants = [
            {
                "id": "splash-2-rolls",
                "name": "Asciugatutto Splash · 2 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 2, "measure": "rotoli"},
            },
            {
                "id": "splash-6-rolls",
                "name": "Asciugatutto Splash · 6 rotoli",
                "stock_group": "splash-rolls",
                "unit": {"quantity": 6, "measure": "rotoli"},
            },
        ]
        delivery_date = datetime.now(ROME).date().isoformat()
        connection = open_database(self.database)
        try:
            sync_catalog(connection, product_variants)
            with self._post(
                "/api/stock",
                {"product_id": "splash-2-rolls", "action": "set", "quantity": 3},
                origin=self.base_url,
            ) as response:
                stock_update = json.load(response)
            self.assertEqual(stock_update["quantity"], 3)
            self.assertTrue(stock_update["shared_stock"])
            self.assertEqual(stock_update["shared_quantity"], 6)
            orders = [
                ParsedOrder(
                    order_id="ORD-SHARED-STOCK-EARLY",
                    items=[OrderItem("splash-2-rolls", "Asciugatutto Splash · 2 rotoli", 1)],
                    customer_name="Cliente confezione piccola",
                    customer_email="small@example.org",
                    customer_phone="+39 333 1112233",
                    delivery_address="Via Roma 1",
                    delivery_city="Montoro",
                    recurring=False,
                    voucher_candidate="",
                    voucher_value="",
                    products_subtotal="€ 4,99",
                    recurring_discount="Nessuno",
                    order_datetime=datetime.now(ROME),
                    message_id="<shared-stock-early@example.org>",
                ),
                ParsedOrder(
                    order_id="ORD-SHARED-STOCK-LATE",
                    items=[OrderItem("splash-6-rolls", "Asciugatutto Splash · 6 rotoli", 1)],
                    customer_name="Cliente confezione grande",
                    customer_email="large@example.org",
                    customer_phone="+39 333 2223344",
                    delivery_address="Via Roma 2",
                    delivery_city="Montoro",
                    recurring=False,
                    voucher_candidate="",
                    voucher_value="",
                    products_subtotal="€ 9,99",
                    recurring_discount="Nessuno",
                    order_datetime=datetime.now(ROME) + timedelta(minutes=1),
                    message_id="<shared-stock-late@example.org>",
                ),
            ]
            with patch("gestionale.gestionale.send_email"):
                for order in orders:
                    prepare_order(connection, order, self.site)
                    confirm_order(connection, order.order_id, self.site)
        finally:
            connection.close()

        with urlopen(f"{self.base_url}/api/dashboard", timeout=3) as response:
            dashboard = json.load(response)
        stock_by_id = {item["product_id"]: item for item in dashboard["stock"]}
        self.assertTrue(stock_by_id["splash-2-rolls"]["shared_stock"])
        self.assertEqual(stock_by_id["splash-2-rolls"]["shared_quantity"], 6)
        self.assertEqual(stock_by_id["splash-6-rolls"]["quantity"], 1)

        with urlopen(
            f"{self.base_url}/api/deliveries?date={delivery_date}",
            timeout=3,
        ) as response:
            result = json.load(response)

        orders_by_id = {order["order_id"]: order for order in result["orders"]}
        self.assertTrue(orders_by_id["ORD-SHARED-STOCK-EARLY"]["deliverable"])
        later_order = orders_by_id["ORD-SHARED-STOCK-LATE"]
        self.assertFalse(later_order["deliverable"])
        self.assertIn("richiesti 6 rotoli, disponibili 4 rotoli", later_order["availability_issues"][0])

    def test_single_vehicle_route_api_splits_load_into_deadline_ordered_tours(self):
        delivery_date = datetime.now(ROME).date()
        connection = open_database(self.database)
        try:
            set_stock(connection, "carta-igienica", 20)
            orders = [
                ParsedOrder(
                    order_id="ORD-API-TOUR-EARLY",
                    items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                    customer_name="Cliente mattina",
                    customer_email="early@example.org",
                    customer_phone="+39 333 1112233",
                    delivery_address="Via Roma 4",
                    delivery_city="Montoro",
                    recurring=False,
                    voucher_candidate="",
                    voucher_value="",
                    products_subtotal="€ 6,00",
                    recurring_discount="Nessuno",
                    order_datetime=datetime.now(ROME),
                    message_id="<api-tour-early@example.org>",
                    preferred_delivery_date=delivery_date.isoformat(),
                    preferred_delivery_time="Dalle 10:00 alle 11:00",
                ),
                ParsedOrder(
                    order_id="ORD-API-TOUR-LATE",
                    items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                    customer_name="Cliente pomeriggio",
                    customer_email="late@example.org",
                    customer_phone="+39 333 2223344",
                    delivery_address="Via Roma 5",
                    delivery_city="Montoro",
                    recurring=False,
                    voucher_candidate="",
                    voucher_value="",
                    products_subtotal="€ 6,00",
                    recurring_discount="Nessuno",
                    order_datetime=datetime.now(ROME) + timedelta(minutes=1),
                    message_id="<api-tour-late@example.org>",
                    preferred_delivery_date=delivery_date.isoformat(),
                    preferred_delivery_time="Dalle 12:00 alle 13:00",
                ),
            ]
            with patch("gestionale.gestionale.send_email"):
                for order in orders:
                    prepare_order(connection, order, self.site)
                    confirm_order(connection, order.order_id, self.site)
        finally:
            connection.close()

        with self._post(
            "/api/load-config",
            {
                "product_volumes": {"carta-igienica": 3},
                "vehicles": [{"name": "Furgone unico", "capacity_liters": 6}],
            },
            origin=self.base_url,
        ) as response:
            self.assertEqual(response.status, 200)

        with self._post(
            "/api/vehicle-routes",
            {
                "origin": "Piazza Roma, Montoro",
                "date": delivery_date.isoformat(),
                "start": "09:00",
                "end": "16:00",
                "return_to_origin": True,
            },
            origin=self.base_url,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))

        tours = result["vehicles"]
        self.assertEqual(len(tours), 2)
        self.assertEqual(
            [[order["order_id"] for order in tour["orders"]] for tour in tours],
            [["ORD-API-TOUR-EARLY"], ["ORD-API-TOUR-LATE"]],
        )
        requested_windows = [(time(10, 0), time(11, 0)), (time(12, 0), time(13, 0))]
        destinations = ["Via Roma 4, Montoro", "Via Roma 5, Montoro"]
        for tour, requested_window, destination in zip(tours, requested_windows, destinations):
            estimated_arrival = datetime.fromisoformat(
                tour["orders"][0]["estimated_arrival_at"]
            )
            self.assertEqual(estimated_arrival.date(), delivery_date)
            self.assertGreaterEqual(estimated_arrival.time(), requested_window[0])
            self.assertLessEqual(estimated_arrival.time(), requested_window[1])
            self.assertEqual(tour["schedule_warnings"], [])
            maps_query = parse_qs(urlsplit(tour["maps_urls"][0]).query)
            self.assertEqual(maps_query["waypoints"], [destination])
            calendar_details = parse_qs(urlsplit(tour["calendar_url"]).query)["details"][0]
            self.assertIn(tour["orders"][0]["order_id"], calendar_details)
        first_return = datetime.fromisoformat(tours[0]["estimated_return_at"])
        next_available = datetime.fromisoformat(tours[0]["next_available_at"])
        second_departure = datetime.fromisoformat(tours[1]["departure_at"])
        self.assertEqual(next_available, first_return + timedelta(minutes=20))
        self.assertGreaterEqual(second_departure, next_available)
        self.assertTrue(all(tour["maps_urls"] and tour["calendar_url"] for tour in tours))
        self.assertEqual(result["unassigned_orders"], [])

    def test_route_grouping_prioritizes_origin_city_unless_time_requires_other_city(self):
        untimed_orders = [
            {"order_id": "SOL-1", "delivery_city": "Solofra", "preferred_delivery_time": ""},
            {"order_id": "MON-1", "delivery_city": "Montoro", "preferred_delivery_time": ""},
            {"order_id": "MON-2", "delivery_city": "Montoro", "preferred_delivery_time": ""},
        ]
        origin = "Via Roma, 1, Torchiati di Montoro (AV)"
        grouped = _group_route_orders_by_city(untimed_orders, origin)
        self.assertEqual([order["order_id"] for order in grouped], ["MON-1", "MON-2", "SOL-1"])

        timed_orders = [
            {"order_id": "MON-1", "delivery_city": "Montoro", "preferred_delivery_time": ""},
            {"order_id": "SOL-1", "delivery_city": "Solofra", "preferred_delivery_time": "10:00"},
        ]
        grouped = _group_route_orders_by_city(timed_orders, origin)
        self.assertEqual([order["order_id"] for order in grouped], ["SOL-1", "MON-1"])

    def test_route_optimizes_city_detours_around_fixed_time_constraints(self):
        site = {
            "delivery_zones": [
                {
                    "locations": [
                        {"name": "Montoro", "lat": 40.0, "lon": 14.0},
                        {"name": "Forino", "lat": 40.0, "lon": 14.1},
                        {"name": "Solofra", "lat": 40.0, "lon": 14.2},
                        {"name": "Fisciano", "lat": 40.0, "lon": 14.3},
                    ]
                }
            ]
        }
        origin = "Via Roma, 1, Torchiati di Montoro (AV)"
        orders = [
            {"order_id": "FISCIANO", "delivery_city": "Fisciano", "preferred_delivery_time": "", "delivery_notes": "Dopo le 12:00"},
            {"order_id": "SOLOFRA", "delivery_city": "Solofra", "preferred_delivery_time": "", "delivery_notes": ""},
            {"order_id": "MONTORO", "delivery_city": "Montoro", "preferred_delivery_time": "", "delivery_notes": ""},
            {"order_id": "FORINO", "delivery_city": "Forino", "preferred_delivery_time": "10:00–11:00", "delivery_notes": ""},
        ]

        grouped = _group_route_orders_by_city(orders, origin, site)

        self.assertEqual(
            [order["delivery_city"] for order in grouped],
            ["Montoro", "Forino", "Solofra", "Fisciano"],
        )

        earlier_appointment_orders = [
            {"order_id": "MONTORO", "delivery_city": "Montoro", "preferred_delivery_time": "15:00–16:00"},
            {"order_id": "FORINO", "delivery_city": "Forino", "preferred_delivery_time": "10:00–11:00"},
        ]
        grouped = _group_route_orders_by_city(earlier_appointment_orders, origin, site)
        self.assertEqual([order["delivery_city"] for order in grouped], ["Forino", "Montoro"])

    def test_orders_api_separates_completed_orders_into_history(self):
        today = datetime.now(ROME).date()
        order_specs = [
            ("ORD-HISTORY", False),
            ("ORD-DISABLED-PENDING", True),
            ("ORD-DISABLED-DELIVERED", True),
            ("ORD-RECURRING-ACTIVE", True),
            ("ORD-UNCONFIRMED", False),
        ]
        connection = open_database(self.database)
        try:
            for order_id, recurring in order_specs:
                order = ParsedOrder(
                    order_id=order_id,
                    items=[OrderItem("carta-igienica", "Carta igienica lavanda", 1)],
                    customer_name="Mario Bianchi",
                    customer_email="cliente@example.org",
                    customer_phone="+39 333 1234567",
                    delivery_address="Via Roma 1",
                    delivery_city="Montoro",
                    recurring=recurring,
                    voucher_candidate="",
                    voucher_value="",
                    products_subtotal="€ 10,00",
                    recurring_discount="Nessuno",
                    order_datetime=datetime.now(ROME),
                    message_id=f"<{order_id}@example.org>",
                )
                prepare_order(connection, order, self.site)

            for order_id in ("ORD-HISTORY", "ORD-DISABLED-DELIVERED"):
                connection.execute(
                    "UPDATE orders SET confirmation_status = 'confirmed', delivery_status = 'delivered', "
                    "delivered_at = ?, delivery_date = ?, last_delivered_date = ?, recurring_enabled = 0 "
                    "WHERE order_id = ?",
                    (datetime.now(ROME).isoformat(timespec="seconds"), today.isoformat(), today.isoformat(), order_id),
                )
            connection.execute(
                "UPDATE orders SET confirmation_status = 'confirmed', delivery_status = 'pending', "
                "recurring_enabled = 0, delivery_date = ? WHERE order_id = ?",
                (today.isoformat(), "ORD-DISABLED-PENDING"),
            )
            connection.execute(
                "UPDATE orders SET confirmation_status = 'confirmed', delivery_status = 'pending', "
                "recurring_enabled = 1, recurring_frequency_days = 7, delivery_date = ?, "
                "next_recurring_delivery_date = ? WHERE order_id = ?",
                (
                    (today + timedelta(days=7)).isoformat(),
                    (today + timedelta(days=14)).isoformat(),
                    "ORD-RECURRING-ACTIVE",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        with urlopen(self.base_url + "/api/dashboard", timeout=3) as response:
            dashboard = json.load(response)
        with urlopen(self.base_url + "/api/orders/history", timeout=3) as response:
            history = json.load(response)

        self.assertCountEqual(
            [order["order_id"] for order in dashboard["orders"]],
            ["ORD-DISABLED-PENDING", "ORD-RECURRING-ACTIVE", "ORD-UNCONFIRMED"],
        )
        self.assertCountEqual(
            [order["order_id"] for order in history["orders"]],
            ["ORD-HISTORY", "ORD-DISABLED-DELIVERED"],
        )

    def test_dashboard_and_stock_update_are_available_from_local_web_ui(self):
        with urlopen(self.base_url + "/", timeout=3) as response:
            page = response.read().decode("utf-8")
        self.assertIn("Ordini e consegne", page)
        self.assertIn("Consegne", page)
        self.assertIn("Ordini ricorrenti attivi", page)
        self.assertIn("Storico ordini", page)
        self.assertIn('id="orders-history-view"', page)
        self.assertNotIn("recurring-schedules-list", page)

        with urlopen(self.base_url + "/api/dashboard", timeout=3) as response:
            dashboard = json.load(response)
        self.assertEqual(dashboard["brand"], "Cartaway")
        self.assertEqual(dashboard["summary"]["products"], 1)

        origin = self.base_url
        with self._post(
            "/api/stock",
            {"product_id": "carta-igienica", "action": "set", "quantity": 12},
            origin,
        ) as response:
            result = json.load(response)
        self.assertEqual(result["quantity"], 12)

    def test_order_confirmation_api_sends_email_once(self):
        connection = open_database(self.database)
        try:
            set_stock(connection, "carta-igienica", 10)
            order = ParsedOrder(
                order_id="ORD-WEB-1",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Mario Bianchi",
                customer_email="cliente@example.org",
                customer_phone="+39 333 1234567",
                delivery_address="Via Roma 4",
                delivery_city="Montoro",
                recurring=False,
                voucher_candidate="BT-23456789-ABCD",
                voucher_value="€ 5,00",
                products_subtotal="€ 20,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME),
                message_id="<web-order@example.org>",
                preferred_delivery_time="Prima disponibilità",
                request_details={
                    "delivery_zone": "Zona 01 · Montoro",
                    "billing_business_name": "Cartaway SRL",
                    "cost_total": "€ 23,00",
                },
            )
            prepare_order(connection, order, self.site)
        finally:
            connection.close()

        with patch("gestionale.gestionale.send_email") as send_email:
            with self._post("/api/orders/confirm", {"order_id": "ORD-WEB-1"}, self.base_url) as response:
                result = json.load(response)
            with self._post("/api/orders/confirm", {"order_id": "ORD-WEB-1"}, self.base_url) as response:
                repeated = json.load(response)
        with self._post("/api/orders/deliver", {"order_id": "ORD-WEB-1"}, self.base_url) as response:
            delivered = json.load(response)
        with self._post("/api/orders/deliver", {"order_id": "ORD-WEB-1"}, self.base_url) as response:
            repeated_delivery = json.load(response)

        self.assertTrue(result["confirmed"])
        self.assertFalse(result["already_confirmed"])
        self.assertTrue(repeated["already_confirmed"])
        self.assertTrue(delivered["delivered"])
        self.assertFalse(delivered["already_delivered"])
        self.assertTrue(repeated_delivery["already_delivered"])
        send_email.assert_called_once()
        with urlopen(self.base_url + "/api/dashboard", timeout=3) as response:
            dashboard = json.load(response)
        with urlopen(self.base_url + "/api/orders/history", timeout=3) as response:
            history = json.load(response)
        archived_order = history["orders"][0]
        self.assertEqual(archived_order["request_details"]["delivery_zone"], "Zona 01 · Montoro")
        self.assertEqual(archived_order["request_details"]["cost_total"], "€ 23,00")
        self.assertEqual(dashboard["valid_vouchers"][0]["code"], "BT-23456789-ABCD")
        self.assertEqual(archived_order["delivery_status"], "delivered")
        self.assertFalse(dashboard["orders"])
        self.assertEqual(dashboard["stock"][0]["quantity"], 8)

    def test_recurring_delivery_api_advances_and_can_be_disabled(self):
        self.site["recurring_order"] = {
            "frequency_days": [{"days": 7, "label": "Ogni settimana"}],
            "fixed_delivery_day": True,
        }
        connection = open_database(self.database)
        try:
            set_stock(connection, "carta-igienica", 10)
            order = ParsedOrder(
                order_id="ORD-WEB-RECURRING",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Mario Bianchi",
                customer_email="cliente@example.org",
                customer_phone="+39 333 1234567",
                delivery_address="Via Roma 4",
                delivery_city="Montoro",
                recurring=True,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 20,00",
                recurring_discount="5%",
                order_datetime=datetime.now(ROME),
                message_id="<web-recurring@example.org>",
                request_details={
                    "recurring_frequency": "Ogni settimana",
                    "recurring_day": "Lunedì",
                },
            )
            prepare_order(connection, order, self.site)
        finally:
            connection.close()

        with patch("gestionale.gestionale.send_email") as send_email:
            with self._post("/api/orders/confirm", {"order_id": "ORD-WEB-RECURRING"}, self.base_url) as response:
                confirmed = json.load(response)
            with urlopen(self.base_url + "/api/dashboard", timeout=3) as response:
                active_dashboard = json.load(response)
            self.assertEqual(active_dashboard["summary"]["recurring_orders"], 1)
            first_date = confirmed["delivery_date"]
            second_date = confirmed["next_recurring_delivery_date"]
            with urlopen(self.base_url + f"/api/deliveries?date={first_date}", timeout=3) as response:
                first_plan = json.load(response)
            self.assertEqual(len(first_plan["orders"]), 1)
            self.assertEqual(first_plan["orders"][0]["recurring_frequency"], "Ogni settimana")
            self.assertEqual(first_plan["orders"][0]["recurring_day"], "Lunedì")
            with urlopen(self.base_url + f"/api/deliveries?date={second_date}", timeout=3) as response:
                projected_plan = json.load(response)
            self.assertEqual(len(projected_plan["orders"]), 1)
            self.assertTrue(projected_plan["orders"][0]["is_recurring_projection"])
            self.assertFalse(projected_plan["orders"][0]["occurrence_ready"])
            with self.assertRaises(HTTPError) as missing_date:
                self._post("/api/orders/deliver", {"order_id": "ORD-WEB-RECURRING"}, self.base_url)
            self.assertEqual(missing_date.exception.code, 409)
            with self._post(
                "/api/orders/deliver",
                {"order_id": "ORD-WEB-RECURRING", "delivery_date": first_date},
                self.base_url,
            ) as response:
                delivered = json.load(response)
            with self._post(
                "/api/orders/deliver",
                {"order_id": "ORD-WEB-RECURRING", "delivery_date": first_date},
                self.base_url,
            ) as response:
                repeated = json.load(response)
            with urlopen(self.base_url + f"/api/deliveries?date={second_date}", timeout=3) as response:
                second_plan = json.load(response)
            self.assertEqual(len(second_plan["orders"]), 1)
            self.assertEqual(second_plan["orders"][0]["delivery_date"], second_date)
            self.assertFalse(second_plan["orders"][0]["is_recurring_projection"])
            self.assertTrue(second_plan["orders"][0]["occurrence_ready"])
            self.assertEqual(second_plan["orders"][0]["recurring_frequency"], "Ogni settimana")
            with self._post(
                "/api/orders/recurring/disable",
                {"order_id": "ORD-WEB-RECURRING"},
                self.base_url,
            ) as response:
                disabled = json.load(response)
            with urlopen(self.base_url + f"/api/deliveries?date={second_date}", timeout=3) as response:
                disabled_plan = json.load(response)
            self.assertEqual(disabled_plan["orders"][0]["delivery_date"], second_date)
            self.assertFalse(disabled_plan["orders"][0]["recurring_enabled"])
            with self._post(
                "/api/orders/deliver",
                {"order_id": "ORD-WEB-RECURRING", "delivery_date": second_date},
                self.base_url,
            ) as response:
                final_delivery = json.load(response)

        self.assertTrue(confirmed["recurring_scheduled"])
        self.assertFalse(delivered["already_delivered"])
        self.assertTrue(repeated["already_delivered"])
        self.assertTrue(disabled["disabled"])
        self.assertFalse(final_delivery["already_delivered"])
        send_email.assert_called_once()
        with urlopen(self.base_url + "/api/dashboard", timeout=3) as response:
            dashboard = json.load(response)
        with urlopen(self.base_url + "/api/orders/history", timeout=3) as response:
            history = json.load(response)
        self.assertFalse(dashboard["orders"])
        self.assertEqual(history["orders"][0]["order_id"], "ORD-WEB-RECURRING")
        self.assertFalse(history["orders"][0]["recurring_enabled"])
        self.assertEqual(dashboard["summary"]["recurring_orders"], 0)
        self.assertEqual(dashboard["stock"][0]["quantity"], 6)

    def test_web_api_rejects_cross_origin_stock_changes(self):
        with self.assertRaises(HTTPError) as error:
            self._post(
                "/api/stock",
                {"product_id": "carta-igienica", "action": "set", "quantity": 0},
                "http://example.org",
            )
        self.assertEqual(error.exception.code, 403)

    def test_web_api_returns_actionable_timeout_message(self):
        with patch("gestionale.gestionale_web.gestionale.check_mail", side_effect=TimeoutError):
            with self.assertRaises(HTTPError) as error:
                self._post("/api/mail/check", {"limit": 50}, self.base_url)
        self.assertEqual(error.exception.code, 504)
        response = json.loads(error.exception.read().decode("utf-8"))
        self.assertIn("Timeout IMAP", response["error"])
        self.assertIn("IMAP_PORT=993", response["error"])

    def test_route_api_returns_maps_and_calendar_links(self):
        today = datetime.now(ROME).date().isoformat()
        connection = open_database(self.database)
        try:
            set_stock(connection, "carta-igienica", 3)
            order = ParsedOrder(
                order_id="ORD-ROUTE-1",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Mario Bianchi",
                customer_email="cliente@example.org",
                customer_phone="+39 333 1234567",
                delivery_address="Via Napoli 1",
                delivery_city="Montoro",
                recurring=False,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 20,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME),
                message_id="<route@example.org>",
            )
            prepare_order(connection, order, self.site)
            connection.execute(
                "UPDATE orders SET confirmation_status = 'confirmed', confirmed_at = ?, delivery_date = ? WHERE order_id = ?",
                (datetime.now(ROME).isoformat(timespec="seconds"), today, order.order_id),
            )
            connection.commit()
            second_order = ParsedOrder(
                order_id="ORD-ROUTE-2",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Luigi Verdi",
                customer_email="luigi@example.org",
                customer_phone="+39 333 7654321",
                delivery_address="Via Roma 2",
                delivery_city="Solofra",
                recurring=False,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 20,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME),
                message_id="<route-second@example.org>",
            )
            prepare_order(connection, second_order, self.site)
            connection.execute(
                "UPDATE orders SET confirmation_status = 'confirmed', confirmed_at = ?, delivery_date = ? WHERE order_id = ?",
                (datetime.now(ROME).isoformat(timespec="seconds"), today, second_order.order_id),
            )
            connection.commit()
        finally:
            connection.close()

        with urlopen(f"{self.base_url}/api/deliveries?date={today}", timeout=3) as response:
            delivery_data = json.load(response)
        self.assertEqual(
            [order["order_id"] for order in delivery_data["orders"]],
            ["ORD-ROUTE-1", "ORD-ROUTE-2"],
        )
        self.assertEqual([order["deliverable"] for order in delivery_data["orders"]], [True, False])
        self.assertIn("richiesti 2, disponibili 1", delivery_data["orders"][1]["availability_issues"][0])

        with self._post(
            "/api/route",
            {
                "origin": "Piazza Roma, Montoro",
                "date": today,
                "start": "09:00",
                "end": "13:00",
                "return_to_origin": True,
            },
            self.base_url,
        ) as response:
            result = json.load(response)
        self.assertEqual(len(result["maps_urls"]), 1)
        self.assertIn("google.com/maps/dir", result["maps_urls"][0])
        maps_query = parse_qs(urlsplit(result["maps_urls"][0]).query)
        self.assertEqual(maps_query["waypoints"], ["Via Napoli 1, Montoro"])
        self.assertEqual([order["order_id"] for order in result["orders"]], ["ORD-ROUTE-1"])
        self.assertEqual([order["order_id"] for order in result["excluded_orders"]], ["ORD-ROUTE-2"])
        self.assertEqual(result["excluded_unavailable"], 1)
        calendar = parse_qs(urlsplit(result["calendar_url"]).query)
        self.assertEqual(calendar["ctz"], ["Europe/Rome"])

        connection = open_database(self.database)
        try:
            set_stock(connection, "carta-igienica", 1)
        finally:
            connection.close()
        with urlopen(f"{self.base_url}/api/deliveries?date={today}", timeout=3) as response:
            updated_deliveries = json.load(response)
        self.assertFalse(any(order["deliverable"] for order in updated_deliveries["orders"]))
        with self.assertRaises(HTTPError) as error:
            self._post(
                "/api/route",
                {
                    "origin": "Piazza Roma, Montoro",
                    "date": today,
                    "start": "09:00",
                    "end": "13:00",
                    "return_to_origin": False,
                },
                self.base_url,
            )
        self.assertEqual(error.exception.code, 409)
        self.assertIn("disponibilità sufficiente", error.exception.read().decode("utf-8"))

    def test_route_respects_delivery_date_and_time_preferences_and_shows_recurrence(self):
        today = datetime.now(ROME).date()
        days_to_monday = (0 - today.weekday()) % 7 or 7
        delivery_date = today + timedelta(days=days_to_monday)
        self.site["delivery_zones"] = [
            {
                "locations": [
                    {"name": "Montoro", "lat": 40.8328763, "lon": 14.7917765},
                    {"name": "Solofra", "lat": 40.8291308, "lon": 14.8456516},
                ]
            }
        ]
        self.site["recurring_order"] = {
            "frequency_days": [
                {"days": 7, "label": "Ogni settimana"},
                {"days": 14, "label": "Ogni 2 settimane"},
                {"days": 30, "label": "Ogni mese"},
                {"days": 60, "label": "Ogni 2 mesi"},
            ],
            "fixed_delivery_day": True,
        }
        connection = open_database(self.database)
        try:
            set_stock(connection, "carta-igienica", 10)

            late_recurring_order = ParsedOrder(
                order_id="ORD-ROUTE-LATE",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Mario Bianchi",
                customer_email="mario@example.org",
                customer_phone="+39 333 1234567",
                delivery_address="Via Tardi 1",
                delivery_city="Montoro",
                recurring=True,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 20,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME) - timedelta(minutes=2),
                message_id="<route-late@example.org>",
                preferred_delivery_date=delivery_date.isoformat(),
                preferred_delivery_time="Una fascia oraria specifica: dalle 15:00 alle 16:00",
                request_details={"recurring_frequency": "Ogni 2 settimane", "recurring_day": "Lunedì"},
            )
            early_order = ParsedOrder(
                order_id="ORD-ROUTE-EARLY",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Luigi Verdi",
                customer_email="luigi@example.org",
                customer_phone="+39 333 7654321",
                delivery_address="Via Presto 2",
                delivery_city="Solofra",
                recurring=False,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 20,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME),
                message_id="<route-early@example.org>",
                preferred_delivery_date=delivery_date.isoformat(),
                preferred_delivery_time="Una fascia oraria specifica: dalle 10:00 alle 11:00",
            )
            morning_order = ParsedOrder(
                order_id="ORD-ROUTE-MORNING",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Anna Neri",
                customer_email="anna@example.org",
                customer_phone="+39 333 1112233",
                delivery_address="Via Mattina 3",
                delivery_city="Montoro",
                recurring=False,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 20,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME) + timedelta(minutes=1),
                message_id="<route-morning@example.org>",
                preferred_delivery_date=delivery_date.isoformat(),
                preferred_delivery_time="Mattina",
            )
            afternoon_order = ParsedOrder(
                order_id="ORD-ROUTE-AFTERNOON",
                items=[OrderItem("carta-igienica", "Carta igienica lavanda", 2)],
                customer_name="Paolo Blu",
                customer_email="paolo@example.org",
                customer_phone="+39 333 2223344",
                delivery_address="Via Pomeriggio 4",
                delivery_city="Solofra",
                recurring=False,
                voucher_candidate="",
                voucher_value="",
                products_subtotal="€ 20,00",
                recurring_discount="Nessuno",
                order_datetime=datetime.now(ROME) + timedelta(minutes=2),
                message_id="<route-afternoon@example.org>",
                preferred_delivery_date=delivery_date.isoformat(),
                preferred_delivery_time="Pomeriggio",
            )
            next_recurring_date = ""
            with patch("gestionale.gestionale.send_email"):
                for order in (late_recurring_order, early_order, morning_order, afternoon_order):
                    prepare_order(connection, order, self.site)
                    confirmation = confirm_order(connection, order.order_id, self.site)
                    if order.order_id == late_recurring_order.order_id:
                        self.assertEqual(confirmation["delivery_date"], delivery_date.isoformat())
                        next_recurring_date = confirmation["next_recurring_delivery_date"]
        finally:
            connection.close()

        with urlopen(f"{self.base_url}/api/deliveries?date={today.isoformat()}", timeout=3) as response:
            self.assertEqual(json.load(response)["orders"], [])

        with self._post(
            "/api/route",
            {
                "origin": "Piazza Roma, Montoro",
                "date": delivery_date.isoformat(),
                "start": "09:00",
                "end": "17:00",
                "return_to_origin": False,
            },
            self.base_url,
        ) as response:
            result = json.load(response)

        self.assertEqual(
            [order["order_id"] for order in result["orders"]],
            ["ORD-ROUTE-EARLY", "ORD-ROUTE-AFTERNOON", "ORD-ROUTE-MORNING", "ORD-ROUTE-LATE"],
        )
        self.assertEqual(
            [order["delivery_city"] for order in result["orders"]],
            ["Solofra", "Solofra", "Montoro", "Montoro"],
        )
        maps_query = parse_qs(urlsplit(result["maps_urls"][0]).query)
        self.assertEqual(
            maps_query["waypoints"],
            ["Via Presto 2, Solofra|Via Pomeriggio 4, Solofra|Via Mattina 3, Montoro"],
        )
        self.assertEqual(maps_query["destination"], ["Via Tardi 1, Montoro"])
        calendar = parse_qs(urlsplit(result["calendar_url"]).query)
        self.assertIn("Ogni 2 settimane", calendar["details"][0])
        self.assertIn("giorno Lunedì", calendar["details"][0])
        self.assertIn("precedenza alla partenza", calendar["details"][0])
        self.assertEqual(result["schedule_warnings"], [])

        with urlopen(f"{self.base_url}/api/deliveries?date={next_recurring_date}", timeout=3) as response:
            future_plan = json.load(response)
            self.assertEqual(len(future_plan["orders"]), 1)
            self.assertTrue(future_plan["orders"][0]["is_recurring_projection"])
            self.assertFalse(future_plan["orders"][0]["occurrence_ready"])
            self.assertEqual(future_plan["orders"][0]["recurring_frequency"], "Ogni 2 settimane")

        with self._post(
            "/api/route",
            {
                "origin": "Piazza Roma, Montoro",
                "date": delivery_date.isoformat(),
                "start": "09:00",
                "end": "11:00",
                "return_to_origin": False,
            },
            self.base_url,
        ) as response:
            conflicting_schedule = json.load(response)
        self.assertTrue(any("ORD-ROUTE-LATE" in warning for warning in conflicting_schedule["schedule_warnings"]))
        self.assertTrue(any("15:00–16:00" in warning for warning in conflicting_schedule["schedule_warnings"]))
        self.assertTrue(any("ORD-ROUTE-AFTERNOON" in warning for warning in conflicting_schedule["schedule_warnings"]))


if __name__ == "__main__":
    unittest.main()