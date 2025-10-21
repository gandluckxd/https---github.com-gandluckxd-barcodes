"""
Pydantic модели для API
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BarcodeRequest(BaseModel):
    """Запрос на обработку штрихкода"""
    barcode: str = Field(..., description="Штрихкод в формате: [номер изделия][grordersdetailid]")
    
    class Config:
        json_schema_extra = {
            "example": {
                "barcode": "1109565"
            }
        }


class ProductInfo(BaseModel):
    """Информация об изделии"""
    order_number: str = Field(..., description="Номер заказа")
    construction_number: str = Field(..., description="Номер конструкции")
    item_number: int = Field(..., description="Номер изделия")
    orderitems_id: int = Field(..., description="ID элемента заказа")
    orderitems_name: str = Field(..., description="Наименование элемента заказа")
    qty: int = Field(..., description="Общее количество изделий")
    element_name: Optional[str] = Field(None, description="Наименование элемента")
    width: Optional[int] = Field(None, description="Ширина")
    height: Optional[int] = Field(None, description="Высота")
    grordersdetail_id: int = Field(..., description="ID записи в GRORDERSDETAIL")


class ApprovalResponse(BaseModel):
    """Ответ на запрос приходования"""
    success: bool = Field(..., description="Успешность операции")
    message: str = Field(..., description="Сообщение для пользователя")
    voice_message: str = Field(..., description="Текст для озвучивания")
    product_info: Optional[ProductInfo] = Field(None, description="Информация об изделии")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Изделие успешно приходовано",
                "voice_message": "Изделие номер 1 заказа 19561 конструкции 02 готово",
                "product_info": {
                    "order_number": "19561",
                    "construction_number": "02",
                    "item_number": 1,
                    "orderitems_id": 137660,
                    "orderitems_name": "02",
                    "qty": 1,
                    "element_name": "19561 / 02 / 1",
                    "width": 1200,
                    "height": 1400,
                    "grordersdetail_id": 109565
                }
            }
        }


class HealthResponse(BaseModel):
    """Ответ на проверку здоровья сервиса"""
    status: str = Field(..., description="Статус сервиса")
    database_connected: bool = Field(..., description="Статус подключения к БД")

