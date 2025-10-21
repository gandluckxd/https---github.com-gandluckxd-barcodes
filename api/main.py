"""
API сервер для системы учета готовности изделий
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import fdb

from models import BarcodeRequest, ApprovalResponse, ProductInfo, HealthResponse
from database import db
from config import settings


app = FastAPI(
    title="Barcode Approval API",
    description="API для приходования изделий по штрихкоду",
    version="1.0.0"
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
        # Проверяем подключение к БД
        result = db.execute_query("SELECT 1 FROM RDB$DATABASE")
        db_connected = len(result) > 0
        
        return HealthResponse(
            status="ok" if db_connected else "error",
            database_connected=db_connected
        )
    except Exception as e:
        return HealthResponse(
            status="error",
            database_connected=False
        )


@app.post("/api/process-barcode", response_model=ApprovalResponse)
async def process_barcode(request: BarcodeRequest):
    """
    Обработка штрихкода и приходование изделия
    
    Формат штрихкода: [номер изделия][grordersdetailid]
    - Первая цифра - номер изделия (1, 2, 3...)
    - Остальные цифры - GRORDERSDETAILID
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
        
        if len(barcode) < 2:
            return ApprovalResponse(
                success=False,
                message="Штрихкод слишком короткий",
                voice_message="Ошибка. Штрихкод слишком короткий",
                product_info=None
            )
        
        # Парсим штрихкод
        item_number = int(barcode[0])  # Первая цифра - номер изделия
        grordersdetail_id = int(barcode[1:])  # Остальное - GRORDERSDETAILID
        
        # 1. Находим ORDERITEMSID по GRORDERSDETAILID
        query_grorders = """
            SELECT 
                d.GRORDERDETAILID,
                d.ORDERITEMSID,
                d.QTY,
                oi.NAME as ORDERITEM_NAME,
                oi.QTY as ORDERITEM_QTY,
                o.ORDERNO,
                o.ORDERID
            FROM GRORDERSDETAIL d
            INNER JOIN ORDERITEMS oi ON d.ORDERITEMSID = oi.ORDERITEMSID
            INNER JOIN ORDERS o ON oi.ORDERID = o.ORDERID
            WHERE d.GRORDERDETAILID = ?
        """
        
        grorders_result = db.execute_query(query_grorders, (grordersdetail_id,))
        
        if not grorders_result:
            return ApprovalResponse(
                success=False,
                message=f"Изделие с ID {grordersdetail_id} не найдено в базе данных",
                voice_message="Изделие не найдено в базе данных",
                product_info=None
            )
        
        grorder_data = grorders_result[0]
        orderitems_id = grorder_data['ORDERITEMSID']
        order_number = grorder_data['ORDERNO'].strip() if grorder_data['ORDERNO'] else "?"
        construction_number = grorder_data['ORDERITEM_NAME'].strip() if grorder_data['ORDERITEM_NAME'] else "?"
        orderitem_qty = grorder_data['ORDERITEM_QTY']
        
        # Проверяем, что номер изделия не превышает количество
        if item_number > orderitem_qty:
            return ApprovalResponse(
                success=False,
                message=f"Номер изделия {item_number} превышает количество {orderitem_qty}",
                voice_message=f"Ошибка. Номер изделия {item_number} превышает количество {orderitem_qty}",
                product_info=None
            )
        
        # 2. Находим запись в CT_WHDETAIL по ORDERITEMSID и ITEMNO
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
                e.HEIGHT
            FROM CT_WHDETAIL w
            INNER JOIN CT_ELEMENTS e ON w.CTELEMENTSID = e.CTELEMENTSID
            WHERE e.ORDERITEMSID = ? AND w.ITEMNO = ?
        """
        
        whdetail_result = db.execute_query(query_whdetail, (orderitems_id, item_number))
        
        if not whdetail_result:
            return ApprovalResponse(
                success=False,
                message=f"Изделие №{item_number} заказа {order_number} не найдено на складе",
                voice_message=f"Изделие номер {item_number} заказа {order_number} не найдено на складе",
                product_info=None
            )
        
        whdetail_data = whdetail_result[0]
        ctwhdetail_id = whdetail_data['CTWHDETAILID']
        is_approved = whdetail_data['ISAPPROVED']
        element_name = whdetail_data['ELEMENT_NAME'].strip() if whdetail_data['ELEMENT_NAME'] else None
        width = whdetail_data['WIDTH']
        height = whdetail_data['HEIGHT']
        
        # 3. Проверяем, не приходовано ли уже
        if is_approved == 1:
            date_approved = whdetail_data['DATEAPPROVED']
            date_str = ""
            if date_approved:
                date_str = f" (приходовано {date_approved.strftime('%d.%m.%Y %H:%M')})"
            
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
                    grordersdetail_id=grordersdetail_id
                )
            )
        
        # 4. Приходуем изделие - обновляем CT_WHDETAIL
        update_query = """
            UPDATE CT_WHDETAIL
            SET ISAPPROVED = 1,
                DATEAPPROVED = CURRENT_TIMESTAMP
            WHERE CTWHDETAILID = ?
        """
        
        rows_updated = db.execute_update(update_query, (ctwhdetail_id,))
        
        if rows_updated == 0:
            return ApprovalResponse(
                success=False,
                message="Не удалось обновить запись в базе данных",
                voice_message="Ошибка при обновлении базы данных",
                product_info=None
            )
        
        # 5. Формируем успешный ответ
        voice_message = f"Изделие номер {item_number} заказа {order_number} конструкции {construction_number} готово"
        
        return ApprovalResponse(
            success=True,
            message=f"Изделие успешно приходовано",
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
                grordersdetail_id=grordersdetail_id
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

