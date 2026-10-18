"""Interfaccia HTTP locale per il gestionale Cartaway."""

from __future__ import annotations

import json
import imaplib
import re
import sqlite3
import unicodedata
from datetime import date, datetime, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlsplit

from . import gestionale


ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 64 * 1024
DELIVERY_TIMES_PATTERN = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")


def _requested_delivery_times(value: str) -> List[time]:
    return [
        datetime.strptime(match, "%H:%M").time()
        for match in DELIVERY_TIMES_PATTERN.findall(value)[:2]
    ]


def _delivery_time_sort_key(order: Dict[str, Any]) -> Tuple[int, int]:
    preference = str(order.get("preferred_delivery_time") or "").strip().casefold()
    requested_times = _requested_delivery_times(preference)
    if requested_times:
        requested_start = requested_times[0]
        minutes = requested_start.hour * 60 + requested_start.minute
        return (0 if requested_start < time(12, 0) else 1, minutes)
    if "mattina" in preference:
        return (0, -1)
    if "pomeriggio" in preference:
        return (1, 12 * 60)
    return (2, 0)


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


def _group_route_orders_by_city(
    orders: List[Dict[str, Any]],
    origin: str = "",
) -> List[Dict[str, Any]]:
    time_ordered = sorted(orders, key=_delivery_time_sort_key)
    city_rank: Dict[Tuple[str, str], int] = {}
    city_time_priority: Dict[Tuple[str, str], Tuple[int, int]] = {}
    for order in time_ordered:
        key = _delivery_city_key(order)
        city_rank.setdefault(key, len(city_rank))
        order_priority = _delivery_time_sort_key(order)
        if key not in city_time_priority or order_priority < city_time_priority[key]:
            city_time_priority[key] = order_priority
    origin_city = _origin_city_key(origin, time_ordered)
    if origin_city in city_rank:
        earlier_cities = [
            city
            for city in city_rank
            if city != origin_city and city_time_priority[city] < city_time_priority[origin_city]
        ]
        city_order = earlier_cities + [origin_city] + [
            city for city in city_rank if city != origin_city and city not in earlier_cities
        ]
        city_rank = {city: rank for rank, city in enumerate(city_order)}
    return sorted(
        time_ordered,
        key=lambda order: (city_rank[_delivery_city_key(order)], _delivery_time_sort_key(order)),
    )


def _route_schedule_warning(
    order: Dict[str, Any],
    route_start: time,
    route_end: time,
) -> str:
    preference = str(order.get("preferred_delivery_time") or "").strip()
    normalized_preference = preference.casefold()
    requested_times = _requested_delivery_times(preference)
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
            finally:
                connection.close()
            return {"product_id": product_id, "quantity": total}

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
            connection = gestionale.open_database(database)
            try:
                return gestionale.confirm_order(connection, order_id, site)
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

        def _delivery_orders(self, event_date: date) -> Dict[str, Any]:
            connection = gestionale.open_database(database)
            try:
                today = datetime.now(gestionale.ROME).date()
                rows = connection.execute(
                    """
                    SELECT order_id, customer_name, delivery_address, delivery_city,
                        preferred_delivery_date, preferred_delivery_time, delivery_notes,
                        confirmed_at, delivery_date, ordered_at, availability_json,
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
                inventory = {
                    row["product_id"]: {
                        "catalog_available": bool(row["catalog_available"]),
                        "quantity": row["quantity"],
                    }
                    for row in gestionale.list_stock(connection)
                }
                occurrences = []
                for row in rows:
                    base_order = dict(row)
                    try:
                        request_details = json.loads(base_order.pop("request_details_json"))
                    except (json.JSONDecodeError, TypeError):
                        request_details = {}
                    if not isinstance(request_details, dict):
                        request_details = {}
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
                        availability, _ = gestionale.current_order_availability(connection, order)
                    except gestionale.AppError as exc:
                        availability = []
                        order["availability_issue"] = str(exc)
                    for item in availability:
                        product = inventory.get(item["product_id"])
                        if product is None:
                            item["state"] = "catalogo_mancante"
                            item["available"] = 0
                        elif not product["catalog_available"]:
                            item["state"] = "catalogo_non_disponibile"
                            item["available"] = 0
                        elif product["quantity"] is None:
                            item["state"] = "da_verificare"
                            item["available"] = None
                        else:
                            item["available"] = int(product["quantity"])
                            item["state"] = (
                                "disponibile"
                                if item["available"] >= int(item["requested"])
                                else "quantita_insufficiente"
                            )
                    availability_status = (
                        gestionale._availability_status(availability) if availability else "da_verificare"
                    )
                    issues = []
                    for item in availability:
                        if item["state"] == "quantita_insufficiente":
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
                            inventory[item["product_id"]]["quantity"] -= int(item["requested"])
                    if order["delivery_date"] == event_date.isoformat():
                        orders.append(order)
                return {"date": event_date.isoformat(), "orders": orders}
            finally:
                connection.close()

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
            route_orders = _group_route_orders_by_city(route_orders, origin)
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
                return_to_origin=payload.get("return_to_origin") is True,
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
                "Ordini confermati; tappe raggruppate per città dando precedenza alla partenza, "
                "salvo orari più urgenti.\n\n"
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