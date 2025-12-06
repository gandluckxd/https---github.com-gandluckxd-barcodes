"""
Pydantic модели для API
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BarcodeRequest(BaseModel):
    """Запрос на обработку штрихкода"""
    barcode: str = Field(..., description="Штрихкод в формате: [номер изделия (2 цифры)][ORDERITEMSID стеклопакета (7 цифр)]")
    
    class Config:
        json_schema_extra = {
            "example": {
                "barcode": "011234567"
            }
        }


class ProductInfo(BaseModel):
    """Информация об изделии"""
    order_number: str = Field(..., description="Номер заказа")
    construction_number: str = Field(..., description="Номер конструкции")
    item_number: int = Field(..., description="Номер изделия")
    orderitems_id: int = Field(..., description="ID элемента заказа (изделия)")
    orderitems_name: str = Field(..., description="Наименование элемента заказа")
    qty: int = Field(..., description="Общее количество изделий")
    element_name: Optional[str] = Field(None, description="Наименование элемента")
    width: Optional[int] = Field(None, description="Ширина")
    height: Optional[int] = Field(None, description="Высота")
    glass_orderitems_id: int = Field(..., description="ID стеклопакета в ORDERITEMS")
    order_id: Optional[int] = Field(None, description="ID заказа")
    total_items_in_order: Optional[int] = Field(None, description="Общее количество изделий в заказе")
    approved_items_in_order: Optional[int] = Field(None, description="Количество проведенных изделий в заказе")


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
                "voice_message": "Изделие номер 1 конструкции 01 заказа 19686 готово",
                "product_info": {
                    "order_number": "19686",
                    "construction_number": "01",
                    "item_number": 1,
                    "orderitems_id": 137660,
                    "orderitems_name": "01",
                    "qty": 1,
                    "element_name": "19686 / 01 / 1",
                    "width": 1200,
                    "height": 1400,
                    "glass_orderitems_id": 1234567
                }
            }
        }


class HealthResponse(BaseModel):
    """Ответ на проверку здоровья сервиса"""
    status: str = Field(..., description="Статус сервиса")
    database_connected: bool = Field(..., description="Статус подключения к БД")
    api_version: str = Field(..., description="Версия API")

