"""
API сервер для системы учета готовности изделий
"""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import fdb
from datetime import datetime, timedelta

from models import (
    BarcodeRequest, ApprovalResponse, ProductInfo, HealthResponse,
    DailyStatsResponse, DailyStatsRow, OrderStatsResponse, OrderStatsRow
)
from database import db
from config import settings


app = FastAPI(
    title="Barcode Approval API",
    description="API для приходования изделий по штрихкоду",
    version="1.2.0"  # Добавлены endpoints для статистики
)

# CORS middleware для возможности обращения с клиента
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_barcode(barcode: str) -> dict:
    """
    Парсинг штрихкода с определением типа

    Форматы:
    - D-123456789: изделие (9 цифр после префикса)
    - ORD-12345: заказ (ID заказа)
    - T-12345: материал (ID материала - itemsdetailid)
    - S-12345: набор (ID набора - itemssetid)
    - 123456789: старый формат изделия (9 цифр)
    - 12345: старый формат заказа (не 9 цифр)

    Для обратной совместимости также поддерживаются старые префиксы:
    - IZD-123456789, ITM-12345, SET-12345

    Returns:
        dict: {
            'type': 'IZD' | 'ORD' | 'ITM' | 'SET' | 'LEGACY_IZD' | 'LEGACY_ORD',
            'value': str - значение после префикса
        }
    """
    barcode = barcode.strip().upper()

    # Проверка на наличие префикса (формат X-... или XXX-...)
    if '-' in barcode:
        parts = barcode.split('-', 1)
        if len(parts) == 2:
            prefix, value = parts
            prefix = prefix.strip()
            value = value.strip()

            # Новые префиксы
            if prefix == 'D':
                return {'type': 'IZD', 'value': value}
            elif prefix == 'ORD':
                return {'type': 'ORD', 'value': value}
            elif prefix == 'T':
                return {'type': 'ITM', 'value': value}
            elif prefix == 'S':
                return {'type': 'SET', 'value': value}
            # Старые префиксы (обратная совместимость)
            elif prefix in ['IZD', 'ITM', 'SET']:
                return {'type': prefix, 'value': value}

    # Старый формат без префикса
    if barcode.isdigit():
        if len(barcode) == 9:
            return {
                'type': 'LEGACY_IZD',
                'value': barcode
            }
        else:
            return {
                'type': 'LEGACY_ORD',
                'value': barcode
            }

    # Неизвестный формат
    return {
        'type': 'UNKNOWN',
        'value': barcode
    }


async def process_itm_barcode(barcode_value: str) -> ApprovalResponse:
    """
    Обработка штрихкода материала (префикс T или ITM)
    Поиск CT_ELEMENTS по полю ITEMSDETAILID

    Args:
        barcode_value: ID материала (itemsdetailid)

    Returns:
        ApprovalResponse с результатом операции
    """
    try:
        itemsdetailid = int(barcode_value)
    except ValueError:
        return ApprovalResponse(
            success=False,
            message=f"Некорректный ID материала: {barcode_value}",
            voice_message="Ошибка. Некорректный ID материала",
            product_info=None
        )

    # Находим элемент по ITEMSDETAILID
    query_element = """
        SELECT
            e.CTELEMENTSID,
            e.RNAME as ELEMENT_NAME,
            e.WIDTH,
            e.HEIGHT,
            e.MODELID,
            e.ORDERITEMSID,
            e.ITEMSDETAILID
        FROM CT_ELEMENTS e
        WHERE e.ITEMSDETAILID = ?
    """

    element_result = db.execute_query(query_element, (itemsdetailid,))

    if not element_result:
        return ApprovalResponse(
            success=False,
            message=f"Материал с ID {itemsdetailid} не найден",
            voice_message="Материал не найден",
            product_info=None
        )

    element_data = element_result[0]
    ctelementsid = element_data['CTELEMENTSID']
    element_name = element_data['ELEMENT_NAME'].strip() if element_data['ELEMENT_NAME'] else None
    width = element_data['WIDTH']
    height = element_data['HEIGHT']
    orderitems_id = element_data['ORDERITEMSID']

    # Получаем информацию о заказе через ORDERITEMSID
    order_number = None
    proddate = None
    order_id = None
    total_items_in_order = None
    approved_items_in_order = None

    if orderitems_id:
        query_order = """
            SELECT
                o.ORDERID,
                o.ORDERNO,
                o.PRODDATE
            FROM ORDERITEMS oi
            INNER JOIN ORDERS o ON oi.ORDERID = o.ORDERID
            WHERE oi.ORDERITEMSID = ?
        """
        order_result = db.execute_query(query_order, (orderitems_id,))

        if order_result:
            order_data = order_result[0]
            order_number = order_data['ORDERNO'].strip() if order_data['ORDERNO'] else None
            order_id = order_data['ORDERID']

            # Форматируем дату производства
            proddate_raw = order_data.get('PRODDATE')
            if proddate_raw:
                if isinstance(proddate_raw, datetime):
                    proddate = proddate_raw.strftime('%d.%m.%Y')
                elif hasattr(proddate_raw, 'strftime'):
                    proddate = proddate_raw.strftime('%d.%m.%Y')
                else:
                    proddate = str(proddate_raw)

            # Получаем статистику по заказу
            query_order_stats = """
                SELECT
                    SUM(wd.qty) as TOTAL,
                    SUM(CASE WHEN wd.isapproved = 1 THEN wd.qty ELSE 0 END) as APPROVED
                FROM ORDERS o
                JOIN ORDERITEMS oi ON oi.ORDERID = o.ORDERID
                JOIN MODELS m ON m.ORDERITEMSID = oi.ORDERITEMSID
                LEFT JOIN CT_ELEMENTS el ON el.MODELID = m.MODELID
                LEFT JOIN CT_WHDETAIL wd ON wd.CTELEMENTSID = el.CTELEMENTSID
                WHERE o.ORDERID = ?
                AND el.CTTYPEELEMSID = 2
            """
            stats_result = db.execute_query(query_order_stats, (order_id,))

            if stats_result:
                total_items_in_order = stats_result[0]['TOTAL'] if stats_result[0]['TOTAL'] else 0
                approved_items_in_order = stats_result[0]['APPROVED'] if stats_result[0]['APPROVED'] else 0

    # Находим запись в CT_WHDETAIL
    query_whdetail = """
        SELECT
            w.CTWHDETAILID,
            w.ISAPPROVED,
            w.DATEAPPROVED,
            w.ITEMNO
        FROM CT_WHDETAIL w
        WHERE w.CTELEMENTSID = ?
    """

    whdetail_result = db.execute_query(query_whdetail, (ctelementsid,))

    if not whdetail_result:
        return ApprovalResponse(
            success=False,
            message=f"Запись на складе для материала {itemsdetailid} не найдена",
            voice_message="Материал не найден на складе",
            product_info=None
        )

    whdetail_data = whdetail_result[0]

    # Проверяем, не приходован ли уже
    if whdetail_data['ISAPPROVED'] == 1:
        date_approved = whdetail_data['DATEAPPROVED']
        date_str = ""
        if date_approved:
            date_str = f" (приходовано {date_approved.strftime('%d.%m.%Y %H:%M')})"

        return ApprovalResponse(
            success=False,
            message=f"Материал уже был отмечен готовым{date_str}",
            voice_message="Материал уже был отмечен готовым",
            product_info=ProductInfo(
                order_number=order_number,
                proddate=proddate,
                construction_number=None,
                item_number=whdetail_data['ITEMNO'],
                orderitems_id=orderitems_id,
                orderitems_name=element_name,
                qty=None,
                element_name=element_name,
                width=width,
                height=height,
                glass_orderitems_id=None,
                order_id=order_id,
                total_items_in_order=total_items_in_order,
                approved_items_in_order=approved_items_in_order
            )
        )

    # Приходуем материал
    update_query = """
        UPDATE CT_WHDETAIL
        SET ISAPPROVED = 1,
            DATEAPPROVED = CURRENT_TIMESTAMP
        WHERE CTWHDETAILID = ?
    """

    rows_updated = db.execute_update(update_query, (whdetail_data['CTWHDETAILID'],))

    if rows_updated == 0:
        return ApprovalResponse(
            success=False,
            message="Не удалось обновить запись в базе данных",
            voice_message="Ошибка при обновлении базы данных",
            product_info=None
        )

    return ApprovalResponse(
        success=True,
        message=f"Материал {element_name} успешно оприходован!",
        voice_message=f"Материал {element_name} готов",
        product_info=ProductInfo(
            order_number=order_number,
            proddate=proddate,
            construction_number=None,
            item_number=whdetail_data['ITEMNO'],
            orderitems_id=element_data['ORDERITEMSID'],
            orderitems_name=element_name,
            qty=None,
            element_name=element_name,
            width=width,
            height=height,
            glass_orderitems_id=None,
            order_id=order_id,
            total_items_in_order=total_items_in_order,
            approved_items_in_order=approved_items_in_order
        )
    )


async def process_set_barcode(barcode_value: str) -> ApprovalResponse:
    """
    Обработка штрихкода набора (префикс S или SET)
    Поиск CT_ELEMENTS по полю ITEMSSETSID

    Args:
        barcode_value: ID набора (itemssetid)

    Returns:
        ApprovalResponse с результатом операции
    """
    try:
        itemssetid = int(barcode_value)
    except ValueError:
        return ApprovalResponse(
            success=False,
            message=f"Некорректный ID набора: {barcode_value}",
            voice_message="Ошибка. Некорректный ID набора",
            product_info=None
        )

    # Находим элементы по ITEMSSETSID
    query_elements = """
        SELECT
            e.CTELEMENTSID,
            e.RNAME as ELEMENT_NAME,
            e.WIDTH,
            e.HEIGHT,
            e.MODELID,
            e.ORDERITEMSID,
            e.ITEMSSETSID
        FROM CT_ELEMENTS e
        WHERE e.ITEMSSETSID = ?
    """

    elements_result = db.execute_query(query_elements, (itemssetid,))

    if not elements_result:
        return ApprovalResponse(
            success=False,
            message=f"Набор с ID {itemssetid} не найден",
            voice_message="Набор не найден",
            product_info=None
        )

    # Получаем записи CT_WHDETAIL для всех элементов набора
    whdetail_records = []
    for element in elements_result:
        ctelementsid = element['CTELEMENTSID']

        query_whdetail = """
            SELECT
                w.CTWHDETAILID,
                w.ISAPPROVED,
                w.DATEAPPROVED,
                w.ITEMNO,
                w.CTELEMENTSID
            FROM CT_WHDETAIL w
            WHERE w.CTELEMENTSID = ?
        """

        whdetail_result = db.execute_query(query_whdetail, (ctelementsid,))

        if whdetail_result:
            whdetail_records.extend(whdetail_result)

    if not whdetail_records:
        return ApprovalResponse(
            success=False,
            message=f"Записи на складе для набора {itemssetid} не найдены",
            voice_message="Набор не найден на складе",
            product_info=None
        )

    # Берем первый элемент для отображения информации
    first_element = elements_result[0]
    element_name = first_element['ELEMENT_NAME'].strip() if first_element['ELEMENT_NAME'] else None
    width = first_element['WIDTH']
    height = first_element['HEIGHT']
    orderitems_id = first_element['ORDERITEMSID']

    # Получаем информацию о заказе через ORDERITEMSID
    order_number = None
    proddate = None
    order_id = None
    total_items_in_order = None
    approved_items_in_order = None

    if orderitems_id:
        query_order = """
            SELECT
                o.ORDERNO,
                o.PRODDATE,
                o.ORDERID
            FROM ORDERITEMS oi
            INNER JOIN ORDERS o ON oi.ORDERID = o.ORDERID
            WHERE oi.ORDERITEMSID = ?
        """

        order_result = db.execute_query(query_order, (orderitems_id,))

        if order_result:
            order_data = order_result[0]
            order_number = order_data['ORDERNO'].strip() if order_data['ORDERNO'] else None
            proddate_obj = order_data['PRODDATE']
            if proddate_obj:
                proddate = proddate_obj.strftime('%d.%m.%Y')
            order_id = order_data['ORDERID']

            # Получаем статистику по заказу (используем CT_WHDETAIL.isapproved)
            query_stats = """
                SELECT
                    SUM(wd.qty) as TOTAL,
                    SUM(CASE WHEN wd.isapproved = 1 THEN wd.qty ELSE 0 END) as APPROVED
                FROM ORDERS o
                JOIN ORDERITEMS oi ON oi.ORDERID = o.ORDERID
                JOIN MODELS m ON m.ORDERITEMSID = oi.ORDERITEMSID
                LEFT JOIN CT_ELEMENTS el ON el.MODELID = m.MODELID
                LEFT JOIN CT_WHDETAIL wd ON wd.CTELEMENTSID = el.CTELEMENTSID
                WHERE o.ORDERID = ?
                AND el.CTTYPEELEMSID = 2
            """

            stats_result = db.execute_query(query_stats, (order_id,))

            if stats_result:
                total_items_in_order = stats_result[0]['TOTAL'] if stats_result[0]['TOTAL'] else 0
                approved_items_in_order = stats_result[0]['APPROVED'] if stats_result[0]['APPROVED'] else 0

    # Проверяем, не приходованы ли уже ВСЕ записи
    already_approved = [w for w in whdetail_records if w['ISAPPROVED'] == 1]

    if len(already_approved) == len(whdetail_records):
        first_whdetail = whdetail_records[0]
        date_approved = first_whdetail['DATEAPPROVED']
        date_str = ""
        if date_approved:
            date_str = f" (приходовано {date_approved.strftime('%d.%m.%Y %H:%M')})"

        return ApprovalResponse(
            success=False,
            message=f"Набор уже было отмечено готовым{date_str}",
            voice_message="Набор уже было отмечено готовым",
            product_info=ProductInfo(
                order_number=order_number,
                proddate=proddate,
                construction_number=None,
                item_number=None,
                orderitems_id=first_element['ORDERITEMSID'],
                orderitems_name=element_name,
                qty=len(whdetail_records),
                element_name=element_name,
                width=width,
                height=height,
                glass_orderitems_id=None,
                order_id=order_id,
                total_items_in_order=total_items_in_order,
                approved_items_in_order=approved_items_in_order
            )
        )

    # Приходуем ВСЕ элементы набора
    total_updated = 0
    for whdetail in whdetail_records:
        # Пропускаем уже приходованные
        if whdetail['ISAPPROVED'] == 1:
            continue

        update_query = """
            UPDATE CT_WHDETAIL
            SET ISAPPROVED = 1,
                DATEAPPROVED = CURRENT_TIMESTAMP
            WHERE CTWHDETAILID = ?
        """

        rows_updated = db.execute_update(update_query, (whdetail['CTWHDETAILID'],))
        total_updated += rows_updated

    if total_updated == 0:
        return ApprovalResponse(
            success=False,
            message="Не удалось обновить записи в базе данных",
            voice_message="Ошибка при обновлении базы данных",
            product_info=None
        )

    message = f"Успешно оприходовано {total_updated} элемент(ов) набора"
    if total_updated < len(whdetail_records):
        already_count = len(whdetail_records) - total_updated
        message += f" ({already_count} уже было приходовано ранее)"

    return ApprovalResponse(
        success=True,
        message=message,
        voice_message=f"Набор {element_name} готов",
        product_info=ProductInfo(
            order_number=order_number,
            proddate=proddate,
            construction_number=None,
            item_number=None,
            orderitems_id=first_element['ORDERITEMSID'],
            orderitems_name=element_name,
            qty=len(whdetail_records),
            element_name=element_name,
            width=width,
            height=height,
            glass_orderitems_id=None,
            order_id=order_id,
            total_items_in_order=total_items_in_order,
            approved_items_in_order=approved_items_in_order
        )
    )


async def process_izd_barcode(barcode_value: str) -> ApprovalResponse:
    """
    Обработка штрихкода изделия (префикс D, IZD или старый формат 9 цифр)

    Формат: [номер изделия (2 цифры)][ORDERITEMSID стеклопакета (7 цифр)]
    - Первые 2 цифры - номер изделия (01, 02, ... 15...)
    - Остальные 7 цифр - ORDERITEMSID стеклопакета (заполнения)

    Args:
        barcode_value: 9 цифр штрихкода изделия

    Returns:
        ApprovalResponse с результатом операции
    """
    # Валидация: должно быть 9 цифр
    if not barcode_value.isdigit() or len(barcode_value) != 9:
        return ApprovalResponse(
            success=False,
            message=f"Некорректный штрихкод изделия: {barcode_value}. Ожидается 9 цифр",
            voice_message="Ошибка. Некорректный штрихкод изделия",
            product_info=None
        )

    # Парсим штрихкод
    item_number = int(barcode_value[:2])  # Первые 2 цифры - номер изделия
    glass_orderitems_id = int(barcode_value[2:])  # Остальные 7 цифр - ORDERITEMSID стеклопакета

    # 1. Находим ORDERITEMS стеклопакета по его ID
    query_glass = """
        SELECT
            oi.ORDERITEMSID,
            oi.NAME as GLASS_NAME,
            oi.ORDERID,
            o.ORDERNO,
            o.PRODDATE
        FROM ORDERITEMS oi
        INNER JOIN ORDERS o ON oi.ORDERID = o.ORDERID
        WHERE oi.ORDERITEMSID = ?
    """

    glass_result = db.execute_query(query_glass, (glass_orderitems_id,))

    if not glass_result:
        return ApprovalResponse(
            success=False,
            message=f"Стеклопакет с ID {glass_orderitems_id} не найден в базе данных",
            voice_message="Стеклопакет не найден в базе данных",
            product_info=None
        )

    glass_data = glass_result[0]
    glass_name = glass_data['GLASS_NAME'].strip() if glass_data['GLASS_NAME'] else ""

    # 2. Парсим NAME стеклопакета: "19686 / 01 / С-1 [G 2 665]"
    # Формат: [номер заказа] / [номер изделия] / [проём] [...]
    if not glass_name or '/' not in glass_name:
        return ApprovalResponse(
            success=False,
            message=f"Некорректный формат имени стеклопакета: {glass_name}",
            voice_message="Ошибка. Некорректный формат имени стеклопакета",
            product_info=None
        )

    parts = glass_name.split('/')
    if len(parts) < 2:
        return ApprovalResponse(
            success=False,
            message=f"Не удалось распарсить имя стеклопакета: {glass_name}",
            voice_message="Ошибка парсинга имени стеклопакета",
            product_info=None
        )

    order_name = parts[0].strip()  # "19686"
    construction_number = parts[1].strip()  # "01"

    # 3. Находим ORDERITEMSID изделия по названию заказа и номеру конструкции
    query_product = """
        SELECT
            oi.ORDERITEMSID,
            oi.NAME as PRODUCT_NAME,
            oi.QTY,
            o.ORDERNO,
            o.ORDERID,
            o.PRODDATE
        FROM ORDERITEMS oi
        INNER JOIN ORDERS o ON oi.ORDERID = o.ORDERID
        WHERE o.ORDERNO = ? AND oi.NAME = ?
    """

    product_result = db.execute_query(query_product, (order_name, construction_number))

    if not product_result:
        return ApprovalResponse(
            success=False,
            message=f"Изделие {construction_number} заказа №{order_name} не найдено",
            voice_message=f"Изделие {construction_number} заказа №{order_name} не найдено",
            product_info=None
        )

    product_data = product_result[0]
    orderitems_id = product_data['ORDERITEMSID']
    order_number = product_data['ORDERNO'].strip() if product_data['ORDERNO'] else "?"
    orderitem_qty = product_data['QTY']
    order_id = product_data['ORDERID']

    # Форматируем дату производства
    proddate_raw = product_data.get('PRODDATE')
    proddate = None
    if proddate_raw:
        if isinstance(proddate_raw, datetime):
            proddate = proddate_raw.strftime('%d.%m.%Y')
        elif hasattr(proddate_raw, 'strftime'):
            proddate = proddate_raw.strftime('%d.%m.%Y')
        else:
            proddate = str(proddate_raw)

    # Проверяем, что номер изделия не превышает количество
    if item_number > orderitem_qty:
        return ApprovalResponse(
            success=False,
            message=f"Номер изделия {item_number} превышает количество {orderitem_qty}",
            voice_message=f"Ошибка. Номер изделия {item_number} превышает количество {orderitem_qty}",
            product_info=None
        )

    # 4. Находим ВСЕ модели для данного ORDERITEMSID
    query_models = """
        SELECT MODELID, MODELNO
        FROM MODELS
        WHERE ORDERITEMSID = ?
        ORDER BY MODELNO
    """

    models_result = db.execute_query(query_models, (orderitems_id,))

    if not models_result:
        return ApprovalResponse(
            success=False,
            message=f"Модели для изделия {construction_number} заказа №{order_number} не найдены",
            voice_message=f"Модели для изделия {construction_number} заказа №{order_number} не найдены",
            product_info=None
        )

    # 5. Для каждой модели находим CT_ELEMENTS и CT_WHDETAIL с нужным ITEMNO
    whdetail_records = []
    for model in models_result:
        model_id = model['MODELID']

        query_whdetail = """
            SELECT
                w.CTWHDETAILID,
                w.CTELEMENTSID,
                w.ITEMNO,
                w.ISAPPROVED,
                w.USERAPPROVED,
                w.DATEAPPROVED,
                e.RNAME as ELEMENT_NAME,
                e.WIDTH,
                e.HEIGHT,
                e.MODELID
            FROM CT_WHDETAIL w
            INNER JOIN CT_ELEMENTS e ON w.CTELEMENTSID = e.CTELEMENTSID
            WHERE e.MODELID = ? AND w.ITEMNO = ? AND e.CTTYPEELEMSID = 2
        """

        whdetail_result = db.execute_query(query_whdetail, (model_id, item_number))

        if whdetail_result:
            whdetail_records.extend(whdetail_result)

    if not whdetail_records:
        return ApprovalResponse(
            success=False,
            message=f"Изделие {construction_number} заказа №{order_number} не найдено на складе",
            voice_message=f"Изделие {construction_number} заказа №{order_number} не найдено на складе",
            product_info=None
        )

    # Берем данные из первой записи для информации
    whdetail_data = whdetail_records[0]
    element_name = whdetail_data['ELEMENT_NAME'].strip() if whdetail_data['ELEMENT_NAME'] else None
    width = whdetail_data['WIDTH']
    height = whdetail_data['HEIGHT']

    # 6. Проверяем, не приходованы ли уже ВСЕ записи
    already_approved = [w for w in whdetail_records if w['ISAPPROVED'] == 1]

    if len(already_approved) == len(whdetail_records):
        date_approved = whdetail_data['DATEAPPROVED']
        date_str = ""
        if date_approved:
            date_str = f" (приходовано {date_approved.strftime('%d.%m.%Y %H:%M')})"

        # Получаем статистику по заказу для уже приходованного изделия
        query_total_items = """
            SELECT SUM(wd.qty) as TOTAL
            FROM ORDERS o
            JOIN ORDERITEMS oi ON oi.ORDERID = o.ORDERID
            JOIN MODELS m ON m.ORDERITEMSID = oi.ORDERITEMSID
            LEFT JOIN CT_ELEMENTS el ON el.MODELID = m.MODELID
            LEFT JOIN CT_WHDETAIL wd ON wd.CTELEMENTSID = el.CTELEMENTSID
            WHERE o.ORDERID = ?
            AND el.CTTYPEELEMSID = 2
        """

        query_approved_items = """
            SELECT SUM(wd.qty) as APPROVED
            FROM ORDERS o
            JOIN ORDERITEMS oi ON oi.ORDERID = o.ORDERID
            JOIN MODELS m ON m.ORDERITEMSID = oi.ORDERITEMSID
            LEFT JOIN CT_ELEMENTS el ON el.MODELID = m.MODELID
            LEFT JOIN CT_WHDETAIL wd ON wd.CTELEMENTSID = el.CTELEMENTSID
            WHERE o.ORDERID = ?
            AND el.CTTYPEELEMSID = 2
            AND wd.ISAPPROVED = 1
        """

        total_items_result = db.execute_query(query_total_items, (order_id,))
        approved_items_result = db.execute_query(query_approved_items, (order_id,))

        total_items_in_order = total_items_result[0]['TOTAL'] if total_items_result and total_items_result[0]['TOTAL'] else 0
        approved_items_in_order = approved_items_result[0]['APPROVED'] if approved_items_result and approved_items_result[0]['APPROVED'] else 0

        return ApprovalResponse(
            success=False,
            message=f"Изделие уже было отмечено готовым{date_str}",
            voice_message="Изделие уже было отмечено готовым",
            product_info=ProductInfo(
                order_number=order_number,
                proddate=proddate,
                construction_number=construction_number,
                item_number=item_number,
                orderitems_id=orderitems_id,
                orderitems_name=construction_number,
                qty=orderitem_qty,
                element_name=element_name,
                width=width,
                height=height,
                glass_orderitems_id=glass_orderitems_id,
                order_id=order_id,
                total_items_in_order=total_items_in_order,
                approved_items_in_order=approved_items_in_order
            )
        )

    # 7. Приходуем ВСЕ изделия - обновляем CT_WHDETAIL для всех моделей
    total_updated = 0
    for whdetail in whdetail_records:
        # Пропускаем уже приходованные
        if whdetail['ISAPPROVED'] == 1:
            continue

        update_query = """
            UPDATE CT_WHDETAIL
            SET ISAPPROVED = 1,
                DATEAPPROVED = CURRENT_TIMESTAMP
            WHERE CTWHDETAILID = ?
        """

        rows_updated = db.execute_update(update_query, (whdetail['CTWHDETAILID'],))
        total_updated += rows_updated

    if total_updated == 0:
        return ApprovalResponse(
            success=False,
            message="Не удалось обновить записи в базе данных",
            voice_message="Ошибка при обновлении базы данных",
            product_info=None
        )

    # 8. Получаем статистику по заказу И проверяем готовность (ПОСЛЕ проводки)
    # Объединяем все проверки в один запрос для оптимизации
    order_id = product_data['ORDERID']

    # Единый запрос для получения статистики и проверки готовности заказа
    query_order_stats = """
        SELECT
            SUM(wd.qty) as TOTAL,
            SUM(CASE WHEN wd.isapproved = 1 THEN wd.qty ELSE 0 END) as APPROVED,
            COUNT(CASE WHEN wd.isapproved = 0 THEN 1 END) as NOT_APPROVED_COUNT
        FROM ORDERS o
        JOIN ORDERITEMS oi ON oi.ORDERID = o.ORDERID
        JOIN MODELS m ON m.ORDERITEMSID = oi.ORDERITEMSID
        LEFT JOIN CT_ELEMENTS el ON el.MODELID = m.MODELID
        LEFT JOIN CT_WHDETAIL wd ON wd.CTELEMENTSID = el.CTELEMENTSID
        WHERE o.ORDERID = ?
        AND el.CTTYPEELEMSID = 2
    """

    stats_result = db.execute_query(query_order_stats, (order_id,))

    total_items_in_order = stats_result[0]['TOTAL'] if stats_result and stats_result[0]['TOTAL'] else 0
    approved_items_in_order = stats_result[0]['APPROVED'] if stats_result and stats_result[0]['APPROVED'] else 0
    not_approved_count = stats_result[0]['NOT_APPROVED_COUNT'] if stats_result and stats_result[0]['NOT_APPROVED_COUNT'] else 0

    # 9. Проверяем, не готов ли теперь весь заказ
    # Если NOT_APPROVED_COUNT = 0, значит все изделия готовы
    all_approved = (not_approved_count == 0)
    has_items = (total_items_in_order > 0)

    # Если все изделия готовы, устанавливаем статус "Completed" (ID = 4)
    if all_approved and has_items:
        try:
            # Проверяем текущее состояние заказа
            current_state_query = """
                SELECT orderstateid FROM orders WHERE orderid = ?
            """
            current_state = db.execute_query(current_state_query, (order_id,))
            current_orderstateid = current_state[0]['ORDERSTATEID'] if current_state else None

            # Устанавливаем статус только если он еще не "Completed" (4)
            if current_orderstateid != 4:
                # Получаем максимальную позицию состояния для данного заказа
                get_max_posit_query = """
                    SELECT MAX(stateposit) as MAXPOSIT
                    FROM orderstatesreg
                    WHERE orderid = ?
                """
                max_posit_result = db.execute_query(get_max_posit_query, (order_id,))
                next_posit = (max_posit_result[0]['MAXPOSIT'] or 0) + 1

                # Добавляем запись в ORDERSTATESREG, используя генератор для ID
                # EMPID = 8 (как в примере из базы, "Скрипт sChangeState")
                insert_state_query = """
                    INSERT INTO orderstatesreg
                    (orderstatesregid, orderid, orderstateid, empid, changedate, stateposit, rcomment)
                    VALUES (GEN_ID(GEN_ORDERSTATESREG, 1), ?, 4, 8, CURRENT_TIMESTAMP, ?, 'Автоматическая установка статуса после штрихкодирования')
                """
                db.execute_update(insert_state_query, (order_id, next_posit))

                # Обновляем состояние заказа
                update_order_state_query = """
                    UPDATE orders
                    SET orderstateid = 4
                    WHERE orderid = ?
                """
                db.execute_update(update_order_state_query, (order_id,))

                print(f"[OK] Заказ {order_number} (ID={order_id}) автоматически переведен в статус 'Готов'")
        except Exception as e:
            # Логируем ошибку, но не прерываем основной процесс
            print(f"[ERROR] Ошибка при установке статуса 'Готов' для заказа {order_number}: {e}")

    # 10. Формируем успешный ответ
    models_count = len(models_result)
    voice_message = f"Изделие {construction_number} заказа {order_number} готово"

    message = f"Успешно оприходовано {total_updated} изделие(й) из {models_count} модели(ей)"
    if total_updated < len(whdetail_records):
        already_count = len(whdetail_records) - total_updated
        message += f" ({already_count} уже было приходовано ранее)"

    # Если заказ полностью готов, добавляем это в сообщение
    if all_approved and has_items:
        message += f". ЗАКАЗ {order_number} ПОЛНОСТЬЮ ГОТОВ!"
        voice_message = f"Заказ {order_number} полностью готов!"

    return ApprovalResponse(
        success=True,
        message=message,
        voice_message=voice_message,
        product_info=ProductInfo(
            order_number=order_number,
            proddate=proddate,
            construction_number=construction_number,
            item_number=item_number,
            orderitems_id=orderitems_id,
            orderitems_name=construction_number,
            qty=orderitem_qty,
            element_name=element_name,
            width=width,
            height=height,
            glass_orderitems_id=glass_orderitems_id,
            order_id=order_id,
            total_items_in_order=total_items_in_order,
            approved_items_in_order=approved_items_in_order
        )
    )


async def process_order_barcode(barcode: str) -> ApprovalResponse:
    """
    Обработка штрихкода заказа для перевода в статус "Отгружен"

    Args:
        barcode: ORDERID заказа

    Returns:
        ApprovalResponse с результатом операции
    """
    try:
        order_id = int(barcode)
    except ValueError:
        return ApprovalResponse(
            success=False,
            message=f"Некорректный штрихкод заказа: {barcode}",
            voice_message="Ошибка. Некорректный штрихкод заказа",
            product_info=None
        )

    # Проверяем существование заказа и его текущий статус
    query_order = """
        SELECT
            o.ORDERID,
            o.ORDERNO,
            o.ORDERSTATEID,
            os.NAME as STATE_NAME
        FROM ORDERS o
        LEFT JOIN ORDERSTATES os ON os.ORDERSTATEID = o.ORDERSTATEID
        WHERE o.ORDERID = ?
    """

    order_result = db.execute_query(query_order, (order_id,))

    if not order_result:
        return ApprovalResponse(
            success=False,
            message=f"Заказ с ID {order_id} не найден",
            voice_message="Заказ не найден",
            product_info=None
        )

    order_data = order_result[0]
    order_number = order_data['ORDERNO'].strip() if order_data['ORDERNO'] else "?"
    current_state_id = order_data['ORDERSTATEID']
    current_state_name = order_data['STATE_NAME'].strip() if order_data['STATE_NAME'] else "Неизвестно"

    # Проверяем, что заказ в статусе "Готов" (ID=4)
    if current_state_id != 4:
        return ApprovalResponse(
            success=False,
            message=f"Заказ {order_number} в статусе '{current_state_name}'. Можно отгружать только заказы со статусом 'Готов'",
            voice_message=f"Ошибка. Заказ {order_number} не готов к отгрузке",
            product_info=None
        )

    # Переводим заказ в статус "Отгружен" (ID=5)
    try:
        # Получаем максимальную позицию состояния для данного заказа
        get_max_posit_query = """
            SELECT MAX(stateposit) as MAXPOSIT
            FROM orderstatesreg
            WHERE orderid = ?
        """
        max_posit_result = db.execute_query(get_max_posit_query, (order_id,))
        next_posit = (max_posit_result[0]['MAXPOSIT'] or 0) + 1

        # Добавляем запись в ORDERSTATESREG, используя генератор для ID
        # EMPID = 8 (как в примере из базы, "Скрипт sChangeState")
        insert_state_query = """
            INSERT INTO orderstatesreg
            (orderstatesregid, orderid, orderstateid, empid, changedate, stateposit, rcomment)
            VALUES (GEN_ID(GEN_ORDERSTATESREG, 1), ?, 5, 8, CURRENT_TIMESTAMP, ?, 'Автоматическая установка статуса "Отгружен" после сканирования штрихкода заказа')
        """
        db.execute_update(insert_state_query, (order_id, next_posit))

        # Обновляем состояние заказа
        update_order_state_query = """
            UPDATE orders
            SET orderstateid = 5
            WHERE orderid = ?
        """
        db.execute_update(update_order_state_query, (order_id,))

        print(f"[OK] Заказ {order_number} (ID={order_id}) переведен в статус 'Отгружен'")

        return ApprovalResponse(
            success=True,
            message=f"Заказ {order_number} успешно отгружен!",
            voice_message=f"Заказ {order_number} отгружен",
            product_info=ProductInfo(
                order_number=order_number,
                proddate=None,
                construction_number=None,
                item_number=None,
                orderitems_id=None,
                orderitems_name=None,
                qty=None,
                element_name=None,
                width=None,
                height=None,
                glass_orderitems_id=None,
                order_id=order_id,
                total_items_in_order=None,
                approved_items_in_order=None
            )
        )

    except Exception as e:
        print(f"[ERROR] Ошибка при установке статуса 'Отгружен' для заказа {order_number}: {e}")
        return ApprovalResponse(
            success=False,
            message=f"Ошибка при отгрузке заказа: {str(e)}",
            voice_message="Ошибка при отгрузке заказа",
            product_info=None
        )


@app.get("/", response_model=HealthResponse)
async def health_check():
    """Проверка работоспособности API и подключения к БД"""
    try:
        print(f"Попытка подключения к БД: {settings.DB_HOST}:{settings.DB_PORT}")
        print(f"База данных: {settings.DB_DATABASE}")

        # Проверяем подключение к БД
        result = db.execute_query("SELECT 1 FROM RDB$DATABASE")
        db_connected = len(result) > 0

        print(f"[OK] Подключение к БД успешно, результат: {result}")

        return HealthResponse(
            status="ok" if db_connected else "error",
            database_connected=db_connected,
            api_version=app.version
        )
    except Exception as e:
        print(f"[ERROR] Ошибка подключения к БД: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

        return HealthResponse(
            status="error",
            database_connected=False,
            api_version=app.version
        )


@app.post("/api/process-barcode", response_model=ApprovalResponse)
async def process_barcode(request: BarcodeRequest):
    """
    Обработка штрихкода и приходование изделия

    Поддерживаемые форматы:
    1. D-123456789: Штрихкод изделия (9 цифр после префикса)
       - Первые 2 цифры: номер изделия (01, 02, ...)
       - Остальные 7 цифр: ORDERITEMSID стеклопакета

    2. ORD-12345: Штрихкод заказа (ID заказа)
       - Переводит заказ из статуса "Готов" в статус "Отгружен"

    3. T-12345: Штрихкод материала (ID материала - itemsdetailid)
       - Поиск CT_ELEMENTS по полю ITEMSDETAILID

    4. S-12345: Штрихкод набора (ID набора - itemssetid)
       - Поиск CT_ELEMENTS по полю ITEMSSETSID

    Старые форматы (обратная совместимость):
    - IZD-123456789, ITM-12345, SET-12345 (старые префиксы)
    - 123456789 (9 цифр): обрабатывается как D-123456789
    - 12345 (не 9 цифр): обрабатывается как ORD-12345
    """
    try:
        barcode = request.barcode.strip()

        # Парсим штрихкод и определяем тип
        barcode_info = parse_barcode(barcode)
        barcode_type = barcode_info['type']
        barcode_value = barcode_info['value']

        print(f"[INFO] Обработка штрихкода: type={barcode_type}, value={barcode_value}")

        # Маршрутизация по типу штрихкода
        if barcode_type == 'IZD' or barcode_type == 'LEGACY_IZD':
            return await process_izd_barcode(barcode_value)

        elif barcode_type == 'ORD' or barcode_type == 'LEGACY_ORD':
            return await process_order_barcode(barcode_value)

        elif barcode_type == 'ITM':
            return await process_itm_barcode(barcode_value)

        elif barcode_type == 'SET':
            return await process_set_barcode(barcode_value)

        else:  # UNKNOWN
            return ApprovalResponse(
                success=False,
                message=f"Неизвестный формат штрихкода: {barcode}",
                voice_message="Ошибка. Неизвестный формат штрихкода",
                product_info=None
            )
        
    except ValueError as e:
        return ApprovalResponse(
            success=False,
            message=f"Ошибка обработки штрихкода: {str(e)}",
            voice_message="Ошибка обработки штрихкода",
            product_info=None
        )
    except fdb.DatabaseError as e:
        return ApprovalResponse(
            success=False,
            message=f"Ошибка базы данных: {str(e)}",
            voice_message="Ошибка базы данных",
            product_info=None
        )
    except Exception as e:
        return ApprovalResponse(
            success=False,
            message=f"Неизвестная ошибка: {str(e)}",
            voice_message="Неизвестная ошибка",
            product_info=None
        )


@app.get("/api/statistics/daily", response_model=DailyStatsResponse)
async def get_daily_statistics(
    start_date: str = Query(..., description="Начальная дата (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Конечная дата (YYYY-MM-DD)")
):
    """
    Получить общую статистику по дням

    Возвращает запланированные и изготовленные изделия (ПВХ и раздвижки)
    группированные по датам производства
    """
    try:
        # Валидация дат
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return DailyStatsResponse(
                success=False,
                message="Неверный формат даты. Используйте YYYY-MM-DD",
                data=[]
            )

        if start_dt > end_dt:
            return DailyStatsResponse(
                success=False,
                message="Начальная дата не может быть больше конечной",
                data=[]
            )

        # Ограничение диапазона
        delta = (end_dt - start_dt).days
        if delta > 365:
            return DailyStatsResponse(
                success=False,
                message="Диапазон не может превышать 1 год",
                data=[]
            )

        # Объединенный SQL запрос
        query = """
            SELECT
                o.proddate,
                o.orderno,
                o.rcomment,
                SUM(CASE
                    WHEN rs.systemtype = 0 AND rs.rsystemid <> 8 AND rs.rsystemid <> 27
                    THEN 1 ELSE 0
                END) AS planned_pvh,
                SUM(CASE
                    WHEN (rs.systemtype = 1) OR (rs.rsystemid = 8)
                    THEN 1 ELSE 0
                END) AS planned_razdv,
                SUM(CASE
                    WHEN rs.rsystemid = 28
                    THEN 1 ELSE 0
                END) AS planned_glass,
                SUM(CASE
                    WHEN rs.systemtype = 0 AND rs.rsystemid <> 8 AND rs.rsystemid <> 27 AND wd.isapproved = 1
                    THEN 1 ELSE 0
                END) AS completed_pvh,
                SUM(CASE
                    WHEN ((rs.systemtype = 1) OR (rs.rsystemid = 8)) AND wd.isapproved = 1
                    THEN 1 ELSE 0
                END) AS completed_razdv,
                SUM(CASE
                    WHEN rs.rsystemid = 28 AND wd.isapproved = 1
                    THEN 1 ELSE 0
                END) AS completed_glass
            FROM orders o
            JOIN orderitems oi ON oi.orderid = o.orderid
            JOIN models m ON m.orderitemsid = oi.orderitemsid
            JOIN r_systems rs ON rs.rsystemid = m.sysprofid
            LEFT JOIN ct_elements el ON el.modelid = m.modelid AND el.cttypeelemsid = 2
            LEFT JOIN ct_whdetail wd ON wd.ctelementsid = el.ctelementsid
            WHERE o.proddate BETWEEN ? AND ?
            GROUP BY o.proddate, o.orderno, o.rcomment
            ORDER BY o.proddate, o.orderno
        """

        results = db.execute_query(query, (start_date, end_date))

        # Агрегация по датам
        daily_dict = {}
        for row in results:
            proddate = row['PRODDATE']
            if isinstance(proddate, datetime):
                proddate = proddate.date().strftime('%Y-%m-%d')
            elif hasattr(proddate, 'strftime'):
                proddate = proddate.strftime('%Y-%m-%d')
            else:
                proddate = str(proddate)

            if proddate not in daily_dict:
                daily_dict[proddate] = {
                    'planned_pvh': 0,
                    'planned_razdv': 0,
                    'planned_glass': 0,
                    'completed_pvh': 0,
                    'completed_razdv': 0,
                    'completed_glass': 0
                }

            daily_dict[proddate]['planned_pvh'] += row.get('PLANNED_PVH', 0) or 0
            daily_dict[proddate]['planned_razdv'] += row.get('PLANNED_RAZDV', 0) or 0
            daily_dict[proddate]['planned_glass'] += row.get('PLANNED_GLASS', 0) or 0
            daily_dict[proddate]['completed_pvh'] += row.get('COMPLETED_PVH', 0) or 0
            daily_dict[proddate]['completed_razdv'] += row.get('COMPLETED_RAZDV', 0) or 0
            daily_dict[proddate]['completed_glass'] += row.get('COMPLETED_GLASS', 0) or 0

        # Преобразование в список
        daily_stats = [
            DailyStatsRow(
                proddate=date,
                planned_pvh=stats['planned_pvh'],
                planned_razdv=stats['planned_razdv'],
                planned_glass=stats['planned_glass'],
                completed_pvh=stats['completed_pvh'],
                completed_razdv=stats['completed_razdv'],
                completed_glass=stats['completed_glass']
            )
            for date, stats in sorted(daily_dict.items())
        ]

        return DailyStatsResponse(
            success=True,
            message=f"Статистика по {len(daily_stats)} дням успешно получена",
            data=daily_stats
        )

    except fdb.DatabaseError as e:
        return DailyStatsResponse(
            success=False,
            message=f"Ошибка базы данных: {str(e)}",
            data=[]
        )
    except Exception as e:
        return DailyStatsResponse(
            success=False,
            message=f"Неизвестная ошибка: {str(e)}",
            data=[]
        )


@app.get("/api/statistics/orders", response_model=OrderStatsResponse)
async def get_order_statistics(
    start_date: str = Query(..., description="Начальная дата (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Конечная дата (YYYY-MM-DD)")
):
    """
    Получить детальную статистику по заказам

    Возвращает запланированные и изготовленные изделия (ПВХ и раздвижки)
    группированные по заказам с комментариями
    """
    try:
        # Валидация дат
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return OrderStatsResponse(
                success=False,
                message="Неверный формат даты. Используйте YYYY-MM-DD",
                data=[]
            )

        if start_dt > end_dt:
            return OrderStatsResponse(
                success=False,
                message="Начальная дата не может быть больше конечной",
                data=[]
            )

        # Ограничение диапазона
        delta = (end_dt - start_dt).days
        if delta > 365:
            return OrderStatsResponse(
                success=False,
                message="Диапазон не может превышать 1 год",
                data=[]
            )

        # Объединенный SQL запрос (тот же что и для daily)
        query = """
            SELECT
                o.proddate,
                o.orderno,
                o.rcomment,
                SUM(CASE
                    WHEN rs.systemtype = 0 AND rs.rsystemid <> 8 AND rs.rsystemid <> 27
                    THEN 1 ELSE 0
                END) AS planned_pvh,
                SUM(CASE
                    WHEN (rs.systemtype = 1) OR (rs.rsystemid = 8)
                    THEN 1 ELSE 0
                END) AS planned_razdv,
                SUM(CASE
                    WHEN rs.rsystemid = 28
                    THEN 1 ELSE 0
                END) AS planned_glass,
                SUM(CASE
                    WHEN rs.systemtype = 0 AND rs.rsystemid <> 8 AND rs.rsystemid <> 27 AND wd.isapproved = 1
                    THEN 1 ELSE 0
                END) AS completed_pvh,
                SUM(CASE
                    WHEN ((rs.systemtype = 1) OR (rs.rsystemid = 8)) AND wd.isapproved = 1
                    THEN 1 ELSE 0
                END) AS completed_razdv,
                SUM(CASE
                    WHEN rs.rsystemid = 28 AND wd.isapproved = 1
                    THEN 1 ELSE 0
                END) AS completed_glass
            FROM orders o
            JOIN orderitems oi ON oi.orderid = o.orderid
            JOIN models m ON m.orderitemsid = oi.orderitemsid
            JOIN r_systems rs ON rs.rsystemid = m.sysprofid
            LEFT JOIN ct_elements el ON el.modelid = m.modelid AND el.cttypeelemsid = 2
            LEFT JOIN ct_whdetail wd ON wd.ctelementsid = el.ctelementsid
            WHERE o.proddate BETWEEN ? AND ?
            GROUP BY o.proddate, o.orderno, o.rcomment
            ORDER BY o.proddate, o.orderno
        """

        results = db.execute_query(query, (start_date, end_date))

        # Преобразование результатов
        order_stats = []
        for row in results:
            proddate = row['PRODDATE']
            if isinstance(proddate, datetime):
                proddate = proddate.date().strftime('%Y-%m-%d')
            elif hasattr(proddate, 'strftime'):
                proddate = proddate.strftime('%Y-%m-%d')
            else:
                proddate = str(proddate)

            orderno = row['ORDERNO'].strip() if row['ORDERNO'] else ""
            rcomment = row['RCOMMENT'].strip() if row['RCOMMENT'] else None

            order_stats.append(OrderStatsRow(
                order_number=orderno,
                proddate=proddate,
                planned_pvh=row.get('PLANNED_PVH', 0) or 0,
                planned_razdv=row.get('PLANNED_RAZDV', 0) or 0,
                planned_glass=row.get('PLANNED_GLASS', 0) or 0,
                completed_pvh=row.get('COMPLETED_PVH', 0) or 0,
                completed_razdv=row.get('COMPLETED_RAZDV', 0) or 0,
                completed_glass=row.get('COMPLETED_GLASS', 0) or 0,
                comment=rcomment
            ))

        return OrderStatsResponse(
            success=True,
            message=f"Статистика по {len(order_stats)} заказам успешно получена",
            data=order_stats
        )

    except fdb.DatabaseError as e:
        return OrderStatsResponse(
            success=False,
            message=f"Ошибка базы данных: {str(e)}",
            data=[]
        )
    except Exception as e:
        return OrderStatsResponse(
            success=False,
            message=f"Неизвестная ошибка: {str(e)}",
            data=[]
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info"
    )

