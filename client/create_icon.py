"""
Скрипт для создания иконки приложения
"""
from PIL import Image, ImageDraw, ImageFont

def create_icon():
    """Создает иконку с emoji для приложения"""
    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for size in sizes:
        # Создаем изображение с белым фоном
        image = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)

        # Рисуем синий круг как фон
        margin = size // 10
        draw.ellipse([margin, margin, size-margin, size-margin], fill='#2196F3')

        # Пытаемся использовать системный шрифт с поддержкой emoji
        try:
            font_size = int(size * 0.6)
            font = ImageFont.truetype("seguiemj.ttf", font_size)
        except (OSError, IOError):
            try:
                font_size = int(size * 0.6)
                font = ImageFont.truetype("arial.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()

        # Рисуем emoji в центре
        emoji = "📦"

        # Получаем размер текста для центрирования
        bbox = draw.textbbox((0, 0), emoji, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        position = ((size - text_width) // 2 - bbox[0],
                   (size - text_height) // 2 - bbox[1])

        draw.text(position, emoji, font=font, embedded_color=True)

        images.append(image)

    # Сохраняем как .ico файл со всеми размерами
    images[0].save('icon.ico', format='ICO', sizes=[(img.width, img.height) for img in images])
    print("Icon created: icon.ico")

if __name__ == '__main__':
    create_icon()
