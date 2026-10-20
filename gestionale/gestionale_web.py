"""Interfaccia HTTP locale per il gestionale Cartaway."""

from __future__ import annotations

import base64
import json
import imaplib
import math
import re
import sqlite3
import unicodedata
from io import BytesIO
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import gestionale


ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 64 * 1024
DELIVERY_TIMES_PATTERN = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")
TOUR_AVERAGE_SPEED_KMH = 30
TOUR_ROAD_DISTANCE_FACTOR = 1.35
TOUR_MINIMUM_LEG_MINUTES = 10
TOUR_FALLBACK_LEG_MINUTES = 25
TOUR_STOP_SERVICE_MINUTES = 10
TOUR_RELOAD_MINUTES = 20
TOUR_MAX_STOP_WAIT_MINUTES = 120


def _pdf_value(value: Any, fallback: str = "—") -> str:
    normalized = str(value or "").strip()
    return escape(normalized).replace("\n", "<br/>") if normalized else fallback


def _pdf_datetime(value: Any, fallback: str = "Non registrato") -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return fallback
    try:
        return datetime.fromisoformat(normalized).strftime("%d/%m/%Y, ore %H:%M")
    except ValueError:
        return normalized


def _pdf_duration(value: Any) -> str:
    try:
        minutes = max(0, int(value))
    except (TypeError, ValueError):
        return "Da verificare"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours} h {remaining_minutes:02d} min" if hours else f"{remaining_minutes} min"


def _pdf_money(value: Any, fallback: str = "Non registrato", zero_for_none: bool = False) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return fallback
    if zero_for_none and normalized.casefold() in {"nessuno", "nessuna", "nessun"}:
        return "€ 0,00"
    return normalized


def _format_pdf_currency(value: Any) -> str:
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f"€ {formatted}"


def _pdf_product_amounts(
    order: Dict[str, Any],
    catalog_products: Dict[str, Dict[str, Any]],
    prefer_catalog_prices: bool = False,
) -> Tuple[List[Dict[str, str]], Optional[Decimal], bool]:
    request_details = order.get("request_details") or {}
    product_lines = request_details.get("product_lines")
    if not isinstance(product_lines, list):
        product_lines = []
    prices_by_product = {
        str(line.get("product_id") or ""): line
        for line in product_lines
        if isinstance(line, dict)
    }
    rows = []
    line_amounts = []
    missing_line_amount = False

    for item in order.get("availability") or []:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("product_id") or "")
        line = prices_by_product.get(product_id, {})
        catalog_product = catalog_products.get(product_id, {})
        quantity_value = item.get("requested", item.get("quantity", line.get("quantity")))
        quantity = gestionale._parse_money(str(quantity_value or ""))
        unit_price_value = (
            catalog_product.get("price")
            if prefer_catalog_prices
            else line.get("unit_price")
        )
        unit_price = (
            gestionale._parse_money(str(unit_price_value))
            if unit_price_value not in (None, "")
            else None
        )
        if not prefer_catalog_prices and unit_price is None and catalog_product.get("price") is not None:
            unit_price = gestionale._parse_money(str(catalog_product["price"]))
            unit_price_value = _format_pdf_currency(unit_price) if unit_price is not None else None
        if prefer_catalog_prices and unit_price is not None:
            unit_price_value = _format_pdf_currency(unit_price)

        line_total_value = None if prefer_catalog_prices else line.get("line_total")
        line_total = (
            gestionale._parse_money(str(line_total_value))
            if line_total_value not in (None, "")
            else None
        )
        if line_total is None and unit_price is not None and quantity is not None:
            line_total = (unit_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            line_total_value = _format_pdf_currency(line_total)

        if line_total is None:
            missing_line_amount = True
        else:
            line_amounts.append(line_total)

        rows.append({
            "quantity": str(quantity_value or "—"),
            "name": str(item.get("name") or catalog_product.get("name") or "Prodotto"),
            "unit_price": str(unit_price_value or "—"),
            "line_total": str(line_total_value or "—"),
        })

    if rows and not missing_line_amount:
        return rows, sum(line_amounts, Decimal("0")), False

    saved_subtotal = gestionale._parse_money(str(order.get("products_subtotal") or ""))
    if saved_subtotal is not None:
        return rows, saved_subtotal, missing_line_amount
    return rows, None, missing_line_amount or bool(rows)


def _pdf_discount_amount(
    value: Any,
    subtotal: Optional[Decimal],
    recurring: bool,
    requested_total: Optional[Decimal] = None,
    shipping_amount: Optional[Decimal] = None,
) -> Optional[Decimal]:
    normalized = str(value or "").strip()
    if not normalized:
        amount = Decimal("0") if not recurring else None
    elif normalized.casefold() in {"nessuno", "nessuna", "nessun"}:
        return Decimal("0")
    else:
        amount = gestionale._parse_money(normalized)
    if amount is None:
        if not recurring or subtotal is None or requested_total is None or shipping_amount is None:
            return None
        recovered = (subtotal + shipping_amount - requested_total).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return recovered if Decimal("0") <= recovered <= subtotal else None
    amount = abs(amount)
    if "%" in normalized:
        if subtotal is None:
            return None
        return (subtotal * amount / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return amount


def _pdf_shipping_amount(value: Any) -> Optional[Decimal]:
    normalized = str(value or "").strip().casefold()
    if normalized in {"gratuito", "gratuita", "gratis", "free"}:
        return Decimal("0")
    return gestionale._parse_money(str(value or ""))


def _pdf_recover_net_recurring_prices(
    order: Dict[str, Any],
    catalog_products: Dict[str, Dict[str, Any]],
    net_subtotal: Optional[Decimal],
    discount_percent: Any,
) -> Optional[Tuple[List[Dict[str, str]], Decimal, Decimal]]:
    if not order.get("recurring_order") or str(order.get("recurring_discount") or "").strip():
        return None
    if net_subtotal is None:
        return None

    discount_rate = gestionale._parse_money(str(discount_percent or ""))
    if discount_rate is None or discount_rate < 0 or discount_rate >= 100:
        return None
    request_details = order.get("request_details")
    if not isinstance(request_details, dict):
        return None
    requested_total = gestionale._parse_money(str(request_details.get("cost_total") or ""))
    shipping_amount = _pdf_shipping_amount(request_details.get("cost_shipping"))
    if requested_total is None or shipping_amount is None:
        return None
    if abs(net_subtotal + shipping_amount - requested_total) > Decimal("0.01"):
        return None

    gross_rows, gross_subtotal, missing_catalog_prices = _pdf_product_amounts(
        order,
        catalog_products,
        prefer_catalog_prices=True,
    )
    if gross_subtotal is None or missing_catalog_prices:
        return None

    net_subtotal_cents = 0
    for row in gross_rows:
        quantity = gestionale._parse_money(str(row.get("quantity") or ""))
        unit_price = gestionale._parse_money(str(row.get("unit_price") or ""))
        if (
            quantity is None
            or quantity <= 0
            or quantity != quantity.to_integral_value()
            or unit_price is None
        ):
            return None
        unit_price_cents = int((unit_price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        net_unit_price_cents = int(
            (
                Decimal(unit_price_cents)
                * (Decimal("100") - discount_rate)
                / Decimal("100")
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        net_subtotal_cents += net_unit_price_cents * int(quantity)

    expected_net_subtotal = Decimal(net_subtotal_cents) / Decimal("100")
    if abs(expected_net_subtotal - net_subtotal) > Decimal("0.01"):
        return None
    if abs(expected_net_subtotal + shipping_amount - requested_total) > Decimal("0.01"):
        return None
    discount_amount = (gross_subtotal - expected_net_subtotal).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if discount_amount < 0:
        return None
    return gross_rows, gross_subtotal, discount_amount


def _pdf_payment_summary(
    order: Dict[str, Any],
    request_details: Dict[str, Any],
    calculated_total: Optional[Decimal] = None,
) -> Dict[str, str]:
    confirmed_total_value = order.get("confirmed_total") or request_details.get("confirmed_total")
    paid_amount_value = (
        order.get("paid_amount")
        or request_details.get("paid_amount")
        or request_details.get("amount_paid")
    )
    payment_status = str(
        order.get("payment_status") or request_details.get("payment_status") or ""
    ).strip().casefold()
    confirmed_total = (
        gestionale._parse_money(str(confirmed_total_value))
        if confirmed_total_value not in (None, "")
        else None
    )
    requested_total = gestionale._parse_money(str(request_details.get("cost_total") or ""))
    if confirmed_total is None and calculated_total is not None and requested_total is not None:
        if abs(calculated_total - requested_total) <= Decimal("0.01"):
            confirmed_total = requested_total
    paid_amount = (
        gestionale._parse_money(str(paid_amount_value))
        if paid_amount_value not in (None, "")
        else None
    )

    if confirmed_total is None:
        confirmed_label = "Non registrato"
        remaining_label = "Non registrato"
        state = {
            "paid": "Già pagato",
            "pagato": "Già pagato",
            "pagata": "Già pagato",
            "unpaid": "Da incassare",
            "da incassare": "Da incassare",
            "partial": "Importo residuo non registrato",
            "parziale": "Importo residuo non registrato",
        }.get(payment_status, "Non registrato")
        if paid_amount is not None and paid_amount > 0 and state == "Non registrato":
            state = "Importo residuo non registrato"
    else:
        confirmed_label = _format_pdf_currency(confirmed_total)
        zero_amount = confirmed_total - confirmed_total
        if payment_status in {"paid", "pagato", "pagata", "già pagato"}:
            paid_amount = confirmed_total
        remaining = confirmed_total - paid_amount if paid_amount is not None else confirmed_total
        remaining = max(remaining, zero_amount)
        payment_method = str(request_details.get("payment_information") or "").strip().casefold()
        if remaining <= 0 or payment_status in {"paid", "pagato", "pagata", "già pagato"}:
            state = "Già pagato"
            remaining_label = _format_pdf_currency(zero_amount)
        elif payment_status in {"partial", "parziale"} and paid_amount is None:
            state = "Importo residuo non registrato"
            remaining_label = "Non registrato"
        elif paid_amount is not None and paid_amount > 0:
            state = "Importo residuo"
            remaining_label = _format_pdf_currency(remaining)
        elif payment_status in {"unpaid", "da incassare"} or any(
            keyword in payment_method for keyword in ("alla consegna", "contrassegno")
        ):
            state = "Da incassare"
            remaining_label = _format_pdf_currency(remaining)
            if paid_amount is None:
                paid_amount = zero_amount
        elif paid_amount == 0:
            state = "Da incassare"
            remaining_label = _format_pdf_currency(remaining)
        else:
            state = "Non registrato"
            remaining_label = "Non registrato"

    return {
        "method": _pdf_money(request_details.get("payment_information"), "Non indicata"),
        "confirmed_total": confirmed_label,
        "paid_amount": _format_pdf_currency(paid_amount) if paid_amount is not None else "Non registrato",
        "remaining": remaining_label,
        "state": state,
    }


def _pdf_currency_label(value: Any, fallback: str = "Non registrato") -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return fallback
    if not any(character.isalpha() for character in normalized):
        amount = gestionale._parse_money(normalized)
        if amount is not None:
            return _format_pdf_currency(amount)
    return normalized


def _pdf_cost_summary_rows(
    order: Dict[str, Any],
    request_details: Dict[str, Any],
    products_subtotal: str,
    discount_label: str,
    calculated_total: Optional[Decimal],
    payment_summary: Dict[str, str],
) -> List[Tuple[str, str]]:
    tax_value = str(request_details.get("cost_tax") or "").strip()
    tax_label = (
        "IVA inclusa (di cui)"
        if "inclusa nei prezzi" in tax_value.casefold()
        else "IVA prodotti"
    )
    rows = [
        ("Totale prodotti (IVA inclusa)", products_subtotal),
        ("Sconto ricorrente" if order.get("recurring_order") else "Sconto", discount_label),
        (
            "Costo consegna",
            _pdf_currency_label(request_details.get("cost_shipping"), "Non indicato"),
        ),
        (tax_label, _pdf_currency_label(tax_value, "Non indicata")),
    ]

    requested_value = str(request_details.get("cost_total") or "").strip()
    requested_total = gestionale._parse_money(requested_value) if requested_value else None
    confirmed_value = order.get("confirmed_total")
    if confirmed_value in (None, ""):
        confirmed_value = request_details.get("confirmed_total")
    confirmed_label = str(confirmed_value).strip() if confirmed_value not in (None, "") else ""
    confirmed_total = (
        gestionale._parse_money(confirmed_label)
        if confirmed_label
        else None
    )
    confirmed_is_registered = confirmed_total is not None
    total_values = [
        value
        for value in (requested_total, calculated_total, confirmed_total)
        if value is not None
    ]
    values_agree = (
        bool(total_values)
        and not (requested_value and requested_total is None)
        and all(abs(value - total_values[0]) <= Decimal("0.01") for value in total_values[1:])
    )

    if values_agree:
        if confirmed_total is not None:
            rows.append(("Totale ordine confermato", _format_pdf_currency(confirmed_total)))
        elif calculated_total is not None:
            rows.append(("Totale ordine calcolato", _format_pdf_currency(calculated_total)))
        else:
            rows.append((
                "Totale indicato nella richiesta",
                _pdf_currency_label(requested_value, "Non indicato"),
            ))
    else:
        if requested_value:
            rows.append((
                "Totale indicato nella richiesta",
                _pdf_currency_label(requested_value, "Non indicato"),
            ))
        if calculated_total is not None:
            rows.append(("Totale ordine calcolato", _format_pdf_currency(calculated_total)))
        if confirmed_is_registered:
            rows.append((
                "Totale confermato",
                _pdf_currency_label(confirmed_label, "Non registrato"),
            ))
        if not requested_value and calculated_total is None and not confirmed_is_registered:
            rows.append(("Totale ordine", "Non registrato"))

    for key, label in (
        ("paid_amount", "Già pagato"),
        ("remaining", "Residuo da incassare"),
    ):
        value = str(payment_summary.get(key) or "Non registrato").strip()
        if value.casefold() != "non registrato":
            rows.append((label, _pdf_currency_label(value, "Non registrato")))
    return rows


def _pdf_payment_rows(payment_summary: Dict[str, str]) -> List[Tuple[str, str]]:
    method = payment_summary.get("method", "Non indicata")
    state = payment_summary.get("state", "Non registrato")
    if method == "Non indicata" and state == "Non registrato":
        return [("Pagamento", "Non registrato - verificare prima dell'incasso")]
    return [("Modalità di pagamento", method), ("Stato incasso", state)]


class _NumberedCanvas(Canvas):
    def __init__(self, *args: Any, page_renderer: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []
        self._page_renderer = page_renderer

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for page_number, page_state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(page_state)
            self._page_renderer(self, page_number, page_count)
            Canvas.showPage(self)
        Canvas.save(self)


def _attach_delivery_plan_metadata(result: Dict[str, Any]) -> None:
    generated_at = datetime.now(gestionale.ROME).replace(microsecond=0)
    result["generated_at"] = generated_at.isoformat()
    result["plan_reference"] = (
        f"PIANO-{generated_at.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6].upper()}"
    )
    for vehicle in result.get("vehicles", []):
        vehicle["generated_at"] = result["generated_at"]
        vehicle["plan_reference"] = result["plan_reference"]


def _vehicle_delivery_pdf(
    brand: str,
    delivery_date: str,
    vehicle: Dict[str, Any],
    catalog_products: Optional[Dict[str, Dict[str, Any]]] = None,
    recurring_discount_percent: Any = None,
) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
        title=(
            f"Consegne {vehicle.get('display_name') or vehicle.get('name') or 'Furgone'} "
            f"{vehicle.get('plan_reference') or ''}"
        ).strip(),
        author=brand,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CartawayTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=0,
        textColor=colors.HexColor("#173b35"),
        spaceAfter=2 * mm,
    ))
    styles.add(ParagraphStyle(
        name="CartawaySubtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4e5b57"),
        spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name="OrderHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#173b35"),
        spaceBefore=2 * mm,
        spaceAfter=2 * mm,
    ))
    styles.add(ParagraphStyle(
        name="Cell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    ))
    styles.add(ParagraphStyle(
        name="CellLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#4e5b57"),
    ))
    styles.add(ParagraphStyle(
        name="TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="SmallNote",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4e5b57"),
    ))
    styles.add(ParagraphStyle(
        name="Verify",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#a2342b"),
    ))

    def paragraph(value: Any, style: str = "Cell", fallback: str = "—") -> Paragraph:
        return Paragraph(_pdf_value(value, fallback), styles[style])

    orders = vehicle.get("orders") or []
    vehicle_name = vehicle.get("name") or "Furgone"
    tour_number = vehicle.get("tour_number", "Da verificare")
    tour_count = vehicle.get("tour_count", "Da verificare")
    plan_reference = str(vehicle.get("plan_reference") or "Da verificare")
    generated_at = vehicle.get("generated_at")
    try:
        formatted_date = date.fromisoformat(delivery_date).strftime("%d/%m/%Y")
    except ValueError:
        formatted_date = delivery_date
    story = [
        paragraph(brand, "CartawayTitle", "Cartaway"),
        paragraph("Distinta di consegna", "OrderHeading"),
        paragraph(
            f"{len(orders)} consegne | Giro {tour_number}/{tour_count}",
            "CartawaySubtitle",
        ),
    ]
    summary_rows = [
        [paragraph("Furgone", "CellLabel"), paragraph(vehicle_name)],
        [paragraph("Numero giro", "CellLabel"), paragraph(f"{tour_number}/{tour_count}")],
        [paragraph("Partenza", "CellLabel"), paragraph(_pdf_datetime(vehicle.get("departure_at")))],
        [
            paragraph("Ultimo arrivo stimato", "CellLabel"),
            paragraph(_pdf_datetime(vehicle.get("last_arrival_at"))),
        ],
        [
            paragraph("Ultima consegna terminata", "CellLabel"),
            paragraph(_pdf_datetime(vehicle.get("last_delivery_completed_at"))),
        ],
        [
            paragraph("Rientro previsto al deposito", "CellLabel"),
            paragraph(
                _pdf_datetime(vehicle.get("estimated_return_at"), "Non previsto")
                if vehicle.get("return_to_origin")
                else "Non previsto"
            ),
        ],
        [paragraph("Durata totale del giro", "CellLabel"), paragraph(_pdf_duration(vehicle.get("duration_minutes")))],
        [
            paragraph("Disponibile per il giro successivo", "CellLabel"),
            paragraph(
                f"{_pdf_datetime(vehicle.get('next_available_at'))} "
                f"(ricarica di {vehicle.get('reload_duration_minutes', TOUR_RELOAD_MINUTES)} min inclusa)"
                if vehicle.get("next_available_at")
                else "Nessun giro successivo pianificato"
            ),
        ],
    ]
    summary_table = Table(summary_rows, colWidths=[50 * mm, 134 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f1")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7dfdc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([paragraph("Riepilogo giro", "OrderHeading"), summary_table])
    for warning in vehicle.get("schedule_warnings") or []:
        story.append(Paragraph(f"- {_pdf_value(warning)}", styles["Verify"]))
    story.append(Spacer(1, 3 * mm))

    for index, order in enumerate(orders, start=1):
        if index > 1:
            story.append(PageBreak())
        request_details = order.get("request_details")
        if not isinstance(request_details, dict):
            request_details = {}
        product_rows, product_subtotal, missing_product_prices = _pdf_product_amounts(
            order,
            catalog_products or {},
        )
        recurring_discount = order.get("recurring_discount")
        if not recurring_discount and not order.get("recurring_order"):
            recurring_discount = "Nessuno"
        requested_total = gestionale._parse_money(str(request_details.get("cost_total") or ""))
        shipping_amount = _pdf_shipping_amount(request_details.get("cost_shipping"))
        discount_amount = _pdf_discount_amount(
            recurring_discount,
            product_subtotal,
            bool(order.get("recurring_order")),
            requested_total,
            shipping_amount,
        )
        if order.get("recurring_order") and not recurring_discount:
            recovered_prices = _pdf_recover_net_recurring_prices(
                order,
                catalog_products or {},
                product_subtotal,
                recurring_discount_percent,
            )
            if recovered_prices:
                product_rows, product_subtotal, discount_amount = recovered_prices
            else:
                discount_amount = None
        products_subtotal = (
            _format_pdf_currency(product_subtotal)
            if product_subtotal is not None
            else _pdf_money(order.get("products_subtotal"))
        )

        block = [
            paragraph(
                f"Consegna {index} - Ordine #{order.get('order_id') or ''}",
                "OrderHeading",
            ),
        ]
        customer_rows = [
            [
                paragraph("Cliente", "CellLabel"),
                paragraph(order.get("customer_name")),
                paragraph("Telefono", "CellLabel"),
                paragraph(order.get("customer_phone")),
            ],
            [
                paragraph("Email", "CellLabel"),
                paragraph(order.get("customer_email")),
                paragraph("Arrivo stimato", "CellLabel"),
                paragraph(_pdf_datetime(order.get("estimated_arrival_at"), "Non pianificato")),
            ],
            [
                paragraph("Indirizzo", "CellLabel"),
                paragraph(order.get("delivery_address")),
                "",
                "",
            ],
            [
                paragraph("Città", "CellLabel"),
                paragraph(order.get("delivery_city")),
                paragraph("Fascia", "CellLabel"),
                paragraph(order.get("preferred_delivery_time")),
            ],
            [
                paragraph("Note", "CellLabel"),
                paragraph(order.get("delivery_notes"), fallback="Nessuna"),
                "",
                "",
            ],
        ]
        if str(request_details.get("billing_requested") or "").casefold() in {"sì", "si", "yes", "true"}:
            customer_rows.append([
                paragraph("Fatturare a", "CellLabel"),
                paragraph(request_details.get("billing_business_name") or order.get("customer_name")),
                paragraph("P. IVA", "CellLabel"),
                paragraph(request_details.get("billing_vat_number")),
            ])
            customer_rows.append([
                paragraph("SDI / PEC", "CellLabel"),
                paragraph(request_details.get("billing_recipient")),
                "",
                "",
            ])
        customer_table = Table(customer_rows, colWidths=[18 * mm, 62 * mm, 18 * mm, 86 * mm])
        customer_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f1")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef3f1")),
            ("SPAN", (1, 2), (3, 2)),
            ("SPAN", (1, 4), (3, 4)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7dfdc")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        block.append(customer_table)
        block.append(Spacer(1, 2 * mm))

        item_rows = [[
            paragraph("Q.tà", "TableHeader"),
            paragraph("Prodotto", "TableHeader"),
            paragraph("Prezzo unit.", "TableHeader"),
            paragraph("Subtotale", "TableHeader"),
        ]]
        for item in product_rows:
            item_rows.append([
                paragraph(item.get("quantity", "")),
                paragraph(item.get("name")),
                paragraph(item.get("unit_price")),
                paragraph(item.get("line_total")),
            ])
        if len(item_rows) == 1:
            item_rows.append([
                paragraph("—"),
                paragraph("Nessuna riga prodotto presente"),
                paragraph("—"),
                paragraph("—"),
            ])
        item_table = Table(
            item_rows,
            colWidths=[14 * mm, 88 * mm, 38 * mm, 44 * mm],
            repeatRows=1,
        )
        item_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173b35")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7dfdc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        block.append(item_table)

        payment_summary = _pdf_payment_summary(order, request_details)
        calculated_total = None
        if product_subtotal is not None and discount_amount is not None and shipping_amount is not None:
            calculated_total = max(
                product_subtotal - discount_amount + shipping_amount,
                Decimal("0"),
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            payment_summary = _pdf_payment_summary(order, request_details, calculated_total)
        missing_financial_data = []
        if missing_product_prices or products_subtotal == "Non registrato":
            missing_financial_data.append("prezzi prodotto")
        if order.get("recurring_order") and discount_amount is None:
            missing_financial_data.append("sconto ricorrente")
        if calculated_total is not None and requested_total is not None:
            if abs(calculated_total - requested_total) > Decimal("0.01"):
                missing_financial_data.append("il totale richiesto differisce dal calcolo")
        elif payment_summary["confirmed_total"] == "Non registrato":
            missing_financial_data.append("il totale da incassare")
        if missing_financial_data:
            block.append(Paragraph(
                "<b>Dati economici da verificare prima dell'incasso:</b> "
                f"{_pdf_value('; '.join(missing_financial_data))}.",
                styles["Verify"],
            ))
        if order.get("recurring_order") and discount_amount is not None:
            discount_label = (
                f"−{_format_pdf_currency(discount_amount)}"
                if discount_amount > 0
                else _format_pdf_currency(discount_amount)
            )
        else:
            discount_label = _pdf_money(
                recurring_discount,
                "Non indicato",
                zero_for_none=not bool(order.get("recurring_order")),
            )
        costs = _pdf_cost_summary_rows(
            order,
            request_details,
            products_subtotal,
            discount_label,
            calculated_total,
            payment_summary,
        )
        cost_rows = []
        for label, value in costs:
            cost_rows.append([paragraph(label, "CellLabel"), paragraph(value)])
        cost_table = Table(cost_rows, colWidths=[140 * mm, 44 * mm], hAlign="RIGHT")
        cost_table.setStyle(TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#173b35")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef3f1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        block.extend([Spacer(1, 2 * mm), cost_table])
        payment_table = Table([
            [paragraph(label, "CellLabel"), paragraph(value)]
            for label, value in _pdf_payment_rows(payment_summary)
        ], colWidths=[50 * mm, 134 * mm])
        payment_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f1")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7dfdc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        block.extend([Spacer(1, 2 * mm), payment_table])
        block.append(Paragraph("Firma per ricevuta: __________________________________________", styles["SmallNote"]))
        story.append(KeepTogether(block[:2]))
        story.extend(block[2:])
        story.append(Spacer(1, 5 * mm))

    def draw_page_chrome(pdf_canvas: Canvas, page_number: int, page_count: int) -> None:
        pdf_canvas.saveState()
        pdf_canvas.setFillColor(colors.HexColor("#173b35"))
        pdf_canvas.setFont("Helvetica-Bold", 7)
        pdf_canvas.drawString(
            13 * mm,
            A4[1] - 7 * mm,
            f"{formatted_date} | {vehicle_name} | Giro {tour_number}/{tour_count}",
        )
        pdf_canvas.setFont("Helvetica", 6.5)
        pdf_canvas.drawString(
            13 * mm,
            A4[1] - 11 * mm,
            f"Piano {plan_reference} | Generato {_pdf_datetime(generated_at)}",
        )
        pdf_canvas.setFillColor(colors.HexColor("#5c6864"))
        pdf_canvas.setFont("Helvetica", 7)
        pdf_canvas.drawString(
            13 * mm,
            8 * mm,
            "Documento operativo non fiscale. Verificare importo e pagamento prima dell'incasso.",
        )
        pdf_canvas.drawRightString(A4[0] - 13 * mm, 8 * mm, f"Pagina {page_number} di {page_count}")
        pdf_canvas.restoreState()

    def numbered_canvasmaker(*args: Any, **kwargs: Any) -> _NumberedCanvas:
        return _NumberedCanvas(*args, page_renderer=draw_page_chrome, **kwargs)

    document.build(story, canvasmaker=numbered_canvasmaker)
    return output.getvalue()


def _attach_vehicle_delivery_pdfs(
    brand: str,
    delivery_date: str,
    vehicles: Sequence[Dict[str, Any]],
    catalog_products: Optional[Dict[str, Dict[str, Any]]] = None,
    recurring_discount_percent: Any = None,
) -> None:
    for vehicle in vehicles:
        if vehicle.get("orders"):
            pdf_bytes = _vehicle_delivery_pdf(
                brand,
                delivery_date,
                vehicle,
                catalog_products,
                recurring_discount_percent,
            )
            vehicle["delivery_pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")


def _requested_delivery_times(value: str) -> List[time]:
    return [
        datetime.strptime(match, "%H:%M").time()
        for match in DELIVERY_TIMES_PATTERN.findall(value)[:2]
    ]


def _delivery_time_sort_key(order: Dict[str, Any]) -> Tuple[int, int]:
    preference = str(order.get("preferred_delivery_time") or "").strip().casefold()
    requested_times = _requested_order_times(order)
    if requested_times:
        requested_start = requested_times[0]
        minutes = requested_start.hour * 60 + requested_start.minute
        return (0 if requested_start < time(12, 0) else 2, minutes)
    if "mattina" in preference:
        return (1, 9 * 60)
    if "pomeriggio" in preference:
        return (2, 12 * 60)
    return (1, 0)


def _normalized_place(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(re.findall(r"[a-z]+", ascii_text))


def _delivery_city_key(order: Dict[str, Any]) -> Tuple[str, str]:
    city = _normalized_place(order.get("delivery_city"))
    if city:
        return ("city", city)
    return ("order", str(order.get("order_id") or ""))


def _origin_city_key(origin: str, orders: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    normalized_origin = f" {_normalized_place(origin)} "
    matching_cities = {
        key
        for order in orders
        if (key := _delivery_city_key(order))[0] == "city"
        and len(key[1]) >= 4
        and f" {key[1]} " in normalized_origin
    }
    return max(matching_cities, key=lambda city: len(city[1]), default=None)


def _allocate_vehicle_loads(
    orders: Sequence[Dict[str, Any]],
    vehicles: Sequence[Dict[str, Any]],
    product_volumes: Dict[str, float],
) -> Dict[str, Any]:
    vehicle_loads = [
        {
            "name": str(vehicle["name"]),
            "capacity_liters": float(vehicle["capacity_liters"]),
            "used_volume_liters": 0.0,
            "remaining_liters": float(vehicle["capacity_liters"]),
            "orders": [],
            "products": {},
        }
        for vehicle in vehicles
    ]
    product_totals: Dict[str, Dict[str, Any]] = {}
    loadable_orders = []
    unassigned_orders = []

    for order_index, order in enumerate(orders):
        order_volume = 0.0
        order_products = []
        missing_products = []
        for item in order.get("availability", []):
            product_id = str(item.get("product_id") or "").strip()
            quantity = item.get("requested")
            if not product_id or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                continue
            name = str(item.get("name") or product_id)
            unit_volume = product_volumes.get(product_id)
            summary = product_totals.setdefault(
                product_id,
                {
                    "product_id": product_id,
                    "name": name,
                    "quantity": 0,
                    "unit_volume_liters": unit_volume,
                    "total_volume_liters": None,
                },
            )
            summary["quantity"] += quantity
            if unit_volume is None or not math.isfinite(unit_volume) or unit_volume <= 0:
                missing_products.append(name)
                continue
            if summary["total_volume_liters"] is None:
                summary["total_volume_liters"] = 0.0
                summary["unit_volume_liters"] = unit_volume
            summary["total_volume_liters"] += unit_volume * quantity
            order_volume += unit_volume * quantity
            order_products.append((product_id, name, quantity, unit_volume * quantity))

        if not order_products and not missing_products:
            unassigned_orders.append({
                "order": order,
                "required_volume_liters": None,
                "reason": "L'ordine non contiene quantità prodotto valide.",
            })
        elif missing_products:
            unassigned_orders.append({
                "order": order,
                "required_volume_liters": None,
                "reason": "Ingombro da configurare: " + ", ".join(sorted(set(missing_products))) + ".",
            })
        else:
            loadable_orders.append((order_index, order_volume, order, order_products))

    for _, order_volume, order, order_products in sorted(
        loadable_orders,
        key=lambda item: (-item[1], item[0]),
    ):
        fitting_vehicles = [
            (vehicle["capacity_liters"] - vehicle["used_volume_liters"] - order_volume, index)
            for index, vehicle in enumerate(vehicle_loads)
            if vehicle["remaining_liters"] + 1e-9 >= order_volume
        ]
        if not fitting_vehicles:
            unassigned_orders.append({
                "order": order,
                "required_volume_liters": round(order_volume, 3),
                "reason": (
                    "Nessun furgone ha spazio residuo sufficiente "
                    f"per {order_volume:.3f} L."
                ),
            })
            continue

        _, vehicle_index = min(fitting_vehicles)
        vehicle = vehicle_loads[vehicle_index]
        assigned_order = dict(order)
        assigned_order["load_volume_liters"] = round(order_volume, 3)
        vehicle["orders"].append(assigned_order)
        vehicle["used_volume_liters"] += order_volume
        vehicle["remaining_liters"] -= order_volume
        for product_id, name, quantity, total_volume in order_products:
            product = vehicle["products"].setdefault(
                product_id,
                {
                    "product_id": product_id,
                    "name": name,
                    "quantity": 0,
                    "total_volume_liters": 0.0,
                },
            )
            product["quantity"] += quantity
            product["total_volume_liters"] += total_volume

    for vehicle in vehicle_loads:
        vehicle["used_volume_liters"] = round(vehicle["used_volume_liters"], 3)
        vehicle["remaining_liters"] = round(max(0.0, vehicle["remaining_liters"]), 3)
        vehicle["products"] = sorted(
            (
                {**product, "total_volume_liters": round(product["total_volume_liters"], 3)}
                for product in vehicle["products"].values()
            ),
            key=lambda product: product["name"].casefold(),
        )

    products = sorted(
        (
            {
                **product,
                "unit_volume_liters": (
                    round(product["unit_volume_liters"], 3)
                    if product["unit_volume_liters"] is not None
                    else None
                ),
                "total_volume_liters": (
                    round(product["total_volume_liters"], 3)
                    if product["total_volume_liters"] is not None
                    else None
                ),
            }
            for product in product_totals.values()
        ),
        key=lambda product: product["name"].casefold(),
    )
    return {
        "products": products,
        "vehicles": vehicle_loads,
        "unassigned_orders": unassigned_orders,
    }


def _requested_order_times(order: Dict[str, Any]) -> List[time]:
    for value in (order.get("preferred_delivery_time"), order.get("delivery_notes")):
        requested_times = _requested_delivery_times(str(value or ""))
        if requested_times:
            return requested_times
    return []


def _route_time_constraint(order: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    requested_times = _requested_order_times(order)
    if requested_times:
        requested_start = requested_times[0]
        minutes = requested_start.hour * 60 + requested_start.minute
        return (0 if requested_start < time(12, 0) else 2, minutes)
    preference = str(order.get("preferred_delivery_time") or "").strip().casefold()
    if "mattina" in preference:
        return (1, 9 * 60)
    if "pomeriggio" in preference:
        return (2, 12 * 60)
    return None


def _delivery_location_coordinates(site: Dict[str, Any]) -> Dict[str, Tuple[float, float]]:
    coordinates: Dict[str, Tuple[float, float]] = {}
    zones = site.get("delivery_zones")
    if not isinstance(zones, list):
        return coordinates
    for zone in zones:
        if not isinstance(zone, dict) or not isinstance(zone.get("locations"), list):
            continue
        for location in zone["locations"]:
            if not isinstance(location, dict):
                continue
            city = _normalized_place(location.get("name"))
            try:
                latitude = float(location["lat"])
                longitude = float(location["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if city and -90 <= latitude <= 90 and -180 <= longitude <= 180:
                coordinates[city] = (latitude, longitude)
    return coordinates


def _matching_location_coordinate(
    value: str,
    coordinates: Dict[str, Tuple[float, float]],
) -> Optional[Tuple[float, float]]:
    normalized_value = f" {_normalized_place(value)} "
    matches = [
        (city, point)
        for city, point in coordinates.items()
        if f" {city} " in normalized_value
    ]
    return max(matches, key=lambda match: len(match[0]))[1] if matches else None


def _city_coordinate(
    city_key: Tuple[str, str],
    coordinates: Dict[str, Tuple[float, float]],
) -> Optional[Tuple[float, float]]:
    city_name = city_key[1]
    if city_name in coordinates:
        return coordinates[city_name]
    matches = [
        (name, point)
        for name, point in coordinates.items()
        if city_name.startswith(f"{name} ") or name.startswith(f"{city_name} ")
    ]
    return max(matches, key=lambda match: len(match[0]))[1] if matches else None


def _distance_km(
    first_point: Tuple[float, float],
    second_point: Tuple[float, float],
) -> float:
    first_latitude, first_longitude = map(math.radians, first_point)
    second_latitude, second_longitude = map(math.radians, second_point)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = second_longitude - first_longitude
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude) * math.cos(second_latitude) * math.sin(longitude_delta / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def _minimum_distance_city_order(
    city_keys: List[Tuple[str, str]],
    coordinates: Dict[Tuple[str, str], Tuple[float, float]],
    origin_coordinate: Tuple[float, float],
    city_priorities: Dict[Tuple[str, str], Tuple[int, int]],
    return_to_origin: bool,
) -> List[Tuple[str, str]]:
    city_count = len(city_keys)
    priorities = [city_priorities.get(city_key, (1, 0)) for city_key in city_keys]
    priority_levels = sorted(set(priorities))
    distance_matrix = [
        [
            _distance_km(coordinates[first_city], coordinates[second_city])
            for second_city in city_keys
        ]
        for first_city in city_keys
    ]
    origin_distances = [_distance_km(origin_coordinate, coordinates[city_key]) for city_key in city_keys]

    if city_count > 12:
        route_indexes = []
        for priority in priority_levels:
            unplaced_indexes = [index for index, value in enumerate(priorities) if value == priority]
            previous_index = None
            while unplaced_indexes:
                if previous_index is None:
                    next_index = min(
                        unplaced_indexes,
                        key=lambda index: (origin_distances[index], index),
                    )
                else:
                    next_index = min(
                        unplaced_indexes,
                        key=lambda index: (distance_matrix[previous_index][index], index),
                    )
                route_indexes.append(next_index)
                unplaced_indexes.remove(next_index)
                previous_index = next_index
        return [city_keys[index] for index in route_indexes]

    full_mask = (1 << city_count) - 1
    costs: Dict[Tuple[int, int], float] = {}
    parents: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}
    first_priority = priority_levels[0]
    start_indexes = [index for index, priority in enumerate(priorities) if priority == first_priority]
    for city_index in start_indexes:
        state = (1 << city_index, city_index)
        costs[state] = origin_distances[city_index]
        parents[state] = None

    for visited_mask in range(1, full_mask + 1):
        for last_index in range(city_count):
            state = (visited_mask, last_index)
            if state not in costs or visited_mask == full_mask:
                continue
            next_priority = min(
                priority
                for index, priority in enumerate(priorities)
                if not visited_mask & (1 << index)
            )
            for next_index in range(city_count):
                next_bit = 1 << next_index
                if visited_mask & next_bit:
                    continue
                if priorities[next_index] != next_priority:
                    continue
                next_state = (visited_mask | next_bit, next_index)
                next_cost = costs[state] + distance_matrix[last_index][next_index]
                if next_cost < costs.get(next_state, math.inf) - 1e-9:
                    costs[next_state] = next_cost
                    parents[next_state] = state

    best_state: Optional[Tuple[int, int]] = None
    best_cost = math.inf
    for last_index in range(city_count):
        state = (full_mask, last_index)
        if state not in costs:
            continue
        total_cost = costs[state] + (origin_distances[last_index] if return_to_origin else 0)
        if total_cost < best_cost - 1e-9:
            best_state = state
            best_cost = total_cost
    if best_state is None:
        return city_keys

    route_indexes = []
    state = best_state
    while state is not None:
        route_indexes.append(state[1])
        state = parents[state]
    route_indexes.reverse()
    return [city_keys[index] for index in route_indexes]


def _fallback_city_order(
    orders: List[Dict[str, Any]],
    origin: str,
) -> List[Dict[str, Any]]:
    time_ordered = sorted(orders, key=_delivery_time_sort_key)
    city_rank: Dict[Tuple[str, str], int] = {}
    city_time_priority: Dict[Tuple[str, str], Tuple[int, int]] = {}
    for order in time_ordered:
        city_key = _delivery_city_key(order)
        city_rank.setdefault(city_key, len(city_rank))
        order_priority = _delivery_time_sort_key(order)
        if city_key not in city_time_priority or order_priority < city_time_priority[city_key]:
            city_time_priority[city_key] = order_priority
    origin_city = _origin_city_key(origin, time_ordered)
    if origin_city in city_rank:
        earlier_cities = [
            city_key
            for city_key in city_rank
            if city_key != origin_city and city_time_priority[city_key] < city_time_priority[origin_city]
        ]
        city_order = earlier_cities + [origin_city] + [
            city_key for city_key in city_rank if city_key != origin_city and city_key not in earlier_cities
        ]
        city_rank = {city_key: rank for rank, city_key in enumerate(city_order)}
    return sorted(
        time_ordered,
        key=lambda order: (city_rank[_delivery_city_key(order)], _delivery_time_sort_key(order)),
    )


def _group_route_orders_by_city(
    orders: List[Dict[str, Any]],
    origin: str = "",
    site: Optional[Dict[str, Any]] = None,
    return_to_origin: bool = False,
) -> List[Dict[str, Any]]:
    if not orders:
        return []
    if site is None:
        return _fallback_city_order(orders, origin)

    grouped_orders: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for order in orders:
        grouped_orders.setdefault(_delivery_city_key(order), []).append(order)
    location_coordinates = _delivery_location_coordinates(site)
    city_coordinates = {
        city_key: _city_coordinate(city_key, location_coordinates)
        for city_key in grouped_orders
    }
    if not location_coordinates or any(point is None for point in city_coordinates.values()):
        return _fallback_city_order(orders, origin)
    origin_coordinate = _matching_location_coordinate(origin, location_coordinates)
    origin_city = _origin_city_key(origin, orders)
    if origin_coordinate is None and origin_city is not None:
        origin_coordinate = city_coordinates.get(origin_city)
    if origin_coordinate is None:
        return _fallback_city_order(orders, origin)

    city_priorities: Dict[Tuple[str, str], Tuple[int, int]] = {}
    for city_key, city_orders in grouped_orders.items():
        constraints = [
            priority
            for order in city_orders
            if (priority := _route_time_constraint(order)) is not None
        ]
        city_priorities[city_key] = min(constraints) if constraints else (1, 0)
    if origin_city in city_priorities and city_priorities[origin_city] == (1, 0):
        city_priorities[origin_city] = (0, -1)

    route_city_order = _minimum_distance_city_order(
        list(grouped_orders),
        {city_key: point for city_key, point in city_coordinates.items() if point is not None},
        origin_coordinate,
        city_priorities,
        return_to_origin,
    )
    return [
        order
        for city_key in route_city_order
        for order in sorted(grouped_orders[city_key], key=_delivery_time_sort_key)
    ]


def _route_schedule_warning(
    order: Dict[str, Any],
    route_start: time,
    route_end: time,
) -> str:
    preference = str(order.get("preferred_delivery_time") or "").strip()
    normalized_preference = preference.casefold()
    requested_times = _requested_order_times(order)
    if not requested_times:
        if "mattina" in normalized_preference:
            conflict = route_start >= time(12, 0)
            requested_label = "Mattina"
        elif "pomeriggio" in normalized_preference:
            conflict = route_end <= time(12, 0)
            requested_label = "Pomeriggio"
        else:
            return ""
    else:
        requested_start = requested_times[0]
        requested_end = requested_times[-1]
        if requested_end < requested_start:
            conflict = True
        elif requested_start == requested_end:
            conflict = not route_start <= requested_start <= route_end
        else:
            conflict = requested_end <= route_start or requested_start >= route_end
        requested_label = requested_start.strftime("%H:%M")
        if requested_end != requested_start:
            requested_label += f"–{requested_end.strftime('%H:%M')}"
    if not conflict:
        return ""
    return (
        f"#{order['order_id']}: preferenza richiesta {requested_label} non compatibile "
        f"con il giro {route_start.strftime('%H:%M')}–{route_end.strftime('%H:%M')}."
    )


def _delivery_window_minutes(
    order: Dict[str, Any],
    shift_start_minute: int,
    shift_end_minute: int,
) -> Optional[Tuple[int, int]]:
    requested_times = _requested_order_times(order)
    if requested_times:
        start = requested_times[0].hour * 60 + requested_times[0].minute
        end = requested_times[-1].hour * 60 + requested_times[-1].minute
        return start, end

    preference = str(order.get("preferred_delivery_time") or "").strip().casefold()
    if "mattina" in preference:
        return max(shift_start_minute, 9 * 60), min(shift_end_minute, 12 * 60)
    if "pomeriggio" in preference:
        return max(shift_start_minute, 12 * 60), min(shift_end_minute, 17 * 60)
    return None


def _tour_order_sort_key(order: Dict[str, Any]) -> Tuple[int, int, str]:
    return (*_delivery_time_sort_key(order), str(order.get("order_id") or ""))


def _estimated_leg_minutes(
    origin: Optional[Tuple[float, float]],
    destination: Optional[Tuple[float, float]],
) -> Tuple[int, bool]:
    if origin is None or destination is None:
        return TOUR_FALLBACK_LEG_MINUTES, False
    distance_km = _distance_km(origin, destination)
    driving_minutes = math.ceil(
        distance_km * TOUR_ROAD_DISTANCE_FACTOR * 60 / TOUR_AVERAGE_SPEED_KMH
    )
    return max(TOUR_MINIMUM_LEG_MINUTES, driving_minutes), True


def _format_tour_instant(event_date: date, minute_of_day: int) -> str:
    instant = datetime.combine(event_date, time.min, tzinfo=gestionale.ROME)
    return (instant + timedelta(minutes=minute_of_day)).isoformat(timespec="minutes")


def _format_tour_minute(minute_of_day: int) -> str:
    day_offset, minute = divmod(minute_of_day, 24 * 60)
    label = f"{minute // 60:02d}:{minute % 60:02d}"
    return f"+{day_offset} giorno {label}" if day_offset else label


def _estimate_vehicle_tour_schedule(
    orders: Sequence[Dict[str, Any]],
    origin: str,
    site: Dict[str, Any],
    event_date: date,
    shift_start: time,
    shift_end: time,
    available_from_minute: int,
    return_to_origin: bool,
) -> Dict[str, Any]:
    shift_start_minute = shift_start.hour * 60 + shift_start.minute
    shift_end_minute = shift_end.hour * 60 + shift_end.minute
    coordinates = _delivery_location_coordinates(site)
    origin_point = _matching_location_coordinate(origin, coordinates)
    route_orders = _group_route_orders_by_city(list(orders), origin, site, return_to_origin)
    departure_minute = max(shift_start_minute, available_from_minute)
    estimated_legs = 0
    missing_coordinate_legs = 0

    first_destination = (
        _matching_location_coordinate(str(route_orders[0].get("delivery_city") or ""), coordinates)
        if route_orders
        else None
    )
    first_leg, has_first_coordinates = _estimated_leg_minutes(origin_point, first_destination)
    if route_orders and not has_first_coordinates:
        missing_coordinate_legs += 1
    else:
        estimated_legs += 1
    if route_orders:
        first_window = _delivery_window_minutes(
            route_orders[0], shift_start_minute, shift_end_minute
        )
        if first_window is not None:
            departure_minute = max(
                departure_minute,
                first_window[0] - first_leg,
            )

    current_minute = departure_minute
    previous_point = origin_point
    scheduled_orders = []
    order_time_warnings = []
    schedule_warnings = []
    longest_wait_minutes = 0

    for order in route_orders:
        destination_point = _matching_location_coordinate(
            str(order.get("delivery_city") or ""),
            coordinates,
        )
        leg_minutes, has_coordinates = _estimated_leg_minutes(previous_point, destination_point)
        if has_coordinates:
            estimated_legs += 1
        else:
            missing_coordinate_legs += 1
        arrival_minute = current_minute + leg_minutes
        window = _delivery_window_minutes(order, shift_start_minute, shift_end_minute)
        if window is not None:
            window_start, window_end = window
            if arrival_minute < window_start:
                longest_wait_minutes = max(longest_wait_minutes, window_start - arrival_minute)
                arrival_minute = window_start
            if arrival_minute > window_end:
                warning = (
                    f"#{order['order_id']}: arrivo stimato {_format_tour_minute(arrival_minute)} "
                    f"oltre la finestra richiesta {_format_tour_minute(window_start)}–"
                    f"{_format_tour_minute(window_end)}."
                )
                order_time_warnings.append(warning)
                schedule_warnings.append(warning)

        existing_warning = _route_schedule_warning(order, shift_start, shift_end)
        if existing_warning:
            schedule_warnings.append(existing_warning)
        if arrival_minute > shift_end_minute:
            schedule_warnings.append(
                f"#{order['order_id']}: arrivo stimato {_format_tour_minute(arrival_minute)} "
                f"oltre la fine del turno ({_format_tour_minute(shift_end_minute)})."
            )

        scheduled_order = dict(order)
        scheduled_order["estimated_arrival_at"] = _format_tour_instant(event_date, arrival_minute)
        scheduled_orders.append(scheduled_order)
        current_minute = arrival_minute + TOUR_STOP_SERVICE_MINUTES
        previous_point = destination_point

    last_delivery_completed_minute = current_minute
    if return_to_origin and route_orders:
        return_minutes, has_return_coordinates = _estimated_leg_minutes(previous_point, origin_point)
        if has_return_coordinates:
            estimated_legs += 1
        else:
            missing_coordinate_legs += 1
        current_minute += return_minutes

    if route_orders and last_delivery_completed_minute > shift_end_minute:
        schedule_warnings.append(
            f"Ultima consegna terminata {_format_tour_minute(last_delivery_completed_minute)} "
            f"oltre la fine del turno ({_format_tour_minute(shift_end_minute)})."
        )
    if return_to_origin and current_minute > shift_end_minute:
        schedule_warnings.append(
            f"Rientro stimato al deposito {_format_tour_minute(current_minute)} oltre la fine del turno "
            f"({_format_tour_minute(shift_end_minute)})."
        )
    if departure_minute > shift_end_minute:
        schedule_warnings.append(
            f"Partenza stimata {_format_tour_minute(departure_minute)} oltre la fine del turno "
            f"({_format_tour_minute(shift_end_minute)})."
        )

    estimate_note = (
        "Stima indicativa: coordinate dei comuni, distanza stradale stimata al fattore "
        f"{TOUR_ROAD_DISTANCE_FACTOR:g} e velocità media {TOUR_AVERAGE_SPEED_KMH} km/h; "
        f"{TOUR_STOP_SERVICE_MINUTES} min per consegna e {TOUR_RELOAD_MINUTES} min per ricaricare. "
        "Verifica traffico e tempi reali in Google Maps."
    )
    if missing_coordinate_legs:
        estimate_note += (
            f" {missing_coordinate_legs} tratte senza coordinate usano il valore prudenziale "
            f"di {TOUR_FALLBACK_LEG_MINUTES} min ciascuna."
        )

    return {
        "orders": scheduled_orders,
        "departure_minute": departure_minute,
        "last_delivery_completed_minute": last_delivery_completed_minute,
        "finish_minute": current_minute,
        "return_to_origin": return_to_origin,
        "order_time_warnings": order_time_warnings,
        "schedule_warnings": list(dict.fromkeys(schedule_warnings)),
        "longest_wait_minutes": longest_wait_minutes,
        "estimate_note": estimate_note,
        "estimated_legs": estimated_legs,
        "missing_coordinate_legs": missing_coordinate_legs,
    }


def _attach_tour_schedule(
    vehicle: Dict[str, Any],
    schedule: Dict[str, Any],
    event_date: date,
) -> None:
    vehicle["orders"] = schedule["orders"]
    vehicle["departure_at"] = _format_tour_instant(event_date, schedule["departure_minute"])
    vehicle["last_arrival_at"] = (
        schedule["orders"][-1]["estimated_arrival_at"] if schedule["orders"] else None
    )
    vehicle["last_delivery_completed_at"] = _format_tour_instant(
        event_date,
        schedule["last_delivery_completed_minute"],
    )
    vehicle["estimated_finish_at"] = _format_tour_instant(event_date, schedule["finish_minute"])
    vehicle["estimated_return_at"] = (
        vehicle["estimated_finish_at"] if schedule["return_to_origin"] else None
    )
    vehicle["duration_minutes"] = schedule["finish_minute"] - schedule["departure_minute"]
    vehicle["return_to_origin"] = schedule["return_to_origin"]
    vehicle["schedule_warnings"] = list(schedule["schedule_warnings"])
    vehicle["estimate_note"] = schedule["estimate_note"]


def _vehicle_tour_sequence_warning(
    previous_finish_minute: int,
    next_departure_minute: int,
    previous_tour_number: int,
    next_tour_number: int,
) -> Optional[str]:
    if next_departure_minute < previous_finish_minute:
        return (
            f"Sovrapposizione tra giri: il giro {next_tour_number} parte alle "
            f"{_format_tour_minute(next_departure_minute)} prima del rientro del giro "
            f"{previous_tour_number}, previsto alle {_format_tour_minute(previous_finish_minute)}."
        )

    reload_complete_minute = previous_finish_minute + TOUR_RELOAD_MINUTES
    if next_departure_minute < reload_complete_minute:
        return (
            f"Il giro {next_tour_number} parte alle {_format_tour_minute(next_departure_minute)} "
            f"prima del termine della ricarica del giro {previous_tour_number}, prevista alle "
            f"{_format_tour_minute(reload_complete_minute)}."
        )
    return None


def _plan_single_vehicle_tours(
    orders: Sequence[Dict[str, Any]],
    vehicle: Dict[str, Any],
    product_volumes: Dict[str, float],
    origin: str,
    site: Dict[str, Any],
    event_date: date,
    shift_start: time,
    shift_end: time,
    return_to_origin: bool,
) -> Dict[str, Any]:
    capacity_liters = float(vehicle["capacity_liters"])
    shift_start_minute = shift_start.hour * 60 + shift_start.minute
    shift_end_minute = shift_end.hour * 60 + shift_end.minute
    prepared_orders = []
    unassigned_orders = []
    summary = _allocate_vehicle_loads(orders, [vehicle], product_volumes)

    for order in orders:
        single_order = _allocate_vehicle_loads([order], [vehicle], product_volumes)
        if single_order["unassigned_orders"]:
            unassigned_orders.extend(single_order["unassigned_orders"])
        elif single_order["vehicles"][0]["orders"]:
            prepared_orders.append(single_order["vehicles"][0]["orders"][0])

    prepared_orders.sort(key=_tour_order_sort_key)

    tour_specs = []
    current_orders = []
    current_volume = 0.0
    available_from_minute = shift_start_minute

    def close_tour(tour_orders: List[Dict[str, Any]], tour_return_to_origin: bool) -> None:
        nonlocal available_from_minute
        route = _group_route_orders_by_city(
            tour_orders,
            origin,
            site,
            tour_return_to_origin,
        )
        schedule = _estimate_vehicle_tour_schedule(
            route,
            origin,
            site,
            event_date,
            shift_start,
            shift_end,
            available_from_minute,
            tour_return_to_origin,
        )
        tour_specs.append((tour_orders, schedule))
        available_from_minute = schedule["finish_minute"] + TOUR_RELOAD_MINUTES

    for order in prepared_orders:
        order_volume = float(order["load_volume_liters"])
        if current_orders and current_volume + order_volume > capacity_liters + 1e-9:
            close_tour(current_orders, True)
            current_orders = []
            current_volume = 0.0

        if current_orders:
            current_route = _group_route_orders_by_city(current_orders, origin, site, True)
            current_schedule = _estimate_vehicle_tour_schedule(
                current_route,
                origin,
                site,
                event_date,
                shift_start,
                shift_end,
                available_from_minute,
                True,
            )
            candidate_orders = [*current_orders, order]
            candidate_route = _group_route_orders_by_city(candidate_orders, origin, site, True)
            candidate_schedule = _estimate_vehicle_tour_schedule(
                candidate_route,
                origin,
                site,
                event_date,
                shift_start,
                shift_end,
                available_from_minute,
                True,
            )
            new_order_warnings = set(candidate_schedule["order_time_warnings"]) - set(
                current_schedule["order_time_warnings"]
            )
            new_shift_conflict = (
                candidate_schedule["finish_minute"] > shift_end_minute
                and current_schedule["finish_minute"] <= shift_end_minute
            )
            new_excessive_wait = (
                candidate_schedule["longest_wait_minutes"] > TOUR_MAX_STOP_WAIT_MINUTES
            )
            if new_order_warnings or new_shift_conflict or new_excessive_wait:
                close_tour(current_orders, True)
                current_orders = []
                current_volume = 0.0

        current_orders.append(order)
        current_volume += order_volume

    if current_orders:
        close_tour(current_orders, return_to_origin)

    tours = []
    tour_count = len(tour_specs)
    for index, (tour_orders, schedule) in enumerate(tour_specs, start=1):
        allocation = _allocate_vehicle_loads(tour_orders, [vehicle], product_volumes)
        tour = allocation["vehicles"][0]
        tour["display_name"] = f"{vehicle['name']} · Giro {index}/{tour_count}"
        tour["tour_number"] = index
        tour["tour_count"] = tour_count
        _attach_tour_schedule(tour, schedule, event_date)
        if index > 1:
            previous_schedule = tour_specs[index - 2][1]
            sequence_warning = _vehicle_tour_sequence_warning(
                previous_schedule["finish_minute"],
                schedule["departure_minute"],
                index - 1,
                index,
            )
            if sequence_warning:
                tour["schedule_warnings"].append(sequence_warning)
        if index < tour_count:
            tour["reload_duration_minutes"] = TOUR_RELOAD_MINUTES
            next_available_minute = schedule["finish_minute"] + TOUR_RELOAD_MINUTES
            tour["next_available_at"] = _format_tour_instant(event_date, next_available_minute)
        else:
            next_available_minute = None

        destinations = [order["destination"] for order in tour["orders"]]
        tour["maps_urls"] = gestionale.build_maps_urls(
            origin,
            destinations,
            return_to_origin=schedule["return_to_origin"],
        )
        order_details = []
        for order in tour["orders"]:
            products = ", ".join(
                f"{item['requested']} × {item['name']}"
                for item in order["availability"]
            )
            arrival_at = order["estimated_arrival_at"]
            detail = (
                f"#{order['order_id']} - {order['customer_name']} - {order['destination']} - "
                f"Arrivo stimato: {arrival_at} - Carico: {order['load_volume_liters']:.3f} L - "
                f"Prodotti: {products}"
            )
            if order["preferred_delivery_time"]:
                detail += f" - Orario richiesto: {order['preferred_delivery_time']}"
            if order["delivery_notes"]:
                detail += f" - Note: {order['delivery_notes']}"
            order_details.append(detail)
        details = "\n\n".join(order_details + tour["maps_urls"])
        details += f"\n\n{schedule['estimate_note']}"
        if tour["schedule_warnings"]:
            details += "\n\nAvvisi sugli orari:\n" + "\n".join(tour["schedule_warnings"])

        departure_datetime = datetime.fromisoformat(tour["departure_at"])
        finish_datetime = datetime.fromisoformat(tour["estimated_finish_at"])
        tour["calendar_url"] = ""
        if departure_datetime.date() == event_date and finish_datetime.date() == event_date:
            tour["calendar_url"] = gestionale.build_calendar_url(
                f"Giro {index}/{tour_count} - {vehicle['name']}",
                event_date,
                departure_datetime.time(),
                finish_datetime.time(),
                origin,
                details,
            )
        tours.append(tour)

    return {
        "products": summary["products"],
        "tours": tours,
        "unassigned_orders": unassigned_orders,
    }


class WebRequestError(gestionale.AppError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def create_server(
    database: Path,
    site: Dict[str, Any],
    products: Dict[str, Dict[str, Any]],
    port: int,
) -> ThreadingHTTPServer:
    catalog_products = products

    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "CartawayGestionale"
        sys_version = ""

        def log_message(self, format_string: str, *args: Any) -> None:
            return

        def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            if content_type.startswith("text/html"):
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                    "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                    "img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
                )
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, "application/json; charset=utf-8", body)

        def _origin_is_local(self, require_origin: bool = False) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return not require_origin
            expected_host = f"127.0.0.1:{self.server.server_port}"
            return origin == f"http://{expected_host}" and self.headers.get("Host") == expected_host

        def _read_json(self) -> Dict[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise WebRequestError("La richiesta deve usare application/json.", 415)
            raw_length = self.headers.get("Content-Length", "")
            if not raw_length.isdecimal():
                raise WebRequestError("Lunghezza della richiesta non valida.")
            length = int(raw_length)
            if length > MAX_REQUEST_BYTES:
                raise WebRequestError("Richiesta troppo grande.", 413)
            try:
                payload = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise WebRequestError("JSON non valido.") from exc
            if not isinstance(payload, dict):
                raise WebRequestError("Il corpo deve essere un oggetto JSON.")
            return payload

        def _dashboard(self) -> Dict[str, Any]:
            connection = gestionale.open_database(database)
            try:
                stock = [
                    {
                        "product_id": row["product_id"],
                        "name": row["name"],
                        "catalog_available": bool(row["catalog_available"]),
                        "quantity": row["quantity"],
                        "stock_group": row["stock_group"],
                        "stock_units_per_package": row["stock_units_per_package"],
                        "shared_stock": bool(row["shared_stock"]),
                        "shared_quantity": row["shared_quantity"],
                        "shared_unit": row["shared_unit"],
                    }
                    for row in gestionale.list_stock(connection)
                ]
                order_rows = connection.execute(
                    """
                    SELECT order_id, customer_name, customer_email, customer_phone,
                        delivery_address, delivery_city, ordered_at, status, confirmation_status,
                        confirmed_at, delivery_date, delivery_status, delivered_at, preferred_delivery_date,
                        preferred_delivery_time, delivery_notes,
                        first_month_order, voucher_candidate, voucher_candidate_value,
                        voucher_code, voucher_value, voucher_validity_days, voucher_valid,
                        products_subtotal, recurring_discount, recurring_order, recurring_enabled,
                        recurring_frequency_days, recurring_fixed_day, next_recurring_delivery_date,
                        last_delivered_date,
                        request_details_json, availability_json, response_required, email_status
                    FROM orders
                    WHERE NOT (
                        confirmation_status = 'confirmed'
                        AND delivery_status = 'delivered'
                        AND recurring_enabled = 0
                    )
                    ORDER BY ordered_at DESC LIMIT 100
                    """
                ).fetchall()
                active_recurring_orders = connection.execute(
                    "SELECT COUNT(*) FROM orders WHERE confirmation_status = 'confirmed' AND recurring_enabled = 1"
                ).fetchone()[0]
                orders_pending_confirmation = connection.execute(
                    "SELECT COUNT(*) FROM orders WHERE confirmation_status != 'confirmed'"
                ).fetchone()[0]
                valid_voucher_rows = connection.execute(
                    """
                    SELECT vouchers.code, vouchers.order_id, vouchers.value,
                        vouchers.validity_days, vouchers.validated_at, orders.customer_name
                    FROM valid_vouchers AS vouchers
                    JOIN orders ON orders.order_id = vouchers.order_id
                    ORDER BY vouchers.validated_at DESC
                    """
                ).fetchall()
                orders: List[Dict[str, Any]] = []
                for row in order_rows:
                    order = dict(row)
                    try:
                        order["availability"], order["status"] = gestionale.current_order_availability(connection, order)
                    except (gestionale.AppError, json.JSONDecodeError, TypeError):
                        order["availability"] = []
                    try:
                        order["request_details"] = json.loads(order.pop("request_details_json"))
                    except (json.JSONDecodeError, TypeError):
                        order["request_details"] = {}
                    if not isinstance(order["request_details"], dict):
                        order["request_details"] = {}
                    order.pop("availability_json", None)
                    order["voucher_status"] = gestionale.voucher_validation_status(connection, order, site)
                    order["first_month_order"] = bool(order["voucher_status"]["first_month_order"])
                    order["voucher_valid"] = bool(order["voucher_status"]["valid"])
                    order["recurring_order"] = bool(order["recurring_order"])
                    order["response_required"] = bool(order["response_required"])
                    order["confirmation_status"] = str(order["confirmation_status"])
                    order["delivery_status"] = str(order["delivery_status"])
                    order["delivered_at"] = str(order["delivered_at"])
                    order["recurring_enabled"] = bool(order["recurring_enabled"])
                    order["recurring_frequency_days"] = int(order["recurring_frequency_days"])
                    order["recurring_fixed_day"] = bool(order["recurring_fixed_day"])
                    order["next_recurring_delivery_date"] = str(order["next_recurring_delivery_date"])
                    order["last_delivered_date"] = str(order["last_delivered_date"])
                    orders.append(order)
                return {
                    "brand": str(site.get("brand") or "Cartaway"),
                    "default_origin": str(site.get("address") or ""),
                    "stock": stock,
                    "orders": orders,
                    "valid_vouchers": [dict(row) for row in valid_voucher_rows],
                    "summary": {
                        "products": len(stock),
                        "stock_unset": sum(row["quantity"] is None for row in stock),
                        "recurring_orders": active_recurring_orders,
                        "orders_pending_confirmation": orders_pending_confirmation,
                    },
                }
            finally:
                connection.close()

        def _order_history(self) -> Dict[str, List[Dict[str, Any]]]:
            connection = gestionale.open_database(database)
            try:
                rows = connection.execute(
                    """
                    SELECT order_id, customer_name, customer_email, customer_phone,
                        delivery_address, delivery_city, ordered_at, delivery_date,
                        delivered_at, last_delivered_date, preferred_delivery_time,
                        delivery_notes, products_subtotal, recurring_discount, recurring_order,
                        confirmation_status, delivery_status, recurring_enabled,
                        request_details_json, availability_json
                    FROM orders
                    WHERE confirmation_status = 'confirmed'
                        AND delivery_status = 'delivered'
                        AND recurring_enabled = 0
                    ORDER BY COALESCE(NULLIF(last_delivered_date, ''), delivery_date) DESC,
                        delivered_at DESC, ordered_at DESC
                    """
                ).fetchall()
                orders = []
                for row in rows:
                    order = dict(row)
                    try:
                        order["request_details"] = json.loads(order.pop("request_details_json"))
                    except (json.JSONDecodeError, TypeError):
                        order["request_details"] = {}
                    if not isinstance(order["request_details"], dict):
                        order["request_details"] = {}
                    try:
                        order["items"] = json.loads(order.pop("availability_json"))
                    except (json.JSONDecodeError, TypeError):
                        order["items"] = []
                    if not isinstance(order["items"], list):
                        order["items"] = []
                    order["recurring_enabled"] = bool(order["recurring_enabled"])
                    order["recurring_order"] = bool(order["recurring_order"])
                    orders.append(order)
                return {"orders": orders}
            finally:
                connection.close()

        def do_GET(self) -> None:
            parsed_url = urlsplit(self.path)
            path = parsed_url.path
            if path == "/" or path == "/gestionale_web.html":
                try:
                    content = (ROOT / "gestionale_web.html").read_bytes()
                except OSError:
                    self._send_json(500, {"error": "Pagina del gestionale non disponibile."})
                    return
                self._send_bytes(200, "text/html; charset=utf-8", content)
                return
            if path == "/api/dashboard":
                if not self._origin_is_local():
                    self._send_json(403, {"error": "Origine non autorizzata."})
                    return
                try:
                    self._send_json(200, self._dashboard())
                except (OSError, sqlite3.Error) as exc:
                    self._send_json(500, {"error": f"Impossibile leggere il gestionale: {exc}"})
                return
            if path == "/api/load-config":
                if not self._origin_is_local():
                    self._send_json(403, {"error": "Origine non autorizzata."})
                    return
                connection = gestionale.open_database(database)
                try:
                    self._send_json(200, gestionale.get_delivery_load_config(connection))
                except (OSError, sqlite3.Error) as exc:
                    self._send_json(500, {"error": f"Impossibile leggere la configurazione carichi: {exc}"})
                finally:
                    connection.close()
                return
            if path == "/api/orders/history":
                if not self._origin_is_local():
                    self._send_json(403, {"error": "Origine non autorizzata."})
                    return
                try:
                    self._send_json(200, self._order_history())
                except (OSError, sqlite3.Error) as exc:
                    self._send_json(500, {"error": f"Impossibile leggere lo storico: {exc}"})
                return
            if path == "/api/deliveries":
                if not self._origin_is_local():
                    self._send_json(403, {"error": "Origine non autorizzata."})
                    return
                values = parse_qs(parsed_url.query).get("date", [])
                try:
                    event_date = date.fromisoformat(values[0]) if values else datetime.now(gestionale.ROME).date()
                    self._send_json(200, self._delivery_orders(event_date))
                except ValueError:
                    self._send_json(400, {"error": "La data deve essere nel formato AAAA-MM-GG."})
                except (OSError, sqlite3.Error) as exc:
                    self._send_json(500, {"error": f"Impossibile leggere le consegne: {exc}"})
                return
            self._send_json(404, {"error": "Risorsa non trovata."})

        def do_POST(self) -> None:
            if not self._origin_is_local(require_origin=True):
                self._send_json(403, {"error": "Origine non autorizzata."})
                return
            try:
                payload = self._read_json()
                path = urlsplit(self.path).path
                if path == "/api/stock":
                    result = self._update_stock(payload)
                elif path == "/api/mail/check":
                    result = self._check_mail(payload)
                elif path == "/api/orders/confirm":
                    result = self._confirm_order(payload)
                elif path == "/api/orders/deliver":
                    result = self._mark_order_delivered(payload)
                elif path == "/api/orders/recurring/disable":
                    result = self._disable_recurring_schedule(payload)
                elif path == "/api/route":
                    result = self._plan_route(payload)
                elif path == "/api/load-config":
                    result = self._save_delivery_load_config(payload)
                elif path == "/api/vehicle-routes":
                    result = self._plan_vehicle_routes(payload)
                else:
                    self._send_json(404, {"error": "Risorsa non trovata."})
                    return
                self._send_json(200, result)
            except WebRequestError as exc:
                self._send_json(exc.status, {"error": str(exc)})
            except gestionale.OrderNotReady as exc:
                self._send_json(409, {"error": str(exc)})
            except gestionale.AppError as exc:
                self._send_json(400, {"error": str(exc)})
            except TimeoutError:
                self._send_json(
                    504,
                    {
                        "error": "Timeout IMAP: verifica IMAP_HOST (server di entrata), "
                        "IMAP_PORT=993 e che IMAP sia attivo per la casella.",
                    },
                )
            except (OSError, sqlite3.Error, ValueError, imaplib.IMAP4.error) as exc:
                self._send_json(500, {"error": f"Operazione non completata: {exc}"})

        def _update_stock(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            product_id = str(payload.get("product_id", "")).strip()
            action = payload.get("action")
            quantity = payload.get("quantity")
            if not product_id:
                raise WebRequestError("Selezionare un prodotto.")
            if action not in {"set", "add"}:
                raise WebRequestError("Operazione stock non valida.")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                raise WebRequestError("La quantità deve essere un intero maggiore o uguale a zero.")
            connection = gestionale.open_database(database)
            try:
                total = gestionale.set_stock(connection, product_id, quantity, add=action == "add")
                stock_row = next(
                    (row for row in gestionale.list_stock(connection) if row["product_id"] == product_id),
                    None,
                )
            finally:
                connection.close()
            return {
                "product_id": product_id,
                "quantity": total,
                "shared_stock": bool(stock_row and stock_row["shared_stock"]),
                "shared_quantity": stock_row["shared_quantity"] if stock_row else None,
                "shared_unit": stock_row["shared_unit"] if stock_row else "",
            }

        def _check_mail(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            limit = payload.get("limit", 50)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
                raise WebRequestError("Il limite email deve essere un intero tra 1 e 200.")
            connection = gestionale.open_database(database)
            try:
                processed = gestionale.check_mail(connection, products, site, limit)
            finally:
                connection.close()
            return {"processed": processed}

        def _confirm_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            order_id = str(payload.get("order_id", "")).strip()
            voucher_backfill = payload.get("voucher_backfill", False)
            if not isinstance(voucher_backfill, bool):
                raise WebRequestError("Il flag di registrazione del Buono Tech non è valido.")
            connection = gestionale.open_database(database)
            try:
                return gestionale.confirm_order(
                    connection,
                    order_id,
                    site,
                    voucher_backfill=voucher_backfill,
                )
            finally:
                connection.close()

        def _mark_order_delivered(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            order_id = str(payload.get("order_id", "")).strip()
            delivery_date = payload.get("delivery_date", "")
            if not isinstance(delivery_date, str):
                raise WebRequestError("La data della consegna deve essere una stringa.")
            if delivery_date:
                try:
                    date.fromisoformat(delivery_date)
                except ValueError as exc:
                    raise WebRequestError("La data della consegna deve essere nel formato AAAA-MM-GG.") from exc
            connection = gestionale.open_database(database)
            try:
                return gestionale.mark_order_delivered(connection, order_id, delivery_date)
            finally:
                connection.close()

        def _disable_recurring_schedule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            order_id = str(payload.get("order_id", "")).strip()
            connection = gestionale.open_database(database)
            try:
                return gestionale.disable_recurring_schedule(connection, order_id)
            finally:
                connection.close()

        def _save_delivery_load_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            product_volumes = payload.get("product_volumes")
            vehicles = payload.get("vehicles")
            connection = gestionale.open_database(database)
            try:
                return gestionale.save_delivery_load_config(connection, product_volumes, vehicles)
            finally:
                connection.close()

        def _delivery_orders(self, event_date: date) -> Dict[str, Any]:
            connection = gestionale.open_database(database)
            try:
                today = datetime.now(gestionale.ROME).date()
                rows = connection.execute(
                    """
                    SELECT order_id, customer_name, customer_email, customer_phone,
                        delivery_address, delivery_city,
                        preferred_delivery_date, preferred_delivery_time, delivery_notes,
                        confirmed_at, delivery_date, ordered_at, availability_json,
                        products_subtotal, recurring_discount,
                        recurring_order, recurring_enabled, recurring_frequency_days,
                        next_recurring_delivery_date, request_details_json
                    FROM orders
                    WHERE confirmation_status = 'confirmed' AND delivery_status != 'delivered'
                        AND (
                            (delivery_date >= ? AND delivery_date <= ?)
                            OR (recurring_enabled = 1 AND next_recurring_delivery_date >= ?
                                AND next_recurring_delivery_date <= ?)
                        )
                    ORDER BY delivery_date, ordered_at, order_id
                    """,
                    (
                        today.isoformat(),
                        event_date.isoformat(),
                        today.isoformat(),
                        event_date.isoformat(),
                    ),
                ).fetchall()
                inventory = gestionale.get_stock_balances(connection)
                occurrences = []
                for row in rows:
                    base_order = dict(row)
                    try:
                        request_details = json.loads(base_order.pop("request_details_json"))
                    except (json.JSONDecodeError, TypeError):
                        request_details = {}
                    if not isinstance(request_details, dict):
                        request_details = {}
                    base_order["request_details"] = request_details
                    base_order["recurring_order"] = bool(base_order["recurring_order"])
                    base_order["recurring_enabled"] = bool(base_order["recurring_enabled"])
                    base_order["recurring_frequency_days"] = int(base_order["recurring_frequency_days"])
                    base_order["next_recurring_delivery_date"] = str(base_order["next_recurring_delivery_date"])
                    base_order["recurring_frequency"] = str(request_details.get("recurring_frequency") or "")
                    base_order["recurring_day"] = str(request_details.get("recurring_day") or "")
                    current_date = str(base_order["delivery_date"])
                    try:
                        current_day = date.fromisoformat(current_date)
                    except ValueError:
                        current_day = None
                    if current_day is not None and today <= current_day <= event_date:
                        occurrences.append(
                            (current_date, str(base_order["ordered_at"]), str(base_order["order_id"]), False, base_order)
                        )
                    next_date = base_order["next_recurring_delivery_date"]
                    try:
                        next_day = date.fromisoformat(next_date)
                    except ValueError:
                        next_day = None
                    if (
                        base_order["recurring_enabled"]
                        and current_day is not None
                        and next_day is not None
                        and current_day < next_day
                        and today <= next_day <= event_date
                    ):
                        occurrences.append(
                            (next_date, str(base_order["ordered_at"]), str(base_order["order_id"]), True, base_order)
                        )

                orders = []
                for occurrence_date, _, _, is_recurring_projection, base_order in sorted(occurrences):
                    order = dict(base_order)
                    previous_delivery_date = str(base_order["delivery_date"])
                    order["delivery_date"] = occurrence_date
                    order["is_recurring_projection"] = is_recurring_projection
                    order["occurrence_ready"] = not is_recurring_projection
                    order["previous_delivery_date"] = previous_delivery_date if is_recurring_projection else ""
                    try:
                        availability, _ = gestionale.current_order_availability(
                            connection,
                            order,
                            inventory,
                        )
                    except gestionale.AppError as exc:
                        availability = []
                        order["availability_issue"] = str(exc)
                    availability_status = (
                        gestionale._availability_status(availability) if availability else "da_verificare"
                    )
                    issues = []
                    for item in availability:
                        if item["state"] == "quantita_insufficiente":
                            if item["shared_stock"]:
                                issues.append(
                                    f"{item['name']}: stock condiviso, richiesti "
                                    f"{item['stock_group_requested_units']} {item['stock_unit']}, disponibili "
                                    f"{item['stock_available_units']} {item['stock_unit']}"
                                )
                            else:
                                issues.append(
                                    f"{item['name']}: richiesti {item['requested']}, disponibili {item['available']}"
                                )
                        elif item["state"] == "catalogo_non_disponibile":
                            issues.append(f"{item['name']}: non disponibile a catalogo")
                        elif item["state"] in {"da_verificare", "catalogo_mancante"}:
                            issues.append(f"{item['name']}: giacenza da verificare")
                    if order.get("availability_issue"):
                        issues.append(order["availability_issue"])
                    order["availability"] = availability
                    order["availability_status"] = availability_status
                    order["availability_issues"] = issues
                    order["deliverable"] = availability_status == "disponibile"
                    order["destination"] = ", ".join(
                        value for value in (order["delivery_address"], order["delivery_city"]) if value
                    )
                    order["address_missing"] = not bool(order["destination"])
                    order.pop("availability_json", None)
                    if order["deliverable"]:
                        for item in availability:
                            inventory[item["inventory_key"]] -= int(item["requested_stock_units"])
                    if order["delivery_date"] == event_date.isoformat():
                        orders.append(order)
                return {"date": event_date.isoformat(), "orders": orders}
            finally:
                connection.close()

        def _plan_vehicle_routes(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            origin = str(payload.get("origin", "")).strip()
            if not origin:
                raise WebRequestError("Inserire il punto di partenza.")
            try:
                event_date = date.fromisoformat(str(payload.get("date", "")))
            except ValueError as exc:
                raise WebRequestError("La data deve essere nel formato AAAA-MM-GG.") from exc

            start_time = gestionale._parse_time(str(payload.get("start", "")), "Ora inizio")
            end_time = gestionale._parse_time(str(payload.get("end", "")), "Ora fine")
            if end_time <= start_time:
                raise WebRequestError("L'orario di fine deve essere successivo all'orario di inizio.")
            delivery_data = self._delivery_orders(event_date)
            orders = delivery_data["orders"]
            route_orders = [
                order for order in orders
                if order["deliverable"] and not order["address_missing"] and order["occurrence_ready"]
            ]
            excluded_orders = []
            for order in orders:
                if order in route_orders:
                    continue
                reasons = list(order["availability_issues"])
                if order["address_missing"]:
                    reasons.append("Indirizzo mancante")
                if not order["occurrence_ready"]:
                    reasons.append(
                        f"In attesa della consegna precedente del {order['previous_delivery_date']}"
                    )
                excluded_orders.append({"order": order, "reason": "; ".join(reasons)})

            connection = gestionale.open_database(database)
            try:
                config = gestionale.get_delivery_load_config(connection)
            finally:
                connection.close()
            if not config["vehicles"]:
                raise WebRequestError("Aggiungere almeno un furgone con la sua capacità in litri.")

            if len(config["vehicles"]) == 1:
                single_vehicle_plan = _plan_single_vehicle_tours(
                    route_orders,
                    config["vehicles"][0],
                    config["product_volumes"],
                    origin,
                    site,
                    event_date,
                    start_time,
                    end_time,
                    payload.get("return_to_origin") is True,
                )
                result = {
                    "date": event_date.isoformat(),
                    "products": single_vehicle_plan["products"],
                    "vehicles": single_vehicle_plan["tours"],
                    "unassigned_orders": single_vehicle_plan["unassigned_orders"],
                    "excluded_orders": excluded_orders,
                }
                _attach_delivery_plan_metadata(result)
                _attach_vehicle_delivery_pdfs(
                    str(site.get("brand") or "Cartaway"),
                    event_date.isoformat(),
                    result["vehicles"],
                    catalog_products,
                    (site.get("recurring_order") or {}).get("discount_percent"),
                )
                return result

            allocation = _allocate_vehicle_loads(
                route_orders,
                config["vehicles"],
                config["product_volumes"],
            )
            return_to_origin = payload.get("return_to_origin") is True
            planned_vehicles = []
            for vehicle in allocation["vehicles"]:
                if vehicle["orders"]:
                    route_orders = _group_route_orders_by_city(
                        vehicle["orders"],
                        origin,
                        site,
                        return_to_origin,
                    )
                    schedule = _estimate_vehicle_tour_schedule(
                        route_orders,
                        origin,
                        site,
                        event_date,
                        start_time,
                        end_time,
                        start_time.hour * 60 + start_time.minute,
                        return_to_origin,
                    )
                    _attach_tour_schedule(vehicle, schedule, event_date)
                    vehicle["display_name"] = f"{vehicle['name']} · Giro 1/1"
                    vehicle["tour_number"] = 1
                    vehicle["tour_count"] = 1
                    vehicle_orders = vehicle["orders"]
                    destinations = [order["destination"] for order in vehicle_orders]
                    vehicle["maps_urls"] = gestionale.build_maps_urls(
                        origin,
                        destinations,
                        return_to_origin=return_to_origin,
                    )
                    order_details = []
                    for order in vehicle_orders:
                        products = ", ".join(
                            f"{item['requested']} × {item['name']}"
                            for item in order["availability"]
                        )
                        detail = (
                            f"#{order['order_id']} - {order['customer_name']} - {order['destination']} - "
                            f"Carico: {order['load_volume_liters']:.3f} L - Prodotti: {products}"
                        )
                        if order["preferred_delivery_time"]:
                            detail += f" - Orario richiesto: {order['preferred_delivery_time']}"
                        if order["delivery_notes"]:
                            detail += f" - Note: {order['delivery_notes']}"
                        order_details.append(detail)
                    details = "\n\n".join(order_details + vehicle["maps_urls"])
                    details += f"\n\n{vehicle['estimate_note']}"
                    if vehicle["schedule_warnings"]:
                        details += "\n\nAvvisi sugli orari:\n" + "\n".join(vehicle["schedule_warnings"])
                    departure_datetime = datetime.fromisoformat(vehicle["departure_at"])
                    finish_datetime = datetime.fromisoformat(vehicle["estimated_finish_at"])
                    vehicle["calendar_url"] = ""
                    if departure_datetime.date() == event_date and finish_datetime.date() == event_date:
                        vehicle["calendar_url"] = gestionale.build_calendar_url(
                            f"Giro consegne {vehicle['name']} - {event_date.isoformat()}",
                            event_date,
                            departure_datetime.time(),
                            finish_datetime.time(),
                            origin,
                            details,
                        )
                else:
                    vehicle["maps_urls"] = []
                    vehicle["schedule_warnings"] = []
                planned_vehicles.append(vehicle)

            result = {
                "date": event_date.isoformat(),
                "products": allocation["products"],
                "vehicles": planned_vehicles,
                "unassigned_orders": allocation["unassigned_orders"],
                "excluded_orders": excluded_orders,
            }
            _attach_delivery_plan_metadata(result)
            _attach_vehicle_delivery_pdfs(
                str(site.get("brand") or "Cartaway"),
                event_date.isoformat(),
                result["vehicles"],
                catalog_products,
                (site.get("recurring_order") or {}).get("discount_percent"),
            )
            return result

        def _plan_route(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            origin = str(payload.get("origin", "")).strip()
            if not origin:
                raise WebRequestError("Inserire il punto di partenza.")
            event_date_value = str(payload.get("date", ""))
            try:
                event_date = date.fromisoformat(event_date_value)
            except ValueError as exc:
                raise WebRequestError("La data deve essere nel formato AAAA-MM-GG.") from exc
            delivery_data = self._delivery_orders(event_date)
            orders = delivery_data["orders"]
            route_orders = [
                order for order in orders
                if order["deliverable"] and not order["address_missing"]
            ]
            excluded_orders = [
                {
                    "order_id": order["order_id"],
                    "availability_issues": order["availability_issues"],
                    "address_missing": order["address_missing"],
                }
                for order in orders
                if not order["deliverable"] or order["address_missing"]
            ]
            if not route_orders:
                if any(not order["deliverable"] for order in orders):
                    raise WebRequestError(
                        f"Nessun ordine con disponibilità sufficiente per il {event_date.strftime('%d/%m/%Y')}; "
                        "controlla giacenze e prodotti nella scheda Ordini.",
                        409,
                    )
                raise WebRequestError(
                    f"Nessun ordine confermato con indirizzo per il {event_date.strftime('%d/%m/%Y')}.",
                    409,
                )
            return_to_origin = payload.get("return_to_origin") is True
            route_orders = _group_route_orders_by_city(
                route_orders,
                origin,
                site,
                return_to_origin,
            )
            destinations = [order["destination"] for order in route_orders]
            start_time = gestionale._parse_time(str(payload.get("start", "")), "Ora inizio")
            end_time = gestionale._parse_time(str(payload.get("end", "")), "Ora fine")
            schedule_warnings = [
                warning
                for order in route_orders
                if (warning := _route_schedule_warning(order, start_time, end_time))
            ]
            maps_urls = gestionale.build_maps_urls(
                origin,
                destinations,
                return_to_origin=return_to_origin,
            )
            order_details = []
            for order in route_orders:
                products = ", ".join(
                    f"{item['requested']} × {item['name']}"
                    for item in order["availability"]
                )
                order_date = date.fromisoformat(order["delivery_date"]).strftime("%d/%m/%Y")
                detail = (
                    f"#{order['order_id']} - {order['customer_name']} - {order['destination']} - "
                    f"Data: {order_date} - Orario richiesto: "
                    f"{order['preferred_delivery_time'] or 'Prima disponibilità'}"
                )
                if products:
                    detail += f" - Prodotti: {products}"
                if order["delivery_notes"]:
                    detail += f" - Note: {order['delivery_notes']}"
                if order["recurring_order"]:
                    recurrence = order["recurring_frequency"] or "frequenza da concordare"
                    if order["recurring_day"]:
                        recurrence += f", giorno {order['recurring_day']}"
                    detail += f" - Richiesta ricorrente: {recurrence} (nessun rinnovo automatico)"
                order_details.append(detail)
            details = (
                "Ordini confermati; precedenza alla partenza quando gli orari lo consentono. "
                "Percorso stimato sui centri comunali, con appuntamenti in ordine temporale e "
                "deviazioni delle altre tappe ridotte.\n\n"
                + "\n".join(order_details)
            )
            if schedule_warnings:
                details += "\n\nAvvisi sugli orari:\n" + "\n".join(schedule_warnings)
            details += "\n\n" + "\n".join(maps_urls)
            calendar_url = gestionale.build_calendar_url(
                f"Giro consegne {site.get('brand') or 'Cartaway'} - {event_date.isoformat()}",
                event_date,
                start_time,
                end_time,
                origin,
                details,
            )
            return {
                "maps_urls": maps_urls,
                "calendar_url": calendar_url,
                "orders": route_orders,
                "schedule_warnings": schedule_warnings,
                "excluded_without_address": sum(order["address_missing"] for order in orders),
                "excluded_unavailable": sum(not order["deliverable"] for order in orders),
                "excluded_orders": excluded_orders,
            }

    return ThreadingHTTPServer(("127.0.0.1", port), RequestHandler)


def serve_web(
    database: Path,
    site: Dict[str, Any],
    product_list: Sequence[Dict[str, Any]],
    products: Dict[str, Dict[str, Any]],
    port: int,
) -> None:
    connection = gestionale.open_database(database)
    try:
        gestionale.sync_catalog(connection, product_list)
    finally:
        connection.close()
    server = create_server(database, site, products, port)
    print(f"Gestionale Cartaway disponibile su http://127.0.0.1:{server.server_port}/")
    print("Solo accesso locale. Premi Ctrl+C per chiudere.")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()