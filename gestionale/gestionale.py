#!/usr/bin/env python3
"""Gestione locale degli ordini Cartaway, dell'inventario e dei giri di consegna."""

from __future__ import annotations

import argparse
import hashlib
import html
import imaplib
import json
import math
import os
import re
import smtplib
import sqlite3
import ssl
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
ROME = ZoneInfo("Europe/Rome")
DEFAULT_DATABASE = Path(
    os.environ.get(
        "CARTAWAY_DB",
        str(Path.home() / ".local" / "share" / "cartaway" / "gestionale.sqlite3"),
    )
).expanduser()


class AppError(Exception):
    pass


class OrderNotReady(AppError):
    pass


@dataclass
class OrderItem:
    product_id: str
    name: str
    quantity: int


@dataclass
class ParsedOrder:
    order_id: str
    items: List[OrderItem]
    customer_name: str
    customer_email: str
    customer_phone: str
    delivery_address: str
    delivery_city: str
    recurring: bool
    voucher_candidate: str
    voucher_value: str
    products_subtotal: str
    recurring_discount: str
    order_datetime: datetime
    message_id: str
    preferred_delivery_date: str = ""
    preferred_delivery_time: str = ""
    delivery_notes: str = ""
    request_details: Dict[str, Any] = field(default_factory=dict)


class _OrderHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[Dict[str, Any]] = []
        self.all_text: List[str] = []
        self.row: Optional[Dict[str, Any]] = None
        self.cell: Optional[List[str]] = None
        self.detail_fields: Dict[str, List[str]] = {}
        self.active_detail_field: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        detail_field = dict(attrs).get("data-order-field")
        if detail_field:
            self.active_detail_field = detail_field
        if tag == "tr":
            self._finish_row()
            self.row = {"cells": [], "links": [], "text": []}
            return
        if self.row is None:
            return
        if tag in ("td", "th"):
            self.cell = []
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.row["links"].append(href)
        elif tag == "br":
            self.row["text"].append(" ")
            if self.cell is not None:
                self.cell.append(" ")

    def handle_data(self, data: str) -> None:
        self.all_text.append(data)
        if self.active_detail_field:
            self.detail_fields.setdefault(self.active_detail_field, []).append(data)
        if self.row is not None:
            self.row["text"].append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self.active_detail_field:
            self.active_detail_field = None
        if tag in ("td", "th") and self.row is not None and self.cell is not None:
            self.row["cells"].append(_clean_text(" ".join(self.cell)))
            self.cell = None
        elif tag == "tr":
            self._finish_row()

    def _finish_row(self) -> None:
        if self.row is not None:
            if self.cell is not None:
                self.row["cells"].append(_clean_text(" ".join(self.cell)))
            if self.row["cells"] or self.row["text"]:
                self.rows.append(self.row)
        self.row = None
        self.cell = None


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).replace("\xa0", " ").split())


def _header_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
    except (LookupError, UnicodeError, ValueError):
        return str(value)


def _email_address(value: str) -> str:
    address = parseaddr(value)[1].strip()
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address):
        return address
    return ""


def _field_value(rows: Sequence[Dict[str, Any]], label: str) -> str:
    wanted = label.casefold().rstrip(":")
    for row in rows:
        cells = row["cells"]
        if len(cells) >= 2 and cells[0].casefold().rstrip(":") == wanted:
            return cells[1]
    return ""


def _delivery_date_value(value: str) -> str:
    normalized = _clean_text(value)
    if normalized.casefold() in {"", "non indicata", "non indicato", "nessuna"}:
        return ""
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def _cost_value(rows: Sequence[Dict[str, Any]], label: str) -> str:
    wanted = label.casefold()
    for row in rows:
        cells = row["cells"]
        if any(cell.casefold() == wanted for cell in cells):
            return cells[-1]
    return ""


def _product_id_from_links(links: Sequence[str]) -> str:
    for link in links:
        values = parse_qs(urlsplit(link).query).get("id", [])
        if values and values[0].strip():
            return values[0].strip()
    return ""


def _find_product_id_by_name(name: str, products: Dict[str, Dict[str, Any]]) -> str:
    normalized = _clean_text(name).casefold()
    if not normalized:
        return ""
    for product_id, product in products.items():
        product_name = _clean_text(str(product.get("name", ""))).casefold()
        if product_name and (product_name == normalized or product_name in normalized):
            return product_id
    return ""


def _message_datetime(message: Message) -> datetime:
    date_header = message.get("Date")
    if date_header:
        try:
            parsed = parsedate_to_datetime(str(date_header))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=ROME)
            return parsed.astimezone(ROME)
        except (TypeError, ValueError, OverflowError):
            pass
    return datetime.now(ROME)


def _message_body(message: Message) -> str:
    parts = list(message.walk()) if message.is_multipart() else [message]
    for wanted_type in ("text/html", "text/plain"):
        for part in parts:
            if part.get_content_type() != wanted_type:
                continue
            if part.get_content_disposition() == "attachment":
                continue
            try:
                content = part.get_content()
            except (LookupError, UnicodeError, AttributeError):
                continue
            if isinstance(content, str):
                return content
    raise AppError("Il messaggio non contiene un corpo HTML o testo leggibile.")


def parse_order_email(
    message: Message,
    products: Dict[str, Dict[str, Any]],
    internal_emails: Sequence[str] = (),
) -> ParsedOrder:
    subject = _header_text(message.get("Subject"))
    body = _message_body(message)
    parser = _OrderHtmlParser()
    parser.feed(body)
    parser.close()
    body_text = _clean_text(" ".join(parser.all_text))
    order_match = re.search(
        r"(?:Riferimento|richiesta)\s*#\s*([A-Z0-9][A-Z0-9_-]{2,63})",
        f"{subject} {body_text}",
        re.IGNORECASE,
    )
    if not order_match:
        raise AppError("Riferimento ordine non trovato nel riepilogo.")

    aggregated: Dict[str, OrderItem] = {}
    product_lines: List[Dict[str, Any]] = []
    for row in parser.rows:
        row_text = _clean_text(" ".join(row["text"]))
        quantity_match = re.search(r"Quantit(?:à|a)\s*:\s*(\d+)\b", row_text, re.IGNORECASE)
        if not quantity_match:
            continue
        quantity = int(quantity_match.group(1))
        if quantity < 1:
            raise AppError("Trovata una quantità prodotto non valida.")
        cells = row["cells"]
        name_text = cells[1] if len(cells) > 1 else row_text
        name_text = re.split(r"Quantit(?:à|a)\s*:", name_text, maxsplit=1, flags=re.IGNORECASE)[0]
        name = _clean_text(name_text) or "Prodotto senza nome"
        product_id = _product_id_from_links(row["links"])
        if not product_id:
            product_id = _find_product_id_by_name(name, products)
        if not product_id:
            raise AppError(
                f"Non riesco ad associare il prodotto '{name}' al catalogo: verificare il link prodotto nel template email."
            )
        catalog_name = str(products.get(product_id, {}).get("name") or name)
        price_cell = cells[-1] if len(cells) > 2 else ""
        prices = re.findall(r"€\s*\d[\d.]*,\d{2}", price_cell)
        product_lines.append(
            {
                "product_id": product_id,
                "name": catalog_name,
                "quantity": quantity,
                "line_total": prices[-2] if len(prices) > 1 else "",
                "unit_price": prices[-1] if "/ unità" in price_cell.casefold() and prices else "",
            }
        )
        if product_id in aggregated:
            aggregated[product_id].quantity += quantity
        else:
            aggregated[product_id] = OrderItem(product_id, catalog_name, quantity)
    if not aggregated:
        raise AppError("Nessun prodotto trovato; il riepilogo deve contenere le righe HTML del template Cartaway.")

    customer_email = _email_address(_field_value(parser.rows, "Email"))
    internal = {value.casefold() for value in internal_emails if value}
    if customer_email.casefold() in internal:
        customer_email = ""
    if not customer_email:
        for header_name in ("Delivered-To", "X-Original-To", "To"):
            header_value = _header_text(message.get(header_name))
            for _, candidate in getaddresses([header_value]):
                candidate = _email_address(candidate)
                if candidate and candidate.casefold() not in internal:
                    customer_email = candidate
                    break
            if customer_email:
                break

    recurring = _field_value(parser.rows, "Attivo").casefold() in {"sì", "si", "yes", "true"}
    candidate_code = _field_value(parser.rows, "Codice")
    if candidate_code.casefold() in {"non disponibile", "nessuno", ""}:
        candidate_code = ""
    voucher_value = _field_value(parser.rows, "Valore stimato")
    products_subtotal = _cost_value(parser.rows, "Prodotti (IVA incl.)")
    recurring_discount = _cost_value(parser.rows, "Sconto ricorrente")
    customer_phone = _field_value(parser.rows, "Telefono")
    if customer_phone.casefold() in {"non fornita", "non fornito", "non indicato", ""}:
        customer_phone = ""
    full_delivery_address = _field_value(parser.rows, "Indirizzo")
    delivery_address, separator, delivery_city = full_delivery_address.rpartition(",")
    if not separator:
        delivery_address = full_delivery_address
        delivery_city = ""
    request_details = {
        "delivery_zone": _field_value(parser.rows, "Zona"),
        "estimated_delivery_time": _field_value(parser.rows, "Tempo indicativo"),
        "billing_requested": _field_value(parser.rows, "Richiesta fattura"),
        "billing_business_name": _field_value(parser.rows, "Ragione sociale"),
        "billing_vat_number": _field_value(parser.rows, "Partita IVA"),
        "billing_recipient": _field_value(parser.rows, "Codice SDI o PEC"),
        "recurring_frequency": _field_value(parser.rows, "Frequenza"),
        "recurring_day": _field_value(parser.rows, "Giorno richiesto"),
        "price_lock_months": _field_value(parser.rows, "Prezzo bloccato"),
        "cost_shipping": _cost_value(parser.rows, "Consegna"),
        "cost_tax": _cost_value(parser.rows, "IVA prodotti"),
        "cost_total": _cost_value(parser.rows, "Totale"),
        "payment_information": _clean_text(
            " ".join(parser.detail_fields.get("payment_information", []))
        ),
        "product_lines": product_lines,
    }

    return ParsedOrder(
        order_id=order_match.group(1).upper(),
        items=list(aggregated.values()),
        customer_name=_field_value(parser.rows, "Nome") or "Cliente",
        customer_email=customer_email,
        customer_phone=customer_phone,
        delivery_address=delivery_address.strip(),
        delivery_city=delivery_city.strip(),
        recurring=recurring,
        voucher_candidate=candidate_code,
        voucher_value=voucher_value,
        products_subtotal=products_subtotal,
        recurring_discount=recurring_discount,
        order_datetime=_message_datetime(message),
        message_id=_header_text(message.get("Message-ID")),
        preferred_delivery_date=_delivery_date_value(_field_value(parser.rows, "Data preferita")),
        preferred_delivery_time=_field_value(parser.rows, "Preferenza di consegna"),
        delivery_notes=_field_value(parser.rows, "Note"),
        request_details=request_details,
    )


def _parse_money(value: str) -> Optional[Decimal]:
    normalized = value.replace("−", "-").replace("–", "-")
    number = re.sub(r"[^0-9,.-]", "", normalized)
    if not number:
        return None
    if "," in number:
        number = number.replace(".", "").replace(",", ".")
    elif number.count(".") > 1:
        pieces = number.split(".")
        number = "".join(pieces[:-1]) + "." + pieces[-1]
    try:
        return Decimal(number)
    except InvalidOperation:
        return None


def _money_to_cents(value: Optional[Decimal]) -> Optional[int]:
    if value is None:
        return None
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _identity_keys(email_address: str, phone: str) -> List[str]:
    identities: List[str] = []
    normalized_email = _email_address(email_address).casefold()
    if normalized_email:
        identities.append("email:" + normalized_email)
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 7 and len(set(digits)) > 1:
        identities.append("phone:" + digits)
    return [hashlib.sha256(value.encode("utf-8")).hexdigest() for value in dict.fromkeys(identities)]


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            catalog_available INTEGER NOT NULL,
            quantity INTEGER,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS delivery_load_volumes (
            product_id TEXT PRIMARY KEY,
            volume_liters REAL NOT NULL CHECK (volume_liters > 0)
        );
        CREATE TABLE IF NOT EXISTS delivery_vehicles (
            vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            capacity_liters REAL NOT NULL CHECK (capacity_liters > 0)
        );
        CREATE TABLE IF NOT EXISTS monthly_orders (
            identity_key TEXT NOT NULL,
            period TEXT NOT NULL,
            order_id TEXT NOT NULL,
            PRIMARY KEY (identity_key, period)
        );
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            delivery_address TEXT NOT NULL,
            delivery_city TEXT NOT NULL,
            ordered_at TEXT NOT NULL,
            first_month_order INTEGER NOT NULL,
            voucher_candidate TEXT NOT NULL,
            voucher_candidate_value TEXT NOT NULL DEFAULT '',
            voucher_code TEXT NOT NULL,
            voucher_value TEXT NOT NULL,
            voucher_validity_days INTEGER,
            voucher_valid INTEGER NOT NULL,
            products_subtotal TEXT NOT NULL DEFAULT '',
            recurring_discount TEXT NOT NULL DEFAULT '',
            recurring_order INTEGER NOT NULL DEFAULT 0,
            preferred_delivery_date TEXT NOT NULL DEFAULT '',
            preferred_delivery_time TEXT NOT NULL DEFAULT '',
            delivery_notes TEXT NOT NULL DEFAULT '',
            request_details_json TEXT NOT NULL DEFAULT '{}',
            delivery_date TEXT NOT NULL DEFAULT '',
            confirmation_status TEXT NOT NULL DEFAULT 'pending',
            confirmed_at TEXT NOT NULL DEFAULT '',
            delivery_status TEXT NOT NULL DEFAULT 'pending',
            delivered_at TEXT NOT NULL DEFAULT '',
            recurring_enabled INTEGER NOT NULL DEFAULT 0,
            recurring_frequency_days INTEGER NOT NULL DEFAULT 0,
            recurring_fixed_day INTEGER NOT NULL DEFAULT 1,
            next_recurring_delivery_date TEXT NOT NULL DEFAULT '',
            last_delivered_date TEXT NOT NULL DEFAULT '',
            availability_json TEXT NOT NULL,
            status TEXT NOT NULL,
            response_required INTEGER NOT NULL,
            response_to TEXT NOT NULL,
            response_subject TEXT NOT NULL,
            response_text TEXT NOT NULL,
            response_html TEXT NOT NULL,
            response_sent INTEGER NOT NULL DEFAULT 0,
            email_status TEXT NOT NULL DEFAULT 'non_richiesta',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS valid_vouchers (
            code TEXT PRIMARY KEY,
            order_id TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            validity_days INTEGER NOT NULL,
            validated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS processed_messages (
            mailbox TEXT NOT NULL,
            uid TEXT NOT NULL,
            order_id TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            PRIMARY KEY (mailbox, uid)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS unique_active_voucher_code
            ON orders (voucher_code) WHERE voucher_code <> '';
        """
    )
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(orders)").fetchall()
    }
    migrations = (
        ("voucher_candidate_value", "TEXT NOT NULL DEFAULT ''"),
        ("products_subtotal", "TEXT NOT NULL DEFAULT ''"),
        ("recurring_discount", "TEXT NOT NULL DEFAULT ''"),
        ("recurring_order", "INTEGER NOT NULL DEFAULT 0"),
        ("preferred_delivery_date", "TEXT NOT NULL DEFAULT ''"),
        ("preferred_delivery_time", "TEXT NOT NULL DEFAULT ''"),
        ("delivery_notes", "TEXT NOT NULL DEFAULT ''"),
        ("request_details_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("delivery_date", "TEXT NOT NULL DEFAULT ''"),
        ("confirmation_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("confirmed_at", "TEXT NOT NULL DEFAULT ''"),
        ("delivery_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("delivered_at", "TEXT NOT NULL DEFAULT ''"),
        ("recurring_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ("recurring_frequency_days", "INTEGER NOT NULL DEFAULT 0"),
        ("recurring_fixed_day", "INTEGER NOT NULL DEFAULT 1"),
        ("next_recurring_delivery_date", "TEXT NOT NULL DEFAULT ''"),
        ("last_delivered_date", "TEXT NOT NULL DEFAULT ''"),
    )
    for column, definition in migrations:
        if column not in existing_columns:
            connection.execute(f"ALTER TABLE orders ADD COLUMN {column} {definition}")
    existing_columns.update(row[1] for row in connection.execute("PRAGMA table_info(orders)").fetchall())
    if {"voucher_code", "voucher_value", "voucher_validity_days", "voucher_valid", "confirmed_at", "created_at"} <= existing_columns:
        connection.execute(
            """
            INSERT OR IGNORE INTO valid_vouchers (code, order_id, value, validity_days, validated_at)
            SELECT voucher_code, order_id, voucher_value, voucher_validity_days,
                COALESCE(NULLIF(confirmed_at, ''), created_at)
            FROM orders
            WHERE voucher_valid = 1 AND voucher_code <> '' AND voucher_validity_days IS NOT NULL
            """
        )
    connection.commit()


def get_delivery_load_config(connection: sqlite3.Connection) -> Dict[str, Any]:
    volumes = connection.execute(
        "SELECT product_id, volume_liters FROM delivery_load_volumes ORDER BY product_id"
    ).fetchall()
    vehicles = connection.execute(
        "SELECT name, capacity_liters FROM delivery_vehicles ORDER BY vehicle_id"
    ).fetchall()
    return {
        "product_volumes": {str(row["product_id"]): float(row["volume_liters"]) for row in volumes},
        "vehicles": [
            {"name": str(row["name"]), "capacity_liters": float(row["capacity_liters"])}
            for row in vehicles
        ],
    }


def save_delivery_load_config(
    connection: sqlite3.Connection,
    product_volumes: Dict[str, Any],
    vehicles: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(product_volumes, dict) or not isinstance(vehicles, (list, tuple)):
        raise AppError("Configurazione di carico non valida.")

    known_product_ids = {
        str(row["product_id"])
        for row in connection.execute("SELECT product_id FROM products").fetchall()
    }
    validated_volumes = []
    for product_id, value in product_volumes.items():
        normalized_id = str(product_id).strip()
        if normalized_id not in known_product_ids:
            raise AppError(f"Prodotto non presente nel catalogo: {normalized_id or 'senza ID'}.")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AppError(f"L'ingombro di {normalized_id} deve essere un numero in litri.")
        volume = float(value)
        if not math.isfinite(volume) or volume <= 0:
            raise AppError(f"L'ingombro di {normalized_id} deve essere maggiore di zero.")
        validated_volumes.append((normalized_id, volume))

    validated_vehicles = []
    vehicle_names = set()
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            raise AppError("Ogni furgone deve avere nome e capacità in litri.")
        name = str(vehicle.get("name") or "").strip()
        capacity_value = vehicle.get("capacity_liters")
        if not name or len(name) > 80:
            raise AppError("Inserire un nome furgone (massimo 80 caratteri).")
        if name.casefold() in vehicle_names:
            raise AppError(f"Nome furgone duplicato: {name}.")
        if isinstance(capacity_value, bool) or not isinstance(capacity_value, (int, float)):
            raise AppError(f"La capacità di {name} deve essere espressa in litri.")
        capacity = float(capacity_value)
        if not math.isfinite(capacity) or capacity <= 0:
            raise AppError(f"La capacità di {name} deve essere maggiore di zero.")
        vehicle_names.add(name.casefold())
        validated_vehicles.append((name, capacity))

    with connection:
        connection.execute("DELETE FROM delivery_load_volumes")
        connection.execute("DELETE FROM delivery_vehicles")
        connection.executemany(
            "INSERT INTO delivery_load_volumes (product_id, volume_liters) VALUES (?, ?)",
            validated_volumes,
        )
        connection.executemany(
            "INSERT INTO delivery_vehicles (name, capacity_liters) VALUES (?, ?)",
            validated_vehicles,
        )
    return get_delivery_load_config(connection)


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    try:
        path.chmod(0o600)
    except OSError:
        connection.close()
        raise
    return connection


def sync_catalog(connection: sqlite3.Connection, products: Sequence[Dict[str, Any]]) -> int:
    now = datetime.now(ROME).isoformat(timespec="seconds")
    for product in products:
        product_id = str(product.get("id", "")).strip()
        name = str(product.get("name", "")).strip()
        if not product_id or not name:
            continue
        catalog_available = 0 if product.get("available", True) is False else 1
        connection.execute(
            """
            INSERT INTO products (product_id, name, catalog_available, quantity, updated_at)
            VALUES (?, ?, ?, NULL, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                name = excluded.name,
                catalog_available = excluded.catalog_available,
                updated_at = excluded.updated_at
            """,
            (product_id, name, catalog_available, now),
        )
    connection.commit()
    return len(products)


def set_stock(connection: sqlite3.Connection, product_id: str, quantity: int, add: bool = False) -> int:
    if quantity < 0:
        raise AppError("La giacenza non può essere negativa.")
    row = connection.execute("SELECT quantity FROM products WHERE product_id = ?", (product_id,)).fetchone()
    if row is None:
        raise AppError(f"Prodotto '{product_id}' non presente in data/products.json.")
    if add:
        if row["quantity"] is None:
            raise AppError("La giacenza non è impostata: usare prima il comando stock set.")
        quantity += int(row["quantity"])
    connection.execute(
        "UPDATE products SET quantity = ?, updated_at = ? WHERE product_id = ?",
        (quantity, datetime.now(ROME).isoformat(timespec="seconds"), product_id),
    )
    connection.commit()
    return quantity


def list_stock(connection: sqlite3.Connection) -> List[sqlite3.Row]:
    return connection.execute(
        "SELECT product_id, name, catalog_available, quantity FROM products ORDER BY name COLLATE NOCASE"
    ).fetchall()


def _availability(connection: sqlite3.Connection, items: Sequence[OrderItem]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for item in items:
        product = connection.execute(
            "SELECT name, catalog_available, quantity FROM products WHERE product_id = ?",
            (item.product_id,),
        ).fetchone()
        if product is None:
            state = "catalogo_mancante"
            available: Optional[int] = 0
            name = item.name
        elif not product["catalog_available"]:
            state = "catalogo_non_disponibile"
            available = 0
            name = product["name"]
        elif product["quantity"] is None:
            state = "da_verificare"
            available = None
            name = product["name"]
        else:
            available = int(product["quantity"])
            state = "disponibile" if available >= item.quantity else "quantita_insufficiente"
            name = product["name"]
        results.append(
            {
                "product_id": item.product_id,
                "name": name,
                "requested": item.quantity,
                "available": available,
                "state": state,
            }
        )
    return results


def _availability_status(stock: Sequence[Dict[str, Any]]) -> str:
    if any(item["state"] in {"da_verificare", "catalogo_mancante"} for item in stock):
        return "da_verificare"
    if any(item["state"] != "disponibile" for item in stock):
        return "disponibilita_insufficiente"
    return "disponibile"


def current_order_availability(
    connection: sqlite3.Connection,
    order_row: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], str]:
    try:
        stored_items = json.loads(order_row["availability_json"])
        items = [
            OrderItem(
                product_id=str(item["product_id"]),
                name=str(item["name"]),
                quantity=int(item["requested"]),
            )
            for item in stored_items
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError("Dati dei prodotti dell'ordine non leggibili.") from exc
    if not items:
        raise AppError("L'ordine non contiene prodotti verificabili.")
    stock = _availability(connection, items)
    return stock, _availability_status(stock)


def _voucher_days(site: Dict[str, Any], recurring: bool) -> Optional[int]:
    if recurring:
        value = site.get("recurring_order", {}).get("tech_voucher_validity_days")
    else:
        value = site.get("tech_voucher", {}).get("validity_days")
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None


    def _money_to_cents(value: Optional[Decimal]) -> Optional[int]:
        if value is None:
            return None
        return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return days if days > 0 else None


def _validate_voucher(
    connection: sqlite3.Connection,
    order_id: str,
    customer_email: str,
    customer_phone: str,
    order_datetime: datetime,
    recurring: bool,
    voucher_candidate: str,
    voucher_candidate_value: str,
    products_subtotal: str,
    recurring_discount: str,
    site: Dict[str, Any],
) -> Tuple[bool, bool, Optional[int]]:
    identities = _identity_keys(customer_email, customer_phone)
    if order_datetime.tzinfo is None:
        order_datetime = order_datetime.replace(tzinfo=ROME)
    period = order_datetime.astimezone(ROME).strftime("%Y-%m")
    prior_order = False
    if identities:
        placeholders = ",".join("?" for _ in identities)
        prior_order = connection.execute(
            f"SELECT 1 FROM monthly_orders WHERE period = ? AND order_id != ? "
            f"AND identity_key IN ({placeholders}) LIMIT 1",
            [period, order_id, *identities],
        ).fetchone() is not None
    first_month_order = bool(identities) and not prior_order

    candidate_amount = _parse_money(voucher_candidate_value)
    candidate_code_valid = bool(re.fullmatch(r"BT-[A-Z0-9-]{4,80}", voucher_candidate))
    maximum_cents = _money_to_cents(_parse_money(str(site.get("tech_voucher", {}).get("maximum_amount", ""))))
    subtotal_cents = _money_to_cents(_parse_money(products_subtotal))
    if recurring_discount.casefold() == "nessuno":
        discount_cents: Optional[int] = 0
    else:
        parsed_discount = _money_to_cents(_parse_money(recurring_discount))
        discount_cents = abs(parsed_discount) if parsed_discount is not None else None
    recurring_settings = site.get("recurring_order", {})
    percent_value = (
        recurring_settings.get("tech_voucher_percent")
        if recurring
        else site.get("tech_voucher", {}).get("percent")
    )
    try:
        percent = Decimal(str(percent_value))
    except (InvalidOperation, TypeError, ValueError):
        percent = Decimal("-1")
    net_subtotal_cents = (
        subtotal_cents - discount_cents
        if subtotal_cents is not None and discount_cents is not None
        else None
    )
    expected_voucher_cents: Optional[int] = None
    if (
        net_subtotal_cents is not None
        and net_subtotal_cents > 0
        and maximum_cents is not None
        and maximum_cents > 0
        and Decimal("0") < percent <= Decimal("100")
    ):
        calculated_cents = int(
            (Decimal(net_subtotal_cents) * percent / Decimal("100")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        expected_voucher_cents = min(calculated_cents, maximum_cents)
    candidate_cents = _money_to_cents(candidate_amount)
    code_already_used = bool(
        voucher_candidate
        and connection.execute(
            "SELECT 1 FROM valid_vouchers WHERE code = ? AND order_id != ? LIMIT 1",
            (voucher_candidate, order_id),
        ).fetchone()
    )
    validity_days = _voucher_days(site, recurring)
    voucher_valid = bool(
        first_month_order
        and candidate_code_valid
        and not code_already_used
        and candidate_amount is not None
        and candidate_amount > 0
        and maximum_cents is not None
        and candidate_cents == expected_voucher_cents
        and validity_days is not None
    )
    return first_month_order, voucher_valid, validity_days


def voucher_validation_status(
    connection: sqlite3.Connection,
    order_row: Dict[str, Any],
    site: Dict[str, Any],
) -> Dict[str, Any]:
    candidate = str(order_row.get("voucher_candidate") or "")
    if not candidate:
        return {"valid": False, "label": "Non presente", "reason": "", "first_month_order": False}

    first_month_order, is_valid, validity_days = _validate_voucher(
        connection,
        str(order_row["order_id"]),
        str(order_row["customer_email"]),
        str(order_row["customer_phone"]),
        datetime.fromisoformat(str(order_row["ordered_at"])),
        bool(order_row["recurring_order"]),
        candidate,
        str(order_row["voucher_candidate_value"] or ""),
        str(order_row["products_subtotal"] or ""),
        str(order_row["recurring_discount"] or ""),
        site,
    )
    if is_valid:
        return {
            "valid": True,
            "label": "Convalidato",
            "reason": "",
            "first_month_order": True,
            "validity_days": validity_days,
        }
    if not first_month_order:
        reason = "Risulta già un altro ordine dello stesso cliente nel mese."
    elif not re.fullmatch(r"BT-[A-Z0-9-]{4,80}", candidate):
        reason = "Il formato del codice non è valido."
    elif not str(order_row.get("voucher_candidate_value") or "").strip() or not str(
        order_row.get("products_subtotal") or ""
    ).strip():
        reason = "Importo del buono o subtotale prodotti non acquisiti dal riepilogo."
    elif str(order_row.get("recurring_discount") or "").strip() == "":
        reason = "Sconto ricorrente non acquisito dal riepilogo."
    elif validity_days is None:
        reason = "Validità del Buono Tech non configurata."
    elif connection.execute(
        "SELECT 1 FROM valid_vouchers WHERE code = ? AND order_id != ? LIMIT 1",
        (candidate, str(order_row["order_id"])),
    ).fetchone():
        reason = "Questo codice è già presente nella lista dei buoni validi."
    else:
        reason = "Il valore non corrisponde alla percentuale e al massimale configurati."
    return {
        "valid": False,
        "label": "Da verificare" if "non acquisiti" in reason or "non acquisito" in reason else "Non convalidato",
        "reason": reason,
        "first_month_order": first_month_order,
    }


def _format_reply(
    order: ParsedOrder,
    stock: Sequence[Dict[str, Any]],
    first_month_order: bool,
    voucher_valid: bool,
    validity_days: Optional[int],
    brand: str,
) -> Tuple[str, str]:
    lines = [f"Ciao {order.customer_name},", "", f"abbiamo verificato la richiesta #{order.order_id}."]
    markup = [f"<p>Ciao {html.escape(order.customer_name)},</p>", f"<p>Abbiamo verificato la richiesta <strong>#{html.escape(order.order_id)}</strong>.</p>"]
    if voucher_valid:
        lines.append(
            f"Buono Tech convalidato: codice {order.voucher_candidate}, valore {order.voucher_value}. "
            f"Validità: {validity_days} giorni dalla consegna."
        )
        markup.append(
            "<p><strong>Buono Tech convalidato</strong><br>"
            f"Codice: {html.escape(order.voucher_candidate)}<br>"
            f"Valore: {html.escape(order.voucher_value)}<br>"
            f"Validità: {validity_days} giorni dalla consegna.</p>"
        )
    elif order.voucher_candidate:
        if not first_month_order:
            reason = "risulta già associato un primo ordine del mese a questo contatto"
        elif not order.customer_email and not order.customer_phone:
            reason = "mancano un indirizzo email e un numero di telefono verificabili"
        else:
            reason = "il codice o il valore non corrisponde ai criteri configurati"
        lines.append(f"Buono Tech non convalidato: {reason}.")
        markup.append(f"<p>Buono Tech non convalidato: {html.escape(reason)}.</p>")

    unavailable = [
        item for item in stock
        if item["state"] in {"catalogo_non_disponibile", "quantita_insufficiente"}
    ]
    unknown = [
        item for item in stock
        if item["state"] in {"da_verificare", "catalogo_mancante"}
    ]
    if unavailable:
        lines.extend(["", "Disponibilità dei prodotti:"])
        markup.append("<p>Disponibilità dei prodotti:</p><ul>")
        for item in unavailable:
            name = str(item["name"])
            if item["state"] == "catalogo_non_disponibile":
                detail = "segnalato come non disponibile nel catalogo"
            else:
                count = int(item["available"] or 0)
                detail = f"richiesti {item['requested']}, disponibili {count} secondo la giacenza registrata"
            lines.append(f"- {name}: {detail}.")
            markup.append(f"<li><strong>{html.escape(name)}</strong>: {html.escape(detail)}.</li>")
        markup.append("</ul>")
    if unknown:
        names = ", ".join(str(item["name"]) for item in unknown)
        lines.extend(["", f"Disponibilità da verificare prima della conferma: {names}."])
        markup.append(
            "<p>Disponibilità da verificare prima della conferma: "
            + html.escape(names)
            + ".</p>"
        )
    if not unavailable and not unknown:
        lines.extend(["", "Le giacenze registrate risultano sufficienti per tutti i prodotti richiesti."])
        markup.append("<p>Le giacenze registrate risultano sufficienti per tutti i prodotti richiesti.</p>")

    lines.extend(
        [
            "",
            "Questa email non è una conferma d'ordine. Disponibilità, consegna e pagamento saranno confermati dall'attività.",
            "Le giacenze sono consultive e non vengono scalate da una richiesta.",
            "",
            brand,
        ]
    )
    markup.append(
        "<p>Questa email non è una conferma d'ordine. Disponibilità, consegna e pagamento saranno confermati "
        "dall'attività. Le giacenze sono consultive e non vengono scalate da una richiesta.</p>"
        f"<p>{html.escape(brand)}</p>"
    )
    return "\n".join(lines), "<!doctype html><html lang=\"it\"><body>" + "".join(markup) + "</body></html>"


def prepare_order(connection: sqlite3.Connection, order: ParsedOrder, site: Dict[str, Any]) -> Dict[str, Any]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing = connection.execute("SELECT * FROM orders WHERE order_id = ?", (order.order_id,)).fetchone()
        if existing:
            connection.commit()
            return dict(existing)

        stock = _availability(connection, order.items)
        identities = _identity_keys(order.customer_email, order.customer_phone)
        period = order.order_datetime.astimezone(ROME).strftime("%Y-%m")
        for identity in identities:
            connection.execute(
                "INSERT OR IGNORE INTO monthly_orders (identity_key, period, order_id) VALUES (?, ?, ?)",
                (identity, period, order.order_id),
            )
        first_month_order, voucher_valid, validity_days = _validate_voucher(
            connection,
            order.order_id,
            order.customer_email,
            order.customer_phone,
            order.order_datetime,
            order.recurring,
            order.voucher_candidate,
            order.voucher_value,
            order.products_subtotal,
            order.recurring_discount,
            site,
        )
        problems = [item for item in stock if item["state"] != "disponibile"]
        response_required = voucher_valid or any(
            item["state"] in {"catalogo_non_disponibile", "quantita_insufficiente"}
            for item in stock
        )
        status = _availability_status(stock)
        brand = str(site.get("brand") or "Cartaway")
        response_text, response_html = _format_reply(
            order, stock, first_month_order, voucher_valid, validity_days, brand
        )
        response_to = _email_address(order.customer_email)
        response_subject = f"Aggiornamento richiesta #{order.order_id} - {brand}"
        email_status = "da_inviare" if response_required and response_to else (
            "email_mancante" if response_required else "non_richiesta"
        )
        now = datetime.now(ROME).isoformat(timespec="seconds")
        connection.execute(
            """
            INSERT INTO orders (
                order_id, message_id, customer_name, customer_email, customer_phone,
                delivery_address, delivery_city, ordered_at, first_month_order,
                voucher_candidate, voucher_candidate_value, voucher_code, voucher_value,
                voucher_validity_days, voucher_valid, products_subtotal, recurring_discount,
                recurring_order, preferred_delivery_date, preferred_delivery_time, delivery_notes,
                request_details_json, availability_json, status, response_required, response_to, response_subject,
                response_text, response_html, response_sent, email_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                order.order_id,
                order.message_id,
                order.customer_name,
                order.customer_email,
                order.customer_phone,
                order.delivery_address,
                order.delivery_city,
                order.order_datetime.isoformat(timespec="seconds"),
                int(first_month_order),
                order.voucher_candidate,
                order.voucher_value,
                order.voucher_candidate if voucher_valid else "",
                order.voucher_value if voucher_valid else "",
                validity_days if voucher_valid else None,
                int(voucher_valid),
                order.products_subtotal,
                order.recurring_discount,
                int(order.recurring),
                order.preferred_delivery_date,
                order.preferred_delivery_time,
                order.delivery_notes,
                json.dumps(order.request_details, ensure_ascii=False),
                json.dumps(stock, ensure_ascii=False),
                status,
                int(response_required),
                response_to,
                response_subject,
                response_text,
                response_html,
                email_status,
                now,
            ),
        )
        if voucher_valid and validity_days is not None:
            connection.execute(
                """
                INSERT OR IGNORE INTO valid_vouchers (code, order_id, value, validity_days, validated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order.voucher_candidate, order.order_id, order.voucher_value, validity_days, now),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    row = connection.execute("SELECT * FROM orders WHERE order_id = ?", (order.order_id,)).fetchone()
    return dict(row)


def _make_customer_email(order_row: Dict[str, Any], site: Dict[str, Any], sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = order_row["response_to"]
    message["Subject"] = order_row["response_subject"]
    reply_to = _email_address(str(site.get("email", "")))
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(order_row["response_text"])
    message.add_alternative(order_row["response_html"], subtype="html")
    return message


def _format_order_confirmation(
    order_row: Dict[str, Any],
    site: Dict[str, Any],
    voucher_valid: bool,
    validity_days: Optional[int],
    delivery_date: str,
) -> Tuple[str, str]:
    brand = str(site.get("brand") or "Cartaway")
    customer_name = str(order_row["customer_name"] or "Cliente")
    order_id = str(order_row["order_id"])
    delivery_label = delivery_date
    try:
        delivery_label = date.fromisoformat(delivery_date).strftime("%d/%m/%Y")
    except ValueError:
        pass
    address = ", ".join(
        value for value in (str(order_row["delivery_address"]), str(order_row["delivery_city"])) if value
    ) or "Da concordare"
    preferred_time = str(order_row["preferred_delivery_time"] or "Prima disponibilità")
    lines = [
        f"Ciao {customer_name},",
        "",
        f"abbiamo verificato la disponibilità e confermato l'ordine #{order_id}.",
        f"Consegna programmata per il {delivery_label} presso {address}.",
        f"Preferenza indicata: {preferred_time}.",
    ]
    markup = [
        f"<p>Ciao {html.escape(customer_name)},</p>",
        f"<p>Abbiamo verificato la disponibilità e confermato l'ordine <strong>#{html.escape(order_id)}</strong>.</p>",
        f"<p>Consegna programmata per il {html.escape(delivery_label)} presso {html.escape(address)}.<br>"
        f"Preferenza indicata: {html.escape(preferred_time)}.</p>",
    ]
    try:
        products = json.loads(order_row["availability_json"])
    except (json.JSONDecodeError, TypeError):
        products = []
    if products:
        lines.extend(["", "Prodotti confermati:"])
        markup.append("<p>Prodotti confermati:</p><ul>")
        for product in products:
            product_line = f"{product['requested']} × {product['name']}"
            lines.append(f"- {product_line}")
            markup.append(f"<li>{html.escape(product_line)}</li>")
        markup.append("</ul>")
    if order_row["delivery_notes"]:
        notes = str(order_row["delivery_notes"])
        lines.extend([f"Note di consegna: {notes}."])
        markup.append(f"<p>Note di consegna: {html.escape(notes)}.</p>")
    if order_row.get("next_recurring_delivery_date"):
        next_date = date.fromisoformat(str(order_row["next_recurring_delivery_date"]))
        next_label = next_date.strftime("%d/%m/%Y")
        frequency = str(order_row.get("recurring_frequency_label") or "la frequenza concordata")
        lines.append(
            f"programmazione ricorrente attiva: prossima consegna il {next_label} ({frequency}). "
            "Nessun pagamento automatico. Per sospenderla, contatta l'attività."
        )
        markup.append(
            "<p><strong>Programmazione ricorrente attiva</strong>: prossima consegna il "
            f"{html.escape(next_label)} ({html.escape(frequency)}). Nessun pagamento automatico. "
            "Per sospenderla, contatta l'attività.</p>"
        )
    if voucher_valid:
        code = str(order_row["voucher_candidate"])
        value = str(order_row["voucher_candidate_value"])
        lines.append(
            f"Il tuo Buono Tech è stato attivato. Codice: {code}. "
            f"Valore: {value}. Validità: {validity_days} giorni dalla consegna."
        )
        markup.append(
            "<p><strong>Il tuo Buono Tech è stato attivato</strong><br>"
            f"Codice: {html.escape(code)}<br>Valore: {html.escape(value)}<br>"
            f"Validità: {validity_days} giorni dalla consegna.</p>"
        )
    elif order_row["voucher_candidate"]:
        lines.append("Buono Tech non convalidato; l'ordine è confermato senza applicare il buono.")
        markup.append("<p>Buono Tech non convalidato; l'ordine è confermato senza applicare il buono.</p>")
    lines.extend(["", brand])
    markup.append(f"<p>{html.escape(brand)}</p>")
    return "\n".join(lines), "<!doctype html><html lang=\"it\"><body>" + "".join(markup) + "</body></html>"


def _configured_recurring_frequency(order_row: Dict[str, Any], site: Dict[str, Any]) -> Optional[int]:
    if not bool(order_row.get("recurring_order")):
        return None
    try:
        request_details = json.loads(order_row.get("request_details_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(request_details, dict):
        return None
    requested_label = str(request_details.get("recurring_frequency") or "").strip().casefold()
    if not requested_label:
        return None
    recurring_settings = site.get("recurring_order", {})
    options = recurring_settings.get("frequency_days", []) if isinstance(recurring_settings, dict) else []
    legacy_labels = recurring_settings.get("frequency_labels", {}) if isinstance(recurring_settings, dict) else {}
    if not isinstance(legacy_labels, dict):
        legacy_labels = {}
    for option in options if isinstance(options, list) else []:
        if isinstance(option, dict):
            days = option.get("days")
            configured_label = option.get("label")
        else:
            days = option
            configured_label = None
        if isinstance(days, bool):
            continue
        try:
            frequency_days = int(days)
        except (TypeError, ValueError):
            continue
        if frequency_days < 1:
            continue
        label = str(
            configured_label
            or legacy_labels.get(f"day_{frequency_days}")
            or f"Ogni {frequency_days} giorni"
        ).strip().casefold()
        if label == requested_label:
            return frequency_days
    return None


def _recurring_weekday(recurring_day: str) -> Optional[int]:
    weekdays = {
        "lunedì": 0, "lunedi": 0, "monday": 0,
        "martedì": 1, "martedi": 1, "tuesday": 1,
        "mercoledì": 2, "mercoledi": 2, "wednesday": 2,
        "giovedì": 3, "giovedi": 3, "thursday": 3,
        "venerdì": 4, "venerdi": 4, "friday": 4,
        "sabato": 5, "saturday": 5,
        "domenica": 6, "sunday": 6,
    }
    return weekdays.get(recurring_day.strip().casefold())


def _recurring_month_day(recurring_day: str) -> Optional[int]:
    try:
        day_of_month = int(recurring_day.strip())
    except ValueError:
        return None
    return day_of_month if 1 <= day_of_month <= 28 else None


def _first_recurring_date(
    delivery_date: date,
    frequency_days: int,
    recurring_day: str,
    fixed_delivery_day: bool,
) -> Optional[date]:
    if not fixed_delivery_day:
        return delivery_date
    if frequency_days in {7, 14}:
        target_weekday = _recurring_weekday(recurring_day)
        if target_weekday is None:
            return None
        return delivery_date + timedelta(days=(target_weekday - delivery_date.weekday()) % 7)
    if frequency_days in {30, 60}:
        day_of_month = _recurring_month_day(recurring_day)
        if day_of_month is None:
            return None
        if delivery_date.day <= day_of_month:
            return date(delivery_date.year, delivery_date.month, day_of_month)
        month_index = delivery_date.year * 12 + delivery_date.month
        year, month = divmod(month_index, 12)
        return date(year, month + 1, day_of_month)
    return delivery_date


def _next_recurring_date(
    delivery_date: date,
    frequency_days: int,
    recurring_day: str,
    fixed_delivery_day: bool,
) -> Optional[date]:
    next_date = delivery_date + timedelta(days=frequency_days)
    if not fixed_delivery_day:
        return next_date
    if frequency_days in {7, 14}:
        target_weekday = _recurring_weekday(recurring_day)
        if target_weekday is None:
            return None
        return next_date + timedelta(days=(target_weekday - next_date.weekday()) % 7)
    if frequency_days in {30, 60}:
        day_of_month = _recurring_month_day(recurring_day)
        if day_of_month is None:
            return None
        months_to_add = frequency_days // 30
        month_index = delivery_date.year * 12 + delivery_date.month - 1 + months_to_add
        year, month = divmod(month_index, 12)
        return date(year, month + 1, day_of_month)
    return next_date


def _recurring_schedule_for_order(
    order_row: Dict[str, Any],
    delivery_date: date,
    site: Dict[str, Any],
) -> Tuple[int, int, int, str, str, str]:
    if not bool(order_row.get("recurring_order")):
        return 0, 0, 1, delivery_date.isoformat(), "", ""
    frequency_days = _configured_recurring_frequency(order_row, site)
    if frequency_days is None:
        raise OrderNotReady("Impossibile programmare la ricorrenza: frequenza non riconosciuta.")
    try:
        request_details = json.loads(order_row.get("request_details_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        request_details = {}
    recurring_day = str(request_details.get("recurring_day") or "") if isinstance(request_details, dict) else ""
    recurring_settings = site.get("recurring_order", {})
    fixed_delivery_day = not (
        isinstance(recurring_settings, dict) and recurring_settings.get("fixed_delivery_day") is False
    )
    scheduled_date = _first_recurring_date(delivery_date, frequency_days, recurring_day, fixed_delivery_day)
    if scheduled_date is None:
        raise OrderNotReady("Impossibile programmare la ricorrenza: verifica il giorno richiesto.")
    next_date = _next_recurring_date(scheduled_date, frequency_days, recurring_day, fixed_delivery_day)
    if next_date is None:
        raise OrderNotReady("Impossibile programmare la ricorrenza: verifica il giorno richiesto.")
    label = str(request_details.get("recurring_frequency") or "") if isinstance(request_details, dict) else ""
    return (
        1,
        frequency_days,
        int(fixed_delivery_day),
        scheduled_date.isoformat(),
        next_date.isoformat(),
        label,
    )


def confirm_order(connection: sqlite3.Connection, order_id: str, site: Dict[str, Any]) -> Dict[str, Any]:
    order_id = order_id.strip()
    if not order_id:
        raise AppError("Selezionare un ordine da confermare.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if row is None:
            raise AppError(f"Ordine #{order_id} non trovato.")
        order_row = dict(row)
        if order_row["confirmation_status"] == "confirmed":
            connection.commit()
            return {
                "order_id": order_id,
                "confirmed": True,
                "already_confirmed": True,
                "delivery_date": order_row["delivery_date"],
                "recurring_scheduled": bool(order_row["recurring_enabled"]),
                "recurring_frequency_days": int(order_row["recurring_frequency_days"]),
                "next_recurring_delivery_date": order_row["next_recurring_delivery_date"],
            }
        if order_row["confirmation_status"] == "sending":
            connection.commit()
            raise OrderNotReady("Email di conferma già in invio per questo ordine.")

        stock, status = current_order_availability(connection, order_row)
        order_datetime = datetime.fromisoformat(order_row["ordered_at"])
        first_month_order, voucher_valid, validity_days = _validate_voucher(
            connection,
            order_id,
            order_row["customer_email"],
            order_row["customer_phone"],
            order_datetime,
            bool(order_row["recurring_order"]),
            order_row["voucher_candidate"],
            order_row["voucher_candidate_value"],
            order_row["products_subtotal"],
            order_row["recurring_discount"],
            site,
        )
        order_row.update(
            {
                "availability_json": json.dumps(stock, ensure_ascii=False),
                "first_month_order": int(first_month_order),
                "voucher_valid": int(voucher_valid),
                "voucher_code": order_row["voucher_candidate"] if voucher_valid else "",
                "voucher_value": order_row["voucher_candidate_value"] if voucher_valid else "",
                "voucher_validity_days": validity_days if voucher_valid else None,
            }
        )
        connection.execute(
            """
            UPDATE orders SET status = ?, availability_json = ?, first_month_order = ?,
                voucher_valid = ?, voucher_code = ?, voucher_value = ?, voucher_validity_days = ?
            WHERE order_id = ?
            """,
            (
                status,
                order_row["availability_json"],
                order_row["first_month_order"],
                order_row["voucher_valid"],
                order_row["voucher_code"],
                order_row["voucher_value"],
                order_row["voucher_validity_days"],
                order_id,
            ),
        )
        if voucher_valid and validity_days is not None:
            connection.execute(
                """
                INSERT OR IGNORE INTO valid_vouchers (code, order_id, value, validity_days, validated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order_row["voucher_candidate"],
                    order_id,
                    order_row["voucher_candidate_value"],
                    validity_days,
                    datetime.now(ROME).isoformat(timespec="seconds"),
                ),
            )
        if status != "disponibile":
            connection.commit()
            reasons = []
            for item in stock:
                if item["state"] == "quantita_insufficiente":
                    reasons.append(f"{item['name']}: richiesti {item['requested']}, disponibili {item['available']}")
                elif item["state"] == "catalogo_non_disponibile":
                    reasons.append(f"{item['name']}: non disponibile nel catalogo")
                elif item["state"] in {"da_verificare", "catalogo_mancante"}:
                    reasons.append(f"{item['name']}: disponibilità da verificare")
            raise OrderNotReady("Ordine non confermato. " + "; ".join(reasons))
        if not order_row["response_to"]:
            connection.commit()
            raise OrderNotReady("Email cliente mancante: ordine non confermato e nessuna email inviata.")

        today = datetime.now(ROME).date()
        try:
            preferred_date = date.fromisoformat(order_row["preferred_delivery_date"])
        except ValueError:
            preferred_date = today
        base_delivery_date = max(preferred_date, today)
        (
            recurring_enabled,
            recurring_frequency_days,
            recurring_fixed_day,
            delivery_date,
            next_recurring_delivery_date,
            recurring_frequency_label,
        ) = _recurring_schedule_for_order(order_row, base_delivery_date, site)
        order_row.update(
            {
                "recurring_enabled": recurring_enabled,
                "recurring_frequency_days": recurring_frequency_days,
                "recurring_fixed_day": recurring_fixed_day,
                "next_recurring_delivery_date": next_recurring_delivery_date,
                "recurring_frequency_label": recurring_frequency_label,
            }
        )
        subject = f"Conferma ordine #{order_id} - {site.get('brand') or 'Cartaway'}"
        text, markup = _format_order_confirmation(
            order_row,
            site,
            voucher_valid,
            validity_days if voucher_valid else None,
            delivery_date,
        )
        order_row.update(
            {
                "response_subject": subject,
                "response_text": text,
                "response_html": markup,
            }
        )
        connection.execute(
            "UPDATE orders SET confirmation_status = 'sending', delivery_date = ?, email_status = 'in_corso' WHERE order_id = ?",
            (delivery_date, order_id),
        )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise

    sender = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")).strip()
    try:
        send_email(_make_customer_email(order_row, site, sender))
    except (AppError, OSError, smtplib.SMTPException) as exc:
        connection.execute(
            "UPDATE orders SET confirmation_status = 'pending', email_status = 'errore' WHERE order_id = ?",
            (order_id,),
        )
        connection.commit()
        raise AppError(f"Ordine verificato, ma email di conferma non inviata: {exc}") from exc

    confirmed_at = datetime.now(ROME).isoformat(timespec="seconds")
    connection.execute(
        """
        UPDATE orders SET confirmation_status = 'confirmed', confirmed_at = ?,
            response_sent = 1, email_status = 'inviata', recurring_enabled = ?,
            recurring_frequency_days = ?, recurring_fixed_day = ?, next_recurring_delivery_date = ?
        WHERE order_id = ?
        """,
        (
            confirmed_at,
            recurring_enabled,
            recurring_frequency_days,
            recurring_fixed_day,
            next_recurring_delivery_date,
            order_id,
        ),
    )
    connection.commit()
    return {
        "order_id": order_id,
        "confirmed": True,
        "already_confirmed": False,
        "delivery_date": delivery_date,
        "recurring_scheduled": bool(recurring_enabled),
        "recurring_frequency_days": recurring_frequency_days,
        "next_recurring_delivery_date": next_recurring_delivery_date,
    }


def disable_recurring_schedule(connection: sqlite3.Connection, order_id: str) -> Dict[str, Any]:
    order_id = order_id.strip()
    if not order_id:
        raise AppError("Selezionare un ordine ricorrente.")
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            "SELECT recurring_enabled, confirmation_status FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            raise AppError(f"Ordine #{order_id} non trovato.")
        if row["confirmation_status"] != "confirmed":
            raise OrderNotReady("Solo una programmazione confermata può essere disattivata.")
        already_disabled = not bool(row["recurring_enabled"])
        if not already_disabled:
            connection.execute(
                "UPDATE orders SET recurring_enabled = 0, next_recurring_delivery_date = '' WHERE order_id = ?",
                (order_id,),
            )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    return {"order_id": order_id, "disabled": True, "already_disabled": already_disabled}


def mark_order_delivered(
    connection: sqlite3.Connection,
    order_id: str,
    delivery_date: str = "",
) -> Dict[str, Any]:
    order_id = order_id.strip()
    if not order_id:
        raise AppError("Selezionare un ordine da segnare come consegnato.")

    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            "SELECT confirmation_status, delivery_status, delivered_at, delivery_date, "
            "availability_json, recurring_enabled, recurring_frequency_days, recurring_fixed_day, "
            "next_recurring_delivery_date, last_delivered_date, request_details_json "
            "FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            raise AppError(f"Ordine #{order_id} non trovato.")
        if row["recurring_enabled"] and not delivery_date.strip():
            raise OrderNotReady("Indicare la data della consegna per registrare l'occorrenza corretta.")
        expected_date = delivery_date.strip() or (
            row["delivery_date"] if row["delivery_status"] != "delivered"
            else row["last_delivered_date"] or row["delivery_date"]
        )
        if expected_date and expected_date == row["last_delivered_date"]:
            connection.commit()
            return {
                "order_id": order_id,
                "delivered": True,
                "already_delivered": True,
                "delivered_at": row["delivered_at"],
            }
        if row["confirmation_status"] != "confirmed":
            raise OrderNotReady("Solo un ordine confermato può essere segnato come consegnato.")
        if expected_date != row["delivery_date"] or row["delivery_status"] == "delivered":
            raise OrderNotReady("Questa data non è più prevista nella programmazione dell'ordine.")
        recurring_occurrence = bool(
            row["recurring_enabled"]
            and row["recurring_frequency_days"] > 0
            and row["next_recurring_delivery_date"]
        )
        next_delivery_date = ""
        following_recurring_date = ""
        if recurring_occurrence:
            try:
                next_delivery_date = date.fromisoformat(row["next_recurring_delivery_date"])
            except ValueError as exc:
                raise OrderNotReady("La prossima data ricorrente non è valida.") from exc
            try:
                request_details = json.loads(row["request_details_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                request_details = {}
            recurring_day = str(request_details.get("recurring_day") or "") if isinstance(request_details, dict) else ""
            following_recurring_date = _next_recurring_date(
                next_delivery_date,
                int(row["recurring_frequency_days"]),
                recurring_day,
                bool(row["recurring_fixed_day"]),
            )
            if following_recurring_date is None:
                raise OrderNotReady("Impossibile calcolare la prossima data ricorrente; verifica giorno e frequenza.")

        try:
            stored_items = json.loads(row["availability_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise AppError("Dati dei prodotti dell'ordine non leggibili.") from exc
        if not isinstance(stored_items, list) or not stored_items:
            raise AppError("L'ordine non contiene prodotti verificabili.")

        quantities: Dict[str, int] = {}
        names: Dict[str, str] = {}
        for item in stored_items:
            if not isinstance(item, dict):
                raise AppError("Dati dei prodotti dell'ordine non leggibili.")
            product_id = str(item.get("product_id") or "").strip()
            requested = item.get("requested")
            if not product_id or isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
                raise AppError("Quantità prodotto non valida nell'ordine.")
            quantities[product_id] = quantities.get(product_id, 0) + requested
            names[product_id] = str(item.get("name") or product_id)

        for product_id, requested in quantities.items():
            product = connection.execute(
                "SELECT name, quantity FROM products WHERE product_id = ?",
                (product_id,),
            ).fetchone()
            if product is None:
                raise OrderNotReady(f"{names[product_id]}: prodotto assente dall'inventario; scarico annullato.")
            if product["quantity"] is None:
                raise OrderNotReady(f"{product['name']}: giacenza da impostare; scarico annullato.")
            available = int(product["quantity"])
            if available < requested:
                raise OrderNotReady(
                    f"{product['name']}: richiesti {requested}, disponibili {available}; "
                    "nessuna quantità è stata scalata. Aggiorna la giacenza e riprova."
                )

        delivered_at = datetime.now(ROME).isoformat(timespec="seconds")
        for product_id, requested in quantities.items():
            cursor = connection.execute(
                "UPDATE products SET quantity = quantity - ?, updated_at = ? "
                "WHERE product_id = ? AND quantity >= ?",
                (requested, delivered_at, product_id, requested),
            )
            if cursor.rowcount != 1:
                raise OrderNotReady("La giacenza è cambiata; nessuna quantità è stata scalata. Aggiorna e riprova.")
        if recurring_occurrence:
            connection.execute(
                "UPDATE orders SET delivery_status = 'pending', delivered_at = ?, "
                "last_delivered_date = ?, delivery_date = ?, next_recurring_delivery_date = ? "
                "WHERE order_id = ?",
                (
                    delivered_at,
                    expected_date,
                    next_delivery_date.isoformat(),
                    following_recurring_date.isoformat(),
                    order_id,
                ),
            )
        else:
            connection.execute(
                "UPDATE orders SET delivery_status = 'delivered', delivered_at = ?, "
                "last_delivered_date = ? WHERE order_id = ?",
                (delivered_at, expected_date, order_id),
            )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise

    return {
        "order_id": order_id,
        "delivered": True,
        "already_delivered": False,
        "delivered_at": delivered_at,
        "recurring": recurring_occurrence,
    }


def send_email(message: EmailMessage) -> None:
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    if not host or not user or not password:
        raise AppError("Configurare SMTP_HOST, SMTP_USER e SMTP_PASSWORD prima dell'invio.")
    try:
        port = int(os.environ.get("SMTP_PORT", "465"))
    except ValueError as exc:
        raise AppError("SMTP_PORT deve essere un numero.") from exc
    security = os.environ.get("SMTP_SECURITY", "auto").strip().lower()
    if security == "auto":
        security = "ssl" if port == 465 else "starttls"
    if security not in {"ssl", "starttls"}:
        raise AppError("SMTP_SECURITY deve essere 'ssl', 'starttls' o 'auto'.")
    context = ssl.create_default_context()
    if security == "ssl":
        server: Any = smtplib.SMTP_SSL(host, port, context=context, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    with server:
        if security == "starttls":
            server.starttls(context=context)
        server.login(user, password)
        server.send_message(message)


def _mark_message_processed(connection: sqlite3.Connection, mailbox: str, uid: str, order_id: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO processed_messages (mailbox, uid, order_id, processed_at) VALUES (?, ?, ?, ?)",
        (mailbox, uid, order_id, datetime.now(ROME).isoformat(timespec="seconds")),
    )
    connection.commit()


def _imap_timeout_seconds() -> float:
    try:
        timeout = float(os.environ.get("IMAP_TIMEOUT", "15"))
    except ValueError as exc:
        raise AppError("IMAP_TIMEOUT deve essere un numero tra 1 e 120 secondi.") from exc
    if not 1 <= timeout <= 120:
        raise AppError("IMAP_TIMEOUT deve essere tra 1 e 120 secondi.")
    return timeout


def _validate_imap_host(host: str) -> None:
    if host.casefold().rstrip(".") == "smtps.aruba.it":
        raise AppError(
            "IMAP_HOST è impostato su smtps.aruba.it, che è il server SMTP in uscita. "
            "Per una casella Aruba standard usa IMAP_HOST=imaps.aruba.it e IMAP_PORT=993; "
            "per PEC o servizi diversi verifica i parametri specifici del provider."
        )


def list_mail_folders() -> List[str]:
    host = os.environ.get("IMAP_HOST", "").strip()
    user = os.environ.get("IMAP_USER", "").strip()
    password = os.environ.get("IMAP_PASSWORD", "")
    if not host or not user or not password:
        raise AppError("Configurare IMAP_HOST, IMAP_USER e IMAP_PASSWORD prima della lettura.")
    _validate_imap_host(host)
    try:
        port = int(os.environ.get("IMAP_PORT", "993"))
    except ValueError as exc:
        raise AppError("IMAP_PORT deve essere un numero.") from exc
    client = imaplib.IMAP4_SSL(
        host,
        port,
        ssl_context=ssl.create_default_context(),
        timeout=_imap_timeout_seconds(),
    )
    try:
        status, _ = client.login(user, password)
        if status != "OK":
            raise AppError("Login IMAP non riuscito.")
        status, data = client.list()
        if status != "OK":
            raise AppError("Impossibile elencare le cartelle IMAP.")
        return [line.decode("utf-8", errors="replace") for line in data or [] if line]
    finally:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def check_mail(connection: sqlite3.Connection, products: Dict[str, Dict[str, Any]], site: Dict[str, Any], limit: int) -> int:
    host = os.environ.get("IMAP_HOST", "").strip()
    user = os.environ.get("IMAP_USER", "").strip()
    password = os.environ.get("IMAP_PASSWORD", "")
    if not host or not user or not password:
        raise AppError("Configurare IMAP_HOST, IMAP_USER e IMAP_PASSWORD prima della lettura.")
    _validate_imap_host(host)
    try:
        port = int(os.environ.get("IMAP_PORT", "993"))
    except ValueError as exc:
        raise AppError("IMAP_PORT deve essere un numero.") from exc
    folder = "INBOX"
    if limit < 1:
        raise AppError("Il limite email deve essere maggiore di zero.")
    client = imaplib.IMAP4_SSL(
        host,
        port,
        ssl_context=ssl.create_default_context(),
        timeout=_imap_timeout_seconds(),
    )
    processed = 0
    mailbox_key = f"{host.casefold()}|{user.casefold()}|{folder.casefold()}"
    try:
        client.login(user, password)
        status, _ = client.select(folder)
        if status != "OK":
            raise AppError(f"Impossibile aprire la cartella IMAP '{folder}'.")
        status, data = client.uid("search", None, "UNSEEN")
        if status != "OK":
            raise AppError("Ricerca email non lette fallita.")
        uids = data[0].split()[-limit:] if data and data[0] else []
        internal_emails = [
            str(site.get("email", "")),
            os.environ.get("SMTP_FROM", ""),
            user,
        ]
        for raw_uid in uids:
            uid = raw_uid.decode("ascii", errors="replace")
            recorded = connection.execute(
                "SELECT order_id FROM processed_messages WHERE mailbox = ? AND uid = ?",
                (mailbox_key, uid),
            ).fetchone()
            if recorded:
                client.uid("store", uid, "+FLAGS", r"(\Seen)")
                continue
            status, fetched = client.uid("fetch", uid, "(RFC822)")
            raw_message = next((part[1] for part in fetched or [] if isinstance(part, tuple)), None)
            if status != "OK" or not raw_message:
                print(f"UID {uid}: impossibile scaricare il messaggio.", file=sys.stderr)
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw_message)
            subject = _header_text(message.get("Subject"))
            try:
                parsed = parse_order_email(message, products, internal_emails)
            except AppError as exc:
                if "Riferimento ordine non trovato" in str(exc) and "Riepilogo richiesta" not in subject:
                    continue
                print(f"UID {uid}: {exc}", file=sys.stderr)
                continue
            order_row = prepare_order(connection, parsed, site)
            print(f"Ordine {parsed.order_id}: richiesta importata; conferma email manuale necessaria.")
            _mark_message_processed(connection, mailbox_key, uid, parsed.order_id)
            client.uid("store", uid, "+FLAGS", r"(\Seen)")
            processed += 1
    finally:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    return processed


def build_maps_urls(origin: str, destinations: Sequence[str], return_to_origin: bool = False) -> List[str]:
    origin = _clean_text(origin)
    stops = [_clean_text(value) for value in destinations if _clean_text(value)]
    if not origin:
        raise AppError("Inserire un punto di partenza.")
    if not stops:
        raise AppError("Inserire almeno un indirizzo di consegna.")
    nodes = [origin, *stops]
    if return_to_origin:
        nodes.append(origin)
    urls: List[str] = []
    start = 0
    while start < len(nodes) - 1:
        end = min(start + 10, len(nodes) - 1)
        segment = nodes[start : end + 1]
        query = {
            "api": "1",
            "origin": segment[0],
            "destination": segment[-1],
            "travelmode": "driving",
        }
        if len(segment) > 2:
            query["waypoints"] = "|".join(segment[1:-1])
        urls.append("https://www.google.com/maps/dir/?" + urlencode(query))
        start = end
    return urls


def build_calendar_url(
    title: str,
    event_date: date,
    start_time: time,
    end_time: time,
    origin: str,
    details: str,
) -> str:
    if end_time <= start_time:
        raise AppError("L'orario di fine deve essere successivo all'orario di inizio nella stessa giornata.")
    starts = datetime.combine(event_date, start_time, tzinfo=ROME).strftime("%Y%m%dT%H%M%S")
    ends = datetime.combine(event_date, end_time, tzinfo=ROME).strftime("%Y%m%dT%H%M%S")
    query = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{starts}/{ends}",
        "ctz": "Europe/Rome",
        "location": origin,
        "details": details,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(query)


def _parse_time(value: str, label: str) -> time:
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError as exc:
        raise AppError(f"{label}: usare il formato HH:MM.") from exc


def plan_route(site: Dict[str, Any]) -> None:
    default_origin = str(site.get("address", "")).strip()
    origin = input(f"Partenza [{default_origin}]: ").strip() or default_origin
    if not origin:
        raise AppError("Inserire l'indirizzo di partenza; data/site.json contiene solo un esempio.")
    today = datetime.now(ROME).date()
    raw_date = input(f"Data giro [{today.isoformat()}]: ").strip() or today.isoformat()
    try:
        event_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise AppError("La data deve essere nel formato AAAA-MM-GG.") from exc
    start = _parse_time(input("Ora inizio [09:00]: ").strip() or "09:00", "Ora inizio")
    end = _parse_time(input("Ora fine [13:00]: ").strip() or "13:00", "Ora fine")
    destinations: List[str] = []
    print("Inserisci gli indirizzi di consegna nell'ordine desiderato; riga vuota per terminare.")
    while True:
        address = input(f"Tappa {len(destinations) + 1}: ").strip()
        if not address:
            break
        destinations.append(address)
    return_home = input("Rientro al punto di partenza? [s/N]: ").strip().casefold() in {"s", "si", "sì"}
    urls = build_maps_urls(origin, destinations, return_home)
    details = "Indirizzi inseriti manualmente e mantenuti nell'ordine indicato.\n\n" + "\n".join(urls)
    calendar_url = build_calendar_url(
        f"Giro consegne Cartaway - {event_date.isoformat()}",
        event_date,
        start,
        end,
        origin,
        details,
    )
    print("\nLink Google Maps:")
    for index, url in enumerate(urls, start=1):
        print(f"{index}. {url}")
    print(f"\nLink Google Calendar: {calendar_url}")
    print("Google Maps mantiene l'ordine inserito; il link non riordina automaticamente le tappe.")


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except OSError as exc:
        raise AppError(f"Impossibile leggere {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AppError(f"JSON non valido in {path}: {exc}") from exc


def _nonnegative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("inserire un numero intero") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("il valore deve essere almeno zero")
    return parsed


def _positive_integer(value: str) -> int:
    parsed = _nonnegative_integer(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("il valore deve essere maggiore di zero")
    return parsed


def _print_stock(connection: sqlite3.Connection) -> None:
    print(f"{'ID':38} {'Giacenza':12} {'Catalogo':12} Prodotto")
    for row in list_stock(connection):
        quantity = "da impostare" if row["quantity"] is None else str(row["quantity"])
        available = "attivo" if row["catalog_available"] else "non disponibile"
        print(f"{row['product_id'][:38]:38} {quantity:12} {available:12} {row['name']}")


def _print_orders(connection: sqlite3.Connection, limit: int) -> None:
    rows = connection.execute(
        """
        SELECT order_id, ordered_at, customer_email, status, voucher_valid, email_status
        FROM orders ORDER BY ordered_at DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    if not rows:
        print("Nessun ordine elaborato.")
        return
    print(f"{'Riferimento':14} {'Data':22} {'Esito stock':26} {'Buono':10} {'Email':18} Cliente")
    for row in rows:
        voucher = "convalidato" if row["voucher_valid"] else "no"
        print(
            f"{row['order_id'][:14]:14} {row['ordered_at'][:22]:22} {row['status'][:26]:26} "
            f"{voucher:10} {row['email_status'][:18]:18} {row['customer_email'] or '(email assente)'}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gestione locale degli ordini e delle consegne Cartaway.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="database SQLite locale")
    parser.add_argument("--products", type=Path, default=ROOT / "data" / "products.json")
    parser.add_argument("--site", type=Path, default=ROOT / "data" / "site.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="crea il database e sincronizza il catalogo")
    stock = commands.add_parser("stock", help="consulta o aggiorna le giacenze")
    stock_commands = stock.add_subparsers(dest="stock_command", required=True)
    stock_commands.add_parser("list", help="mostra catalogo e giacenze")
    stock_set = stock_commands.add_parser("set", help="imposta la giacenza di un prodotto")
    stock_set.add_argument("product_id")
    stock_set.add_argument("quantity", type=_nonnegative_integer)
    stock_add = stock_commands.add_parser("add", help="aggiunge pezzi a una giacenza già impostata")
    stock_add.add_argument("product_id")
    stock_add.add_argument("quantity", type=_nonnegative_integer)
    mail = commands.add_parser("check-mail", help="legge i riepiloghi non letti tramite IMAP")
    mail.add_argument("--limit", type=_positive_integer, default=50)
    commands.add_parser("mail-folders", help="elenca le cartelle IMAP senza leggere o modificare email")
    orders = commands.add_parser("orders", help="mostra gli ordini già elaborati")
    orders.add_argument("--limit", type=_positive_integer, default=30)
    commands.add_parser("route", help="inserisce manualmente tappe e crea link Maps e Calendar")
    web = commands.add_parser("web", help="avvia il gestionale web solo sul computer locale")
    web.add_argument("--port", type=_positive_integer, default=8765)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        site = _read_json(args.site)
        catalog_data = _read_json(args.products)
        if not isinstance(site, dict) or not isinstance(catalog_data, dict):
            raise AppError("I file site.json e products.json devono contenere oggetti JSON.")
        products_list = catalog_data.get("products", [])
        if not isinstance(products_list, list):
            raise AppError("data/products.json non contiene una lista 'products'.")
        products_by_id = {
            str(product.get("id")): product
            for product in products_list
            if isinstance(product, dict) and product.get("id")
        }
        if args.command == "web":
            from .gestionale_web import serve_web

            serve_web(args.database, site, products_list, products_by_id, args.port)
            return 0
        if args.command == "mail-folders":
            for folder in list_mail_folders():
                print(folder)
            return 0
        if args.command == "route":
            plan_route(site)
            return 0

        connection = open_database(args.database)
        try:
            sync_catalog(connection, products_list)
            if args.command == "init":
                print(f"Database pronto: {args.database.expanduser()}")
                print(f"Catalogo sincronizzato: {len(products_by_id)} prodotti.")
            elif args.command == "stock":
                if args.stock_command == "list":
                    _print_stock(connection)
                else:
                    total = set_stock(
                        connection,
                        args.product_id,
                        args.quantity,
                        add=args.stock_command == "add",
                    )
                    print(f"{args.product_id}: giacenza aggiornata a {total}.")
            elif args.command == "orders":
                _print_orders(connection, args.limit)
            elif args.command == "check-mail":
                processed = check_mail(connection, products_by_id, site, args.limit)
                print(f"Email elaborate: {processed}.")
        finally:
            connection.close()
    except (AppError, OSError, sqlite3.Error, imaplib.IMAP4.error) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Operazione interrotta.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())