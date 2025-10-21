# API сервер для системы учета готовности изделий

## Установка

1. Активируйте виртуальное окружение:
```bash
cd api
venv\Scripts\activate
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` на основе `.env.example` и настройте параметры подключения к базе данных.

## Запуск

```bash
python main.py
```

Или через uvicorn:
```bash
uvicorn main:app --host 0.0.0.0 --port 8015 --reload
```

## API Endpoints

### GET `/`
Проверка работоспособности API и подключения к БД

### POST `/api/process-barcode`
Обработка штрихкода и приходование изделия

**Request Body:**
```json
{
  "barcode": "1109565"
}
```

**Response:**
```json
{
  "success": true,
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
```

## Формат штрихкода

`[номер изделия][grordersdetailid]`

- Первая цифра - номер изделия (1, 2, 3...)
- Остальные цифры - GRORDERSDETAILID

Пример: `1109565`
- 1 - первое изделие
- 109565 - GRORDERSDETAILID

