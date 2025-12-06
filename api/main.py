"""
API сервер для системы учета готовности изделий
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import fdb

from models import BarcodeRequest, ApprovalResponse, ProductInfo, HealthResponse
from database import db
from config import settings


app = FastAPI(
    title="Barcode Approval API",
    description="API для приходования изделий по штрихкоду",
    version="1.1.0"  # Увеличена версия (добавлены поля total_items_in_order и approved_items_in_order)
)

# CORS middleware для возможности обращения с клиента
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

        print(f"✓ Подключение к БД успешно, результат: {result}")

        return HealthResponse(
            status="ok" if db_connected else "error",
            database_connected=db_connected,
            api_version=app.version
        )
    except Exception as e:
        print(f"✗ Ошибка подключения к БД: {type(e).__name__}: {e}")
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
    
    Формат штрихкода: [номер изделия (2 цифры)][ORDERITEMSID стеклопакета (7 цифр)]
    - Первые 2 цифры - номер изделия (01, 02, ... 15...)
    - Остальные 7 цифр - ORDERITEMSID стеклопакета (заполнения)
    """
    try:
        barcode = request.barcode.strip()
        
        # Валидация штрихкода
        if not barcode or not barcode.isdigit():
            return ApprovalResponse(
                success=False,
                message="Неверный формат штрихкода",
                voice_message="Ошибка. Неверный формат штрихкода",
                product_info=None
            )
        
        if len(barcode) != 9:
            return ApprovalResponse(
                success=False,
                message=f"Штрихкод должен содержать 9 цифр (получено: {len(barcode)})",
                voice_message="Ошибка. Неверная длина штрихкода",
                product_info=None
            )
        
        # Парсим штрихкод
        item_number = int(barcode[:2])  # Первые 2 цифры - номер изделия
        glass_orderitems_id = int(barcode[2:])  # Остальные 7 цифр - ORDERITEMSID стеклопакета
        
        # 1. Находим ORDERITEMS стеклопакета по его ID
        query_glass = """
            SELECT 
                oi.ORDERITEMSID,
                oi.NAME as GLASS_NAME,
                oi.ORDERID,
                o.ORDERNO
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
                o.ORDERID
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
            order_id = product_data['ORDERID']

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

        # 8. Получаем статистику по заказу (ПОСЛЕ проводки)
        order_id = product_data['ORDERID']

        # Запрос для получения общего количества изделий в заказе
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

        # Запрос для получения количества проведенных изделий в заказе
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

        # 9. Формируем успешный ответ
        models_count = len(models_result)
        voice_message = f"Изделие {construction_number} заказа {order_number} готово"

        message = f"Успешно оприходовано {total_updated} изделие(й) из {models_count} модели(ей)"
        if total_updated < len(whdetail_records):
            already_count = len(whdetail_records) - total_updated
            message += f" ({already_count} уже было приходовано ранее)"

        return ApprovalResponse(
            success=True,
            message=message,
            voice_message=voice_message,
            product_info=ProductInfo(
                order_number=order_number,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info"
    )

